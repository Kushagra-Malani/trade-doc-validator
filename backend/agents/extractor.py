"""
Extractor Agent — Agent A

Input:  File path to a PDF or image
Output: ExtractionResult with structured fields + confidence scores

Model:  GPT-4o (vision)
Fallback: If >50% fields have confidence < 0.5, retry with image preprocessing

Required fields to extract:
  - consignee_name
  - hs_code
  - port_of_loading
  - port_of_discharge
  - incoterms
  - description_of_goods
  - gross_weight
  - invoice_number
  - shipper_name (bonus)
  - vessel_name (bonus)
  - container_number (bonus)
"""

import time
import uuid
import logging
from pathlib import Path

from backend.config import MODEL_EXTRACTION
from backend.models.schemas import ExtractedField, ExtractionResult
from backend.utils.llm_client import call_llm_json, calculate_cost
from backend.utils.document_processor import (
    pdf_to_base64,
    image_to_base64,
    preprocess_image,
)

logger = logging.getLogger(__name__)

# ─── Prompts (Section 4) ────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a trade document field extraction agent. You read trade documents
(Bills of Lading, Commercial Invoices, Packing Lists, Certificates of Origin)
and extract structured fields.

RULES:
1. Only extract values that are EXPLICITLY visible in the document.
2. If a field is not present or not readable, set value to null and confidence to 0.0.
3. NEVER guess or infer a value. If you're unsure, set a low confidence score.
4. Confidence scoring guide:
   - 1.0: Field is clearly visible and unambiguous
   - 0.8-0.9: Field is visible but formatting makes it slightly ambiguous
   - 0.6-0.7: Field is partially obscured or the value is hard to read
   - 0.3-0.5: Field might be present but you're not sure
   - 0.0: Field is not present in the document"""

USER_PROMPT = """\
Extract the following fields from this trade document. Return ONLY a JSON object
with this exact structure:

{
  "document_type": "bill_of_lading | commercial_invoice | packing_list | certificate_of_origin",
  "fields": [
    {
      "field_name": "consignee_name",
      "value": "<extracted value or null>",
      "confidence": <0.0 to 1.0>,
      "source_location": "<where on the document you found this, e.g., 'top-right section, row 3'>"
    }
  ]
}

Extract ALL of the following fields (use the exact field_name strings):
consignee_name, hs_code, port_of_loading, port_of_discharge,
incoterms, description_of_goods, gross_weight, invoice_number,
shipper_name, vessel_name, container_number

Do not include any text outside the JSON object."""

# All 11 field names the extractor must produce
REQUIRED_FIELDS = [
    "consignee_name",
    "hs_code",
    "port_of_loading",
    "port_of_discharge",
    "incoterms",
    "description_of_goods",
    "gross_weight",
    "invoice_number",
    "shipper_name",
    "vessel_name",
    "container_number",
]


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _file_to_base64(file_path: str) -> str:
    """Convert a PDF or image file to a base64-encoded PNG string."""
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return pdf_to_base64(file_path)
    elif ext in {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}:
        return image_to_base64(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def _build_messages(base64_img: str) -> list[dict]:
    """Build the OpenAI chat messages list with the image inline."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": USER_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64_img}",
                        "detail": "high",
                    },
                },
            ],
        },
    ]


def _parse_extraction(
    parsed: dict,
    document_id: str,
    model: str,
    elapsed_ms: int,
    token_usage: dict,
) -> ExtractionResult:
    """
    Parse the LLM JSON response into an ExtractionResult.
    Ensures every required field is present (fills missing ones with null/0.0).
    """
    raw_fields: list[dict] = parsed.get("fields", [])
    # Index by field_name for quick lookup
    field_map = {f["field_name"]: f for f in raw_fields if "field_name" in f}

    fields: list[ExtractedField] = []
    for name in REQUIRED_FIELDS:
        if name in field_map:
            f = field_map[name]
            fields.append(
                ExtractedField(
                    field_name=name,
                    value=f.get("value"),
                    confidence=float(f.get("confidence", 0.0)),
                    source_location=f.get("source_location"),
                )
            )
        else:
            # Field was not returned by the LLM — mark absent
            fields.append(
                ExtractedField(
                    field_name=name,
                    value=None,
                    confidence=0.0,
                    source_location=None,
                )
            )

    return ExtractionResult(
        document_id=document_id,
        document_type=parsed.get("document_type", "unknown"),
        fields=fields,
        raw_text_snippet=None,
        extraction_model=model,
        extraction_time_ms=elapsed_ms,
        token_usage=token_usage,
    )


def _avg_confidence(result: ExtractionResult) -> float:
    """Return the mean confidence across all fields."""
    if not result.fields:
        return 0.0
    return sum(f.confidence for f in result.fields) / len(result.fields)


def _low_confidence_ratio(result: ExtractionResult, threshold: float = 0.5) -> float:
    """Return the fraction of fields with confidence below *threshold*."""
    if not result.fields:
        return 1.0
    low = sum(1 for f in result.fields if f.confidence < threshold)
    return low / len(result.fields)


# ─── Main entry point ───────────────────────────────────────────────────────


async def extract_document(
    file_path: str,
    model: str | None = None,
    retry_with_preprocessing: bool = True,
    run_id: str = "unknown",
) -> ExtractionResult:
    """
    Extract structured fields from a trade document.

    1. Render document to base64 image (PDF → image, or load image directly).
    2. Call GPT-4o vision with structured JSON output prompt.
    3. Parse response into ExtractionResult.
    4. If >50% of fields have confidence < 0.5 and *retry_with_preprocessing*
       is True, preprocess the image and retry once, returning the result with
       the higher average confidence.
    5. Return ExtractionResult with timing + cost metadata.
    """
    model = model or MODEL_EXTRACTION
    document_id = str(uuid.uuid4())[:8]

    # 1. Document → base64
    base64_img = _file_to_base64(file_path)

    # 2. First extraction attempt
    start = time.perf_counter()
    messages = _build_messages(base64_img)
    llm_response = await call_llm_json(
        messages=messages,
        model=model,
        run_id=run_id,
        agent_name="Extractor",
    )
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    result = _parse_extraction(
        parsed=llm_response["parsed"],
        document_id=document_id,
        model=model,
        elapsed_ms=elapsed_ms,
        token_usage=llm_response["token_usage"],
    )

    # 3. Low-confidence fallback
    if retry_with_preprocessing and _low_confidence_ratio(result) > 0.5:
        logger.info(
            "[%s] Extractor — low confidence (%.0f%% fields < 0.5). "
            "Retrying with preprocessed image …",
            run_id,
            _low_confidence_ratio(result) * 100,
        )

        preprocessed_img = preprocess_image(base64_img)
        messages_retry = _build_messages(preprocessed_img)

        start_retry = time.perf_counter()
        llm_retry = await call_llm_json(
            messages=messages_retry,
            model=model,
            run_id=run_id,
            agent_name="Extractor (retry-preprocessed)",
        )
        elapsed_retry = int((time.perf_counter() - start_retry) * 1000)

        result_retry = _parse_extraction(
            parsed=llm_retry["parsed"],
            document_id=document_id,
            model=model,
            elapsed_ms=elapsed_retry,
            token_usage=llm_retry["token_usage"],
        )

        # Keep the better result (higher average confidence)
        if _avg_confidence(result_retry) > _avg_confidence(result):
            logger.info(
                "[%s] Extractor — preprocessed result is better (%.2f > %.2f)",
                run_id,
                _avg_confidence(result_retry),
                _avg_confidence(result),
            )
            result = result_retry

    logger.info(
        "[%s] Extractor — finished. doc_type=%s avg_confidence=%.2f",
        run_id,
        result.document_type,
        _avg_confidence(result),
    )

    return result

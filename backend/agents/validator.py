"""
Validator Agent — Agent B

Input:  ExtractionResult + CustomerRuleSet (via customer_id lookup)
Output: ValidationResult with per-field match / mismatch / uncertain

Model:  GPT-4o-mini (structured output) — used ONLY for fuzzy matching
Deterministic matching for: exact, regex, presence, contains

Validation Logic:
  - For each rule in the customer's rule set, compare against extracted value.
  - Match:     values are equivalent (case-insensitive, trimmed)
  - Mismatch:  values differ AND extraction confidence was >= 0.6
  - Uncertain: extraction confidence < 0.6 OR the match is ambiguous

Critical Rule: NEVER silently approve uncertain fields.
"""

import re
import time
import logging

from backend.config import MODEL_VALIDATION
from backend.models.schemas import (
    ExtractionResult,
    ExtractedField,
    FieldValidationStatus,
    FieldValidationResult,
    ValidationResult,
)
from backend.rules.customer_rules import CUSTOMER_RULES
from backend.utils.llm_client import call_llm_json

logger = logging.getLogger(__name__)

def normalize_hs_code(value: str) -> str:
    """
    Normalize HS code to plain digits.
    "6109.10.00" → "61091000"
    "6109 10 00" → "61091000"
    "61091000"   → "61091000"
    """
    if not value:
        return value
    return re.sub(r"[.\s\-]", "", value.strip())

def normalize_port(value: str) -> str:
    """
    Extract the port code/name from verbose strings.
    "INNSA — Nhava Sheva, India"  → "INNSA"
    "USLAX — Los Angeles, USA"    → "USLAX"
    "Nhava Sheva"                 → "Nhava Sheva"
    Splits on " — ", " - ", " / " and returns the first part stripped.
    """
    if not value:
        return value
    for sep in [" — ", " - ", " – ", " / "]:
        if sep in value:
            return value.split(sep)[0].strip()
    return value.strip()

# ─── Fuzzy-match prompt (Section 5) ─────────────────────────────────────────

FUZZY_SYSTEM_PROMPT = """\
You are a field validation agent for trade documents. You compare extracted
field values against expected customer requirements."""

FUZZY_USER_PROMPT_TEMPLATE = """\
Compare these two values for the field "{field_name}":
- Extracted from document: "{extracted_value}"
- Expected by customer: "{expected_value}"

Context: This is a {field_context} field on a trade document.
Are these values referring to the same thing?

Return JSON:
{{
  "match": true | false,
  "confidence": <0.0 to 1.0>,
  "reason": "<brief explanation>"
}}"""

# Human-readable field context descriptions for the LLM prompt
FIELD_CONTEXTS: dict[str, str] = {
    "consignee_name": "consignee / receiver company name",
    "hs_code": "Harmonized System commodity code",
    "port_of_loading": "port of loading (origin)",
    "port_of_discharge": "port of discharge (destination)",
    "incoterms": "Incoterms trade term",
    "description_of_goods": "goods description",
    "gross_weight": "gross weight",
    "invoice_number": "commercial invoice number",
    "shipper_name": "shipper / exporter company name",
    "vessel_name": "vessel / ship name",
    "container_number": "container identification number",
}


# ─── Deterministic matchers ─────────────────────────────────────────────────


def _match_exact(
    extracted: str,
    rule: dict,
) -> tuple[bool, str]:
    """Case-insensitive exact match with trimming.  Also checks alternatives."""
    expected: str = rule.get("expected", "")
    candidates = [expected] + rule.get("alternatives", [])
    extracted_norm = extracted.strip().upper()
    for candidate in candidates:
        candidate_norm = candidate.strip().upper()
        if extracted_norm == candidate_norm or candidate_norm in extracted_norm:
            return True, f"Exact/Contains match with '{candidate}'"
    return False, (
        f"Extracted '{extracted}' does not match expected '{expected}' "
        f"or any alternatives {rule.get('alternatives', [])}"
    )


def _match_regex(
    extracted: str,
    rule: dict,
) -> tuple[bool, str]:
    """Regex pattern match.  Also checks allowed_values if present."""
    pattern = rule.get("expected_pattern", "")
    allowed = rule.get("allowed_values", [])

    if not re.match(pattern, extracted.strip()):
        return False, f"Value '{extracted}' does not match pattern '{pattern}'"

    if allowed and extracted.strip() not in allowed:
        return False, (
            f"Value '{extracted}' matches pattern but is not in "
            f"allowed values {allowed}"
        )

    return True, f"Matches pattern '{pattern}'"


def _match_presence(
    extracted: str | None,
    _rule: dict,
) -> tuple[bool, str]:
    """Check that the value is not null, not empty, and not whitespace-only."""
    if extracted is None or extracted.strip() == "":
        return False, "Field is missing or empty"
    return True, "Field is present"


def _match_contains(
    extracted: str,
    rule: dict,
) -> tuple[bool, str]:
    """Check if the expected value is a substring of the extracted value."""
    expected: str = rule.get("expected", "")
    if expected.strip().upper() in extracted.strip().upper():
        return True, f"Extracted value contains '{expected}'"
    return False, f"Extracted value does not contain '{expected}'"


DETERMINISTIC_MATCHERS = {
    "exact": _match_exact,
    "regex": _match_regex,
    "presence": _match_presence,
    "contains": _match_contains,
}


# ─── LLM-assisted fuzzy matcher ─────────────────────────────────────────────


async def _match_fuzzy(
    field_name: str,
    extracted_value: str,
    rule: dict,
    model: str,
    run_id: str,
) -> tuple[bool | None, float, str]:
    """
    Ask GPT-4o-mini whether two values refer to the same entity.

    Returns:
        (is_match, confidence, reason)
        is_match is None when the result is ambiguous (confidence 0.5–0.8).
    """
    expected = rule.get("expected", "")
    context = FIELD_CONTEXTS.get(field_name, field_name)

    messages = [
        {"role": "system", "content": FUZZY_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": FUZZY_USER_PROMPT_TEMPLATE.format(
                field_name=field_name,
                extracted_value=extracted_value,
                expected_value=expected,
                field_context=context,
            ),
        },
    ]

    llm = await call_llm_json(
        messages=messages,
        model=model,
        run_id=run_id,
        agent_name="Validator (fuzzy)",
    )
    parsed = llm["parsed"]

    match_flag = parsed.get("match", False)
    confidence = float(parsed.get("confidence", 0.0))
    reason = parsed.get("reason", "")

    # Ambiguous zone: confidence between 0.5 and 0.8 → uncertain
    if 0.5 <= confidence < 0.8:
        return None, confidence, reason

    threshold = rule.get("fuzzy_threshold", 0.85)
    if match_flag and confidence >= threshold:
        return True, confidence, reason

    return False, confidence, reason


# ─── Main entry point ───────────────────────────────────────────────────────


async def validate_extraction(
    extraction: ExtractionResult,
    customer_id: str,
    model: str | None = None,
    run_id: str = "unknown",
) -> ValidationResult:
    """
    Validate extracted fields against the customer's rule set.

    1. Load customer rule set from CUSTOMER_RULES.
    2. For each rule:
       a. Find the matching ExtractedField.
       b. If extraction confidence < 0.6 → mark UNCERTAIN regardless.
       c. Apply deterministic or fuzzy matcher.
       d. Record the result.
    3. Compute overall_score = matched / total_required.
    4. Return ValidationResult.
    """
    model = model or MODEL_VALIDATION
    start = time.perf_counter()

    # ── Load rules ───────────────────────────────────────────────────────
    customer = CUSTOMER_RULES.get(customer_id)
    if not customer:
        raise ValueError(f"Unknown customer_id: {customer_id}")
    rules = customer["rules"]

    # Index extracted fields by name
    field_map: dict[str, ExtractedField] = {
        f.field_name: f for f in extraction.fields
    }

    field_results: list[FieldValidationResult] = []
    total_required = 0
    matched_count = 0
    has_mismatches = False
    has_uncertainties = False

    # Aggregate token usage from any LLM calls made for fuzzy matching
    agg_tokens = {"input": 0, "output": 0}

    for field_name, rule in rules.items():
        is_required = rule.get("required", False)
        if is_required:
            total_required += 1

        match_type: str = rule.get("match_type", "presence")
        extracted_field = field_map.get(field_name)
        extracted_value = extracted_field.value if extracted_field else None
        extraction_confidence = extracted_field.confidence if extracted_field else 0.0

        if field_name == "hs_code" and extracted_value:
            extracted_value = normalize_hs_code(extracted_value)

        if field_name in ("port_of_loading", "port_of_discharge") and extracted_value:
            extracted_value = normalize_port(extracted_value)

        # Determine expected value for display purposes
        expected_display = rule.get("expected", rule.get("expected_pattern", "—"))

        # ── Confidence too low → UNCERTAIN (Critical Rule #1) ────────
        if extraction_confidence < 0.6:
            field_results.append(
                FieldValidationResult(
                    field_name=field_name,
                    status=FieldValidationStatus.UNCERTAIN,
                    extracted_value=extracted_value,
                    expected_value=str(expected_display),
                    reason=(
                        f"Extraction confidence too low ({extraction_confidence:.2f} < 0.60). "
                        "Cannot validate with sufficient certainty."
                    ),
                    confidence=extraction_confidence,
                )
            )
            has_uncertainties = True
            continue

        # ── Deterministic matchers ───────────────────────────────────
        if match_type in DETERMINISTIC_MATCHERS:
            matcher = DETERMINISTIC_MATCHERS[match_type]
            is_match, reason = matcher(extracted_value or "", rule)

            if is_match:
                status = FieldValidationStatus.MATCH
                matched_count += 1
            else:
                status = FieldValidationStatus.MISMATCH
                has_mismatches = True

            field_results.append(
                FieldValidationResult(
                    field_name=field_name,
                    status=status,
                    extracted_value=extracted_value,
                    expected_value=str(expected_display),
                    reason=reason,
                    confidence=extraction_confidence,
                )
            )

        # ── Fuzzy matcher (LLM-assisted) ─────────────────────────────
        elif match_type == "fuzzy":
            is_match, fuzzy_conf, reason = await _match_fuzzy(
                field_name=field_name,
                extracted_value=extracted_value or "",
                rule=rule,
                model=model,
                run_id=run_id,
            )

            if is_match is None:
                # Ambiguous → uncertain
                status = FieldValidationStatus.UNCERTAIN
                has_uncertainties = True
            elif is_match:
                status = FieldValidationStatus.MATCH
                matched_count += 1
            else:
                status = FieldValidationStatus.MISMATCH
                has_mismatches = True

            field_results.append(
                FieldValidationResult(
                    field_name=field_name,
                    status=status,
                    extracted_value=extracted_value,
                    expected_value=str(expected_display),
                    reason=reason,
                    confidence=fuzzy_conf,
                )
            )

        else:
            # Unknown match_type — mark not applicable
            field_results.append(
                FieldValidationResult(
                    field_name=field_name,
                    status=FieldValidationStatus.NOT_APPLICABLE,
                    extracted_value=extracted_value,
                    expected_value=str(expected_display),
                    reason=f"Unknown match_type: {match_type}",
                    confidence=extraction_confidence,
                )
            )

    # ── Overall score ────────────────────────────────────────────────────
    overall_score = matched_count / total_required if total_required > 0 else 0.0
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    result = ValidationResult(
        document_id=extraction.document_id,
        customer_id=customer_id,
        field_results=field_results,
        overall_score=overall_score,
        has_mismatches=has_mismatches,
        has_uncertainties=has_uncertainties,
        validation_model=model,
        validation_time_ms=elapsed_ms,
        token_usage=agg_tokens,
    )

    logger.info(
        "[%s] Validator — finished. score=%.2f mismatches=%s uncertainties=%s",
        run_id,
        overall_score,
        has_mismatches,
        has_uncertainties,
    )

    return result

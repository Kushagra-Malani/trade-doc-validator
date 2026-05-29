"""
Router / Decision Agent — Agent C

Input:  ValidationResult + ExtractionResult + customer_id
Output: RouterResult with decision, reasoning, and optional amendment email draft

Model:  GPT-4o-mini — used ONLY for generating the amendment email draft

Decision Logic (deterministic):
  IF validation has ANY mismatch         → REQUEST_AMENDMENT
  ELIF validation has ANY uncertain      → FLAG_FOR_REVIEW
  ELIF score >= 0.95, no uncertain/mismatch → AUTO_APPROVE
  ELSE                                   → FLAG_FOR_REVIEW
"""

import time
import logging

from backend.config import MODEL_ROUTING
from backend.models.schemas import (
    ExtractionResult,
    ValidationResult,
    FieldValidationStatus,
    RoutingDecision,
    RouterResult,
)
from backend.utils.llm_client import call_llm

logger = logging.getLogger(__name__)

# ─── Amendment email prompt (Section 6) ──────────────────────────────────────

AMENDMENT_SYSTEM_PROMPT = """\
You are a trade document amendment request drafter. You generate professional,
clear amendment emails that a CG (Cargo/Control Group) operator can send to
a Shipping Unit (SU) listing all document discrepancies that need correction."""

AMENDMENT_USER_PROMPT_TEMPLATE = """\
Draft an amendment request email for the following discrepancies found in
shipment document {document_id}:

Discrepancies:
{discrepancy_block}

Requirements:
1. Be professional but direct
2. List EVERY discrepancy with the field name, what was found, and what is expected
3. Ask the SU to correct and resubmit
4. Keep it under 200 words
5. Do NOT include pleasantries beyond a greeting and sign-off

Format as a plain email body (no subject line — that will be added separately)."""


# ─── Main entry point ───────────────────────────────────────────────────────


async def route_decision(
    validation: ValidationResult,
    extraction: ExtractionResult,
    customer_id: str,
    model: str | None = None,
    run_id: str = "unknown",
) -> RouterResult:
    """
    Apply the deterministic decision tree and, if needed, call the LLM to
    generate an amendment email draft.

    1. Collect mismatches and uncertain fields from the ValidationResult.
    2. Apply decision tree.
    3. If REQUEST_AMENDMENT → generate amendment email via LLM.
    4. Return RouterResult with decision, reasoning, draft email (if any).
    """
    model = model or MODEL_ROUTING
    start = time.perf_counter()
    token_usage = {"input": 0, "output": 0}

    # ── Collect mismatches and uncertain fields ──────────────────────────
    mismatches = [
        fr for fr in validation.field_results
        if fr.status == FieldValidationStatus.MISMATCH
    ]
    uncertainties = [
        fr for fr in validation.field_results
        if fr.status == FieldValidationStatus.UNCERTAIN
    ]

    discrepancies: list[dict] = [
        {
            "field": m.field_name,
            "found": m.extracted_value or "—",
            "expected": m.expected_value or "—",
        }
        for m in mismatches
    ]

    # ── Deterministic decision tree (Section 6) ─────────────────────────
    amendment_draft: str | None = None
    decision: RoutingDecision
    reasoning: str

    if mismatches:
        # ── REQUEST_AMENDMENT ────────────────────────────────────────
        decision = RoutingDecision.REQUEST_AMENDMENT

        mismatch_summary = ", ".join(m.field_name for m in mismatches)
        uncertain_summary = (
            f" Additionally, {len(uncertainties)} field(s) are uncertain "
            f"({', '.join(u.field_name for u in uncertainties)})."
            if uncertainties
            else ""
        )
        reasoning = (
            f"{len(mismatches)} field mismatch(es) detected ({mismatch_summary})."
            f"{uncertain_summary} Amendment requested."
        )

        # Generate the amendment email draft via LLM
        discrepancy_lines = "\n".join(
            f"- Field: {d['field']}\n"
            f"  Found in document: {d['found']}\n"
            f"  Expected by customer: {d['expected']}"
            for d in discrepancies
        )

        messages = [
            {"role": "system", "content": AMENDMENT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": AMENDMENT_USER_PROMPT_TEMPLATE.format(
                    document_id=extraction.document_id,
                    discrepancy_block=discrepancy_lines,
                ),
            },
        ]

        llm_response = await call_llm(
            messages=messages,
            model=model,
            run_id=run_id,
            agent_name="Router (amendment draft)",
        )
        amendment_draft = llm_response["content"]
        token_usage = llm_response["token_usage"]

    elif uncertainties:
        # ── FLAG_FOR_REVIEW ──────────────────────────────────────────
        decision = RoutingDecision.FLAG_FOR_REVIEW
        field_list = ", ".join(u.field_name for u in uncertainties)
        reasoning = (
            f"{len(uncertainties)} field(s) could not be validated with "
            f"sufficient confidence ({field_list}). Flagged for human review."
        )

    elif validation.overall_score >= 0.95 and not uncertainties and not mismatches:
        # ── AUTO_APPROVE ─────────────────────────────────────────────
        decision = RoutingDecision.AUTO_APPROVE
        reasoning = (
            "All fields validated successfully against customer requirements. "
            f"Overall validation score: {validation.overall_score:.0%}."
        )

    else:
        # ── FLAG_FOR_REVIEW (catch-all) ──────────────────────────────
        decision = RoutingDecision.FLAG_FOR_REVIEW
        reasoning = (
            f"Validation score ({validation.overall_score:.0%}) is below the "
            "auto-approval threshold (95%). Flagged for human review."
        )

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    result = RouterResult(
        document_id=extraction.document_id,
        decision=decision,
        reasoning=reasoning,
        amendment_email_draft=amendment_draft,
        discrepancies=discrepancies,
        routing_model=model,
        routing_time_ms=elapsed_ms,
        token_usage=token_usage,
    )

    logger.info(
        "[%s] Router — decision=%s reasoning=%s",
        run_id,
        decision.value,
        reasoning[:120],
    )

    return result

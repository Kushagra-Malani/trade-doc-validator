"""
state.py — Pipeline state definition for the LangGraph orchestrator.

PipelineGraphState is a TypedDict that flows through every node in the
pipeline graph.  Each node reads the fields it needs and writes only its
own output section.
"""

from typing import TypedDict, Optional

from backend.models.schemas import (
    ExtractionResult,
    ValidationResult,
    RouterResult,
    PipelineStatus,
)


class PipelineGraphState(TypedDict):
    """
    Complete state carried through the LangGraph pipeline.

    Input fields (set once at pipeline start):
      shipment_id, document_id, document_path, customer_id, run_id

    Tracking fields (mutated by nodes):
      status, retry_count, error_log

    Agent outputs (populated as the pipeline progresses):
      extraction_result, validation_result, routing_result

    Metrics (accumulated across nodes):
      total_cost_usd, total_latency_ms
    """

    # ── Input ────────────────────────────────────────────────────────────
    shipment_id: str
    document_id: str
    document_path: str
    customer_id: str
    run_id: str

    # ── Pipeline tracking ────────────────────────────────────────────────
    status: PipelineStatus
    retry_count: int
    error_log: list[str]

    # ── Agent outputs ────────────────────────────────────────────────────
    extraction_result: Optional[ExtractionResult]
    validation_result: Optional[ValidationResult]
    routing_result: Optional[RouterResult]

    # ── Metrics ──────────────────────────────────────────────────────────
    total_cost_usd: float
    total_latency_ms: int

"""
schemas.py — Pydantic models for all data structures.

These are the contracts between all agents in the pipeline.
Every field, type, and constraint matches Section 3 of the architecture spec.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


# ─── Extraction ──────────────────────────────────────────────────────────────


class ExtractedField(BaseModel):
    """A single field extracted from a trade document."""
    field_name: str
    value: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    source_location: Optional[str] = None  # e.g., "page 1, top-right"


class ExtractionResult(BaseModel):
    """Complete extraction output from the Extractor Agent."""
    document_id: str
    document_type: str  # "bill_of_lading", "commercial_invoice", "packing_list", "certificate_of_origin"
    fields: list[ExtractedField]
    raw_text_snippet: Optional[str] = None
    extraction_model: str
    extraction_time_ms: int
    token_usage: dict  # {"input": int, "output": int}


# ─── Validation ──────────────────────────────────────────────────────────────


class FieldValidationStatus(str, Enum):
    """Possible outcomes for a single field validation check."""
    MATCH = "match"
    MISMATCH = "mismatch"
    UNCERTAIN = "uncertain"
    NOT_APPLICABLE = "not_applicable"


class FieldValidationResult(BaseModel):
    """Validation result for a single field."""
    field_name: str
    status: FieldValidationStatus
    extracted_value: Optional[str] = None
    expected_value: Optional[str] = None
    reason: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)


class ValidationResult(BaseModel):
    """Complete validation output from the Validator Agent."""
    document_id: str
    customer_id: str
    field_results: list[FieldValidationResult]
    overall_score: float = Field(ge=0.0, le=1.0)  # % of fields that matched
    has_mismatches: bool
    has_uncertainties: bool
    validation_model: str
    validation_time_ms: int
    token_usage: dict


# ─── Routing ─────────────────────────────────────────────────────────────────


class RoutingDecision(str, Enum):
    """Possible pipeline routing decisions."""
    AUTO_APPROVE = "auto_approve"
    FLAG_FOR_REVIEW = "flag_for_review"
    REQUEST_AMENDMENT = "request_amendment"


class RouterResult(BaseModel):
    """Complete routing output from the Router / Decision Agent."""
    document_id: str
    decision: RoutingDecision
    reasoning: str  # Human-readable explanation of why this decision was made
    amendment_email_draft: Optional[str] = None  # Only if decision is request_amendment
    discrepancies: list[dict] = []  # [{field, found, expected}] for amendment
    routing_model: str
    routing_time_ms: int
    token_usage: dict


# ─── Pipeline State ─────────────────────────────────────────────────────────


class PipelineStatus(str, Enum):
    """Pipeline execution stages."""
    PENDING = "pending"
    EXTRACTING = "extracting"
    VALIDATING = "validating"
    ROUTING = "routing"
    COMPLETE = "complete"
    ERROR = "error"


class PipelineState(BaseModel):
    """Full pipeline state — tracks a single document's journey through all agents."""
    shipment_id: str
    document_id: str
    document_path: str
    document_type: Optional[str] = None
    customer_id: str
    status: PipelineStatus = PipelineStatus.PENDING
    extraction_result: Optional[ExtractionResult] = None
    validation_result: Optional[ValidationResult] = None
    routing_result: Optional[RouterResult] = None
    error_log: list[str] = []
    retry_count: int = 0
    run_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    total_cost_usd: float = 0.0
    total_latency_ms: int = 0


# ─── API Models ──────────────────────────────────────────────────────────────


class UploadRequest(BaseModel):
    """Request body for document upload."""
    customer_id: str = "CUSTOMER_001"


class QueryRequest(BaseModel):
    """Request body for natural-language queries."""
    question: str


class QueryResponse(BaseModel):
    """Response for natural-language queries."""
    question: str
    sql_generated: str
    answer: str
    rows: list[dict] = []

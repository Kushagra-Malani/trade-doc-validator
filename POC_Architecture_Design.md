# Architecture Design — Multi-Agent Trade Document Validation Pipeline

## Working POC · Deliverable 2

> This document is the complete technical blueprint for building the POC. Every file, function, data structure, prompt, and interaction is specified. An AI coding agent should be able to read this document and produce a fully working system.

---

## Table of Contents

1. [Project Structure](#1-project-structure)
2. [Tech Stack & Dependencies](#2-tech-stack--dependencies)
3. [Data Models & Schemas](#3-data-models--schemas)
4. [Agent A: Extractor Agent](#4-agent-a-extractor-agent)
5. [Agent B: Validator Agent](#5-agent-b-validator-agent)
6. [Agent C: Router / Decision Agent](#6-agent-c-router--decision-agent)
7. [Pipeline Orchestrator (LangGraph)](#7-pipeline-orchestrator-langgraph)
8. [Storage Layer (SQLite)](#8-storage-layer-sqlite)
9. [Query Layer (Natural Language → SQL)](#9-query-layer-natural-language--sql)
10. [Minimal UI (React Frontend)](#10-minimal-ui-react-frontend)
11. [Backend API (FastAPI)](#11-backend-api-fastapi)
12. [Sample Data & Customer Rules](#12-sample-data--customer-rules)
13. [Error Handling & Observability](#13-error-handling--observability)
14. [How to Run](#14-how-to-run)

---

## 1. Project Structure

```
trade-doc-validator/
├── backend/
│   ├── main.py                    # FastAPI app entry point
│   ├── config.py                  # Environment variables, API keys, settings
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py             # Pydantic models for all data structures
│   │   └── database.py            # SQLite setup, ORM models, DB operations
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── extractor.py           # Extractor Agent
│   │   ├── validator.py           # Validator Agent
│   │   ├── router.py              # Router / Decision Agent
│   │   └── query_agent.py         # Natural Language → SQL query agent
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── orchestrator.py        # LangGraph pipeline definition
│   │   └── state.py               # Pipeline state definition
│   ├── rules/
│   │   ├── __init__.py
│   │   └── customer_rules.py      # Customer-specific validation rule sets
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── document_processor.py  # PDF/image preprocessing
│   │   └── llm_client.py          # Centralized LLM client with retry, cost tracking
│   └── sample_docs/               # Sample trade documents for testing
│       ├── clean_bill_of_lading.pdf
│       └── messy_commercial_invoice.png
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── App.jsx                # Main app component
│   │   ├── components/
│   │   │   ├── DocumentUpload.jsx # File upload component
│   │   │   ├── PipelineStatus.jsx # Shows pipeline progress
│   │   │   ├── ExtractionView.jsx # Shows extracted fields with confidence
│   │   │   ├── ValidationView.jsx # Shows field-by-field validation results
│   │   │   ├── DecisionView.jsx   # Shows routing decision + reasoning
│   │   │   ├── QueryInterface.jsx # Natural language query input + results
│   │   │   └── AmendmentDraft.jsx # Shows draft amendment email
│   │   ├── hooks/
│   │   │   └── usePipeline.js     # Custom hook for pipeline API calls
│   │   └── utils/
│   │       └── api.js             # API client
│   └── index.html
├── requirements.txt
├── .env.example
├── README.md
└── Makefile                       # Setup and run commands
```

---

## 2. Tech Stack & Dependencies

### Backend (Python 3.11+)

```
# requirements.txt
fastapi==0.115.0
uvicorn==0.30.0
python-multipart==0.0.9
pydantic==2.9.0
langgraph==0.2.0
langchain-openai==0.2.0
langchain-core==0.3.0
openai==1.50.0
Pillow==10.4.0
pdf2image==1.17.0
pymupdf==1.24.0            # PyMuPDF for PDF rendering
sqlite3                     # built-in
python-dotenv==1.0.1
httpx==0.27.0
tiktoken==0.7.0             # token counting for cost tracking
```

### Frontend (React + Vite)

```json
{
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "axios": "^1.7.0",
    "lucide-react": "^0.400.0"
  },
  "devDependencies": {
    "vite": "^5.4.0",
    "@vitejs/plugin-react": "^4.3.0",
    "tailwindcss": "^3.4.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0"
  }
}
```

### Environment Variables

```
# .env.example
OPENAI_API_KEY=sk-...
MODEL_EXTRACTION=gpt-4o
MODEL_VALIDATION=gpt-4o-mini
MODEL_ROUTING=gpt-4o-mini
MODEL_QUERY=gpt-4o-mini
DATABASE_PATH=./data/trade_docs.db
MAX_RETRIES=3
PIPELINE_TIMEOUT_SECONDS=60
COST_LIMIT_PER_DOC=0.50
```

---

## 3. Data Models & Schemas

### `backend/models/schemas.py`

Define all Pydantic models used across the system. These are the contracts between agents.

```python
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from enum import Enum

# ─── Extraction ───

class ExtractedField(BaseModel):
    field_name: str
    value: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    source_location: Optional[str] = None  # e.g., "page 1, top-right"

class ExtractionResult(BaseModel):
    document_id: str
    document_type: str  # "bill_of_lading", "commercial_invoice", "packing_list", "certificate_of_origin"
    fields: list[ExtractedField]
    raw_text_snippet: Optional[str] = None
    extraction_model: str
    extraction_time_ms: int
    token_usage: dict  # {"input": int, "output": int}

# ─── Validation ───

class FieldValidationStatus(str, Enum):
    MATCH = "match"
    MISMATCH = "mismatch"
    UNCERTAIN = "uncertain"
    NOT_APPLICABLE = "not_applicable"

class FieldValidationResult(BaseModel):
    field_name: str
    status: FieldValidationStatus
    extracted_value: Optional[str] = None
    expected_value: Optional[str] = None
    reason: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)

class ValidationResult(BaseModel):
    document_id: str
    customer_id: str
    field_results: list[FieldValidationResult]
    overall_score: float = Field(ge=0.0, le=1.0)  # % of fields that matched
    has_mismatches: bool
    has_uncertainties: bool
    validation_model: str
    validation_time_ms: int
    token_usage: dict

# ─── Routing ───

class RoutingDecision(str, Enum):
    AUTO_APPROVE = "auto_approve"
    FLAG_FOR_REVIEW = "flag_for_review"
    REQUEST_AMENDMENT = "request_amendment"

class RouterResult(BaseModel):
    document_id: str
    decision: RoutingDecision
    reasoning: str  # Human-readable explanation of why this decision was made
    amendment_email_draft: Optional[str] = None  # Only if decision is request_amendment
    discrepancies: list[dict] = []  # [{field, found, expected}] for amendment
    routing_model: str
    routing_time_ms: int
    token_usage: dict

# ─── Pipeline State ───

class PipelineStatus(str, Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    VALIDATING = "validating"
    ROUTING = "routing"
    COMPLETE = "complete"
    ERROR = "error"

class PipelineState(BaseModel):
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

# ─── API Models ───

class UploadRequest(BaseModel):
    customer_id: str = "CUSTOMER_001"

class QueryRequest(BaseModel):
    question: str

class QueryResponse(BaseModel):
    question: str
    sql_generated: str
    answer: str
    rows: list[dict] = []
```

---

## 4. Agent A: Extractor Agent

### `backend/agents/extractor.py`

**Responsibility:** Takes a raw PDF or image, renders it as an image, sends it to a vision-capable LLM, and returns structured field extraction with confidence scores.

#### Implementation Details

```python
"""
Extractor Agent

Input: File path to a PDF or image
Output: ExtractionResult with structured fields + confidence scores

Model: GPT-4o (vision)
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
```

#### Core Logic

1. **Document Preprocessing (`utils/document_processor.py`):**
   - If PDF: use PyMuPDF (`fitz`) to render each page as a PNG at 300 DPI. For this POC, process only the first page (most trade docs are 1 page). Convert the page to a base64-encoded image.
   - If image (PNG/JPG): load directly, convert to base64.
   - Store the base64 string for the LLM API call.

2. **LLM Call:**
   - Model: `gpt-4o`
   - Use OpenAI's chat completions API with `response_format: { type: "json_object" }`
   - Pass the document image as a base64 image content part
   - System prompt + user prompt (see below)

3. **Response Parsing:**
   - Parse the JSON response into `ExtractionResult`
   - If parsing fails, retry once with a stricter prompt
   - Track token usage and latency

4. **Low-Confidence Fallback:**
   - After parsing, check confidence scores
   - If >50% of fields have confidence < 0.5, apply image preprocessing:
     - Convert to grayscale
     - Increase contrast (Pillow `ImageEnhance.Contrast` factor 1.5)
     - Apply mild sharpening
   - Retry extraction with the preprocessed image
   - Return the better result (higher average confidence)

#### Extraction Prompt

```
SYSTEM PROMPT:
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
   - 0.0: Field is not present in the document

USER PROMPT:
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
    },
    // ... repeat for all required fields:
    // consignee_name, hs_code, port_of_loading, port_of_discharge,
    // incoterms, description_of_goods, gross_weight, invoice_number,
    // shipper_name, vessel_name, container_number
  ]
}

Do not include any text outside the JSON object.
```

#### Function Signature

```python
async def extract_document(
    file_path: str,
    model: str = "gpt-4o",
    retry_with_preprocessing: bool = True
) -> ExtractionResult:
    """
    1. Preprocess document (PDF → image or load image)
    2. Encode as base64
    3. Call GPT-4o vision with structured output prompt
    4. Parse response into ExtractionResult
    5. If low confidence, preprocess and retry
    6. Return ExtractionResult with timing + cost metadata
    """
```

---

## 5. Agent B: Validator Agent

### `backend/agents/validator.py`

**Responsibility:** Takes the extracted fields + a customer-specific rule set, and produces a field-by-field validation result.

#### Implementation Details

```python
"""
Validator Agent

Input: ExtractionResult + CustomerRuleSet (JSON)
Output: ValidationResult with per-field match/mismatch/uncertain

Model: GPT-4o-mini (structured output)

Validation Logic:
  - For each rule in the customer's rule set, compare against extracted value
  - Match: values are equivalent (case-insensitive, trimmed)
  - Mismatch: values differ AND extraction confidence was >= 0.6
  - Uncertain: extraction confidence < 0.6 OR the match is ambiguous
"""
```

#### Customer Rule Set Format

```python
# backend/rules/customer_rules.py

CUSTOMER_RULES = {
    "CUSTOMER_001": {
        "customer_name": "Acme Global Trading Ltd.",
        "rules": {
            "consignee_name": {
                "expected": "Acme Global Trading Ltd.",
                "match_type": "fuzzy",  # "exact" | "fuzzy" | "contains" | "regex"
                "fuzzy_threshold": 0.85,
                "required": True
            },
            "hs_code": {
                "expected_pattern": r"^\d{6,8}$",
                "match_type": "regex",
                "required": True,
                "allowed_values": ["61091000", "61099090", "62034200"]
            },
            "port_of_discharge": {
                "expected": "USLAX",
                "match_type": "exact",
                "required": True,
                "alternatives": ["Los Angeles", "LA", "USLAX", "US LAX"]
            },
            "port_of_loading": {
                "expected": "INNSA",
                "match_type": "exact",
                "required": True,
                "alternatives": ["Nhava Sheva", "JNPT", "INNSA", "IN NSA"]
            },
            "incoterms": {
                "expected": "FOB",
                "match_type": "exact",
                "required": True,
                "allowed_values": ["FOB", "CIF", "CFR", "EXW", "DDP"]
            },
            "gross_weight": {
                "match_type": "presence",  # just check it's present and numeric
                "required": True
            },
            "invoice_number": {
                "match_type": "presence",
                "required": True
            },
            "description_of_goods": {
                "match_type": "presence",
                "required": True
            }
        }
    }
}
```

#### Core Logic

The Validator Agent uses a **hybrid approach**: deterministic rule matching for simple checks + LLM for fuzzy matching and ambiguous cases.

1. **Deterministic checks (no LLM needed):**
   - `exact`: case-insensitive string comparison with trimming
   - `regex`: pattern matching
   - `presence`: check if value is not null and not empty
   - `contains`: check if expected is a substring of extracted

2. **LLM-assisted checks (GPT-4o-mini):**
   - `fuzzy`: send both values to the LLM and ask "Are these referring to the same entity?" with the context of what the field is. Returns match/mismatch with confidence.
   - This handles cases like "ACME Corp." vs "Acme Corporation Ltd." or "Los Angeles" vs "USLAX"

3. **Uncertainty handling:**
   - If the extraction confidence for a field was < 0.6, mark it `uncertain` regardless of the rule check
   - If the LLM fuzzy match confidence is between 0.5 and 0.8, mark it `uncertain`
   - Uncertain fields are NEVER treated as matches

#### Validation Prompt (for fuzzy matching only)

```
SYSTEM PROMPT:
You are a field validation agent for trade documents. You compare extracted
field values against expected customer requirements.

USER PROMPT:
Compare these two values for the field "{field_name}":
- Extracted from document: "{extracted_value}"
- Expected by customer: "{expected_value}"

Context: This is a {field_context} field on a trade document.
Are these values referring to the same thing?

Return JSON:
{
  "match": true | false,
  "confidence": <0.0 to 1.0>,
  "reason": "<brief explanation>"
}
```

#### Function Signature

```python
async def validate_extraction(
    extraction: ExtractionResult,
    customer_id: str,
    model: str = "gpt-4o-mini"
) -> ValidationResult:
    """
    1. Load customer rule set
    2. For each field in the rule set:
       a. Get extracted value from ExtractionResult
       b. If match_type is deterministic, apply rule directly
       c. If match_type is fuzzy, call LLM for comparison
       d. Apply confidence thresholds for uncertainty
    3. Compute overall_score = matched_fields / total_required_fields
    4. Return ValidationResult with all field results
    """
```

---

## 6. Agent C: Router / Decision Agent

### `backend/agents/router.py`

**Responsibility:** Reads the validation result and decides: auto-approve, flag for human review, or draft an amendment request. Must explain its reasoning.

#### Decision Logic (Deterministic + LLM)

The decision tree is primarily deterministic — the LLM is used only for generating the reasoning text and the amendment email draft.

```
IF validation has ANY mismatch:
    → decision = REQUEST_AMENDMENT
    → generate amendment email draft listing all discrepancies
    
ELIF validation has ANY uncertain fields:
    → decision = FLAG_FOR_REVIEW
    → reasoning = "X fields could not be validated with sufficient confidence"
    
ELIF overall_score >= 0.95 AND no uncertain fields AND no mismatches:
    → decision = AUTO_APPROVE
    → reasoning = "All fields validated successfully against customer requirements"
    
ELSE:
    → decision = FLAG_FOR_REVIEW
    → reasoning = "Validation score below auto-approval threshold"
```

#### Amendment Email Prompt

```
SYSTEM PROMPT:
You are a trade document amendment request drafter. You generate professional,
clear amendment emails that a CG (Cargo/Control Group) operator can send to
a Shipping Unit (SU) listing all document discrepancies that need correction.

USER PROMPT:
Draft an amendment request email for the following discrepancies found in
shipment document {document_id}:

Discrepancies:
{for each mismatch:}
- Field: {field_name}
  Found in document: {extracted_value}
  Expected by customer: {expected_value}

Requirements:
1. Be professional but direct
2. List EVERY discrepancy with the field name, what was found, and what is expected
3. Ask the SU to correct and resubmit
4. Keep it under 200 words
5. Do NOT include pleasantries beyond a greeting and sign-off

Format as a plain email body (no subject line — that will be added separately).
```

#### Function Signature

```python
async def route_decision(
    validation: ValidationResult,
    extraction: ExtractionResult,
    customer_id: str,
    model: str = "gpt-4o-mini"
) -> RouterResult:
    """
    1. Apply deterministic decision tree
    2. If REQUEST_AMENDMENT:
       a. Collect all mismatches into discrepancy list
       b. Call LLM to generate amendment email draft
    3. If FLAG_FOR_REVIEW:
       a. Generate reasoning string listing uncertain fields
    4. If AUTO_APPROVE:
       a. Generate simple approval reasoning
    5. Return RouterResult with decision, reasoning, draft email (if applicable)
    """
```

---

## 7. Pipeline Orchestrator (LangGraph)

### `backend/pipeline/orchestrator.py`

**Responsibility:** Define and execute the three-agent pipeline as a LangGraph StateGraph.

#### State Definition (`backend/pipeline/state.py`)

```python
from typing import TypedDict, Optional, Annotated
from models.schemas import (
    ExtractionResult, ValidationResult, RouterResult, PipelineStatus
)

class PipelineGraphState(TypedDict):
    # Input
    shipment_id: str
    document_id: str
    document_path: str
    customer_id: str
    run_id: str
    
    # Pipeline tracking
    status: PipelineStatus
    retry_count: int
    error_log: list[str]
    
    # Agent outputs (populated as pipeline progresses)
    extraction_result: Optional[ExtractionResult]
    validation_result: Optional[ValidationResult]
    routing_result: Optional[RouterResult]
    
    # Metrics
    total_cost_usd: float
    total_latency_ms: int
```

#### Graph Definition

```python
from langgraph.graph import StateGraph, END

def build_pipeline() -> StateGraph:
    """
    Build the LangGraph pipeline:
    
    START → extract_node → check_extraction → validate_node → route_node → store_node → END
                              ↓ (if failed)
                          error_node → END
    """
    graph = StateGraph(PipelineGraphState)
    
    # Add nodes
    graph.add_node("extract", extract_node)
    graph.add_node("check_extraction", check_extraction_quality)
    graph.add_node("validate", validate_node)
    graph.add_node("route", route_node)
    graph.add_node("store", store_node)
    graph.add_node("error", error_node)
    
    # Add edges
    graph.set_entry_point("extract")
    graph.add_edge("extract", "check_extraction")
    
    # Conditional: if extraction quality is too low, go to error
    graph.add_conditional_edges(
        "check_extraction",
        extraction_quality_gate,
        {
            "pass": "validate",
            "fail": "error"
        }
    )
    
    graph.add_edge("validate", "route")
    graph.add_edge("route", "store")
    graph.add_edge("store", END)
    graph.add_edge("error", END)
    
    return graph.compile()
```

#### Node Implementations

Each node is an async function that:
1. Updates state `status` to its phase
2. Calls the corresponding agent
3. Updates state with the result
4. Handles errors with retry logic

```python
async def extract_node(state: PipelineGraphState) -> PipelineGraphState:
    """Call Extractor Agent, update state with result"""
    state["status"] = "extracting"
    try:
        result = await extract_document(state["document_path"])
        state["extraction_result"] = result
        state["total_cost_usd"] += calculate_cost(result.token_usage)
        state["total_latency_ms"] += result.extraction_time_ms
    except Exception as e:
        state["error_log"].append(f"Extraction error: {str(e)}")
        state["retry_count"] += 1
        if state["retry_count"] >= 3:
            state["status"] = "error"
    return state

def extraction_quality_gate(state: PipelineGraphState) -> str:
    """Check if extraction quality is sufficient to proceed"""
    if state.get("status") == "error":
        return "fail"
    result = state.get("extraction_result")
    if not result:
        return "fail"
    # If >50% fields are null or <0.5 confidence, fail
    low_conf_count = sum(1 for f in result.fields if f.confidence < 0.5)
    if low_conf_count > len(result.fields) * 0.5:
        state["error_log"].append("Extraction quality too low — majority of fields below confidence threshold")
        return "fail"
    return "pass"

async def validate_node(state: PipelineGraphState) -> PipelineGraphState:
    """Call Validator Agent"""
    state["status"] = "validating"
    try:
        result = await validate_extraction(
            state["extraction_result"],
            state["customer_id"]
        )
        state["validation_result"] = result
        state["total_cost_usd"] += calculate_cost(result.token_usage)
        state["total_latency_ms"] += result.validation_time_ms
    except Exception as e:
        state["error_log"].append(f"Validation error: {str(e)}")
        state["status"] = "error"
    return state

async def route_node(state: PipelineGraphState) -> PipelineGraphState:
    """Call Router Agent"""
    state["status"] = "routing"
    try:
        result = await route_decision(
            state["validation_result"],
            state["extraction_result"],
            state["customer_id"]
        )
        state["routing_result"] = result
        state["total_cost_usd"] += calculate_cost(result.token_usage)
        state["total_latency_ms"] += result.routing_time_ms
    except Exception as e:
        state["error_log"].append(f"Routing error: {str(e)}")
        state["status"] = "error"
    return state

async def store_node(state: PipelineGraphState) -> PipelineGraphState:
    """Persist final result to SQLite"""
    state["status"] = "complete"
    await save_pipeline_result(state)  # defined in database.py
    return state

async def error_node(state: PipelineGraphState) -> PipelineGraphState:
    """Handle pipeline errors"""
    state["status"] = "error"
    await save_pipeline_result(state)
    return state
```

#### Running the Pipeline

```python
async def run_pipeline(
    document_path: str,
    customer_id: str,
    shipment_id: str = None,
) -> PipelineGraphState:
    """
    Execute the full pipeline on a single document.
    Returns the final state with all agent outputs.
    """
    import uuid
    
    pipeline = build_pipeline()
    
    initial_state: PipelineGraphState = {
        "shipment_id": shipment_id or str(uuid.uuid4())[:8],
        "document_id": str(uuid.uuid4())[:8],
        "document_path": document_path,
        "customer_id": customer_id,
        "run_id": str(uuid.uuid4()),
        "status": "pending",
        "retry_count": 0,
        "error_log": [],
        "extraction_result": None,
        "validation_result": None,
        "routing_result": None,
        "total_cost_usd": 0.0,
        "total_latency_ms": 0,
    }
    
    # Execute with timeout
    result = await asyncio.wait_for(
        pipeline.ainvoke(initial_state),
        timeout=60  # 60 second global timeout
    )
    
    return result
```

---

## 8. Storage Layer (SQLite)

### `backend/models/database.py`

**Responsibility:** Persist all pipeline results to SQLite for querying.

#### Schema

```sql
CREATE TABLE IF NOT EXISTS shipments (
    id TEXT PRIMARY KEY,
    shipment_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    document_type TEXT,
    customer_id TEXT NOT NULL,
    status TEXT NOT NULL,  -- pending, extracting, validating, routing, complete, error
    decision TEXT,  -- auto_approve, flag_for_review, request_amendment
    decision_reasoning TEXT,
    amendment_draft TEXT,
    overall_validation_score REAL,
    total_cost_usd REAL,
    total_latency_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    run_id TEXT
);

CREATE TABLE IF NOT EXISTS extracted_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    extracted_value TEXT,
    confidence REAL,
    source_location TEXT,
    FOREIGN KEY (document_id) REFERENCES shipments(document_id)
);

CREATE TABLE IF NOT EXISTS validation_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    status TEXT NOT NULL,  -- match, mismatch, uncertain, not_applicable
    extracted_value TEXT,
    expected_value TEXT,
    reason TEXT,
    confidence REAL,
    FOREIGN KEY (document_id) REFERENCES shipments(document_id)
);

CREATE TABLE IF NOT EXISTS pipeline_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES shipments(document_id)
);
```

#### Database Operations

```python
import sqlite3
import json
from contextlib import contextmanager

DATABASE_PATH = "./data/trade_docs.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    """Create tables if they don't exist. Call once on startup."""
    with get_db() as conn:
        conn.executescript(SCHEMA_SQL)

async def save_pipeline_result(state: dict):
    """
    Persist the full pipeline state to SQLite.
    Inserts into shipments, extracted_fields, and validation_results tables.
    """
    with get_db() as conn:
        # 1. Insert shipment record
        conn.execute("""
            INSERT OR REPLACE INTO shipments 
            (id, shipment_id, document_id, document_type, customer_id, status, 
             decision, decision_reasoning, amendment_draft, overall_validation_score,
             total_cost_usd, total_latency_ms, run_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (...))  # map from state dict
        
        # 2. Insert extracted fields
        if state.get("extraction_result"):
            for field in state["extraction_result"].fields:
                conn.execute("""
                    INSERT INTO extracted_fields (document_id, field_name, extracted_value, confidence, source_location)
                    VALUES (?, ?, ?, ?, ?)
                """, (state["document_id"], field.field_name, field.value, field.confidence, field.source_location))
        
        # 3. Insert validation results
        if state.get("validation_result"):
            for result in state["validation_result"].field_results:
                conn.execute("""
                    INSERT INTO validation_results (document_id, field_name, status, extracted_value, expected_value, reason, confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (state["document_id"], result.field_name, result.status.value, result.extracted_value, result.expected_value, result.reason, result.confidence))

def query_db(sql: str) -> list[dict]:
    """Execute a read-only SQL query and return results as list of dicts."""
    with get_db() as conn:
        cursor = conn.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
```

---

## 9. Query Layer (Natural Language → SQL)

### `backend/agents/query_agent.py`

**Responsibility:** Take a natural-language question from a non-engineer and convert it to SQL, execute it, and return a grounded answer.

#### Implementation

```python
"""
Query Agent

Input: Natural language question (string)
Output: QueryResponse with the SQL generated, raw results, and a human-readable answer

Model: GPT-4o-mini

Safety: 
  - Only SELECT queries are allowed. 
  - The LLM generates the SQL, but the application validates it before execution.
  - If the SQL contains INSERT/UPDATE/DELETE/DROP/ALTER, it is rejected.
"""
```

#### Query Prompt

```
SYSTEM PROMPT:
You are a SQL query generator for a trade document validation database.
You translate natural language questions into SQLite-compatible SELECT queries.

The database has these tables:

1. shipments (id, shipment_id, document_id, document_type, customer_id, status, 
   decision, decision_reasoning, amendment_draft, overall_validation_score, 
   total_cost_usd, total_latency_ms, created_at, updated_at, run_id)
   
2. extracted_fields (id, document_id, field_name, extracted_value, confidence, source_location)

3. validation_results (id, document_id, field_name, status, extracted_value, 
   expected_value, reason, confidence)

Field `status` in validation_results can be: 'match', 'mismatch', 'uncertain', 'not_applicable'
Field `decision` in shipments can be: 'auto_approve', 'flag_for_review', 'request_amendment'
Field `status` in shipments can be: 'pending', 'extracting', 'validating', 'routing', 'complete', 'error'

RULES:
1. Generate ONLY SELECT queries. No INSERT, UPDATE, DELETE, DROP, ALTER.
2. Always use proper table aliases.
3. For time-based queries, use SQLite date functions.
4. Return ONLY the SQL query, no explanation.

USER PROMPT:
Question: {user_question}

Generate the SQL query:
```

#### Function Signature

```python
async def answer_question(question: str) -> QueryResponse:
    """
    1. Send question to LLM to generate SQL
    2. Validate SQL (only SELECT allowed)
    3. Execute SQL against SQLite
    4. Send results + original question back to LLM to generate human-readable answer
    5. Return QueryResponse with sql, answer, and raw rows
    """
```

#### Answer Generation Prompt

```
Given this question: "{question}"
And these query results: {json_results}

Provide a clear, concise answer to the question based on the data.
If the results are empty, say so clearly. Do not make up data.
Keep the answer under 3 sentences.
```

---

## 10. Minimal UI (React Frontend)

### Design Requirements

The UI must show the pipeline running on ONE document with these visible states:
1. Upload a document → select customer
2. Pipeline progress (extracting → validating → routing)
3. Extracted fields with per-field confidence scores
4. Validation results (match/mismatch/uncertain per field)
5. Routing decision + reasoning
6. Amendment draft (if applicable)
7. Natural language query interface

### Component Breakdown

#### `App.jsx` — Main Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Trade Document Validator — Nova Pipeline POC                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────┐  ┌──────────────────────────────────┐ │
│  │   Document Upload    │  │    Pipeline Status               │ │
│  │   [Choose File]      │  │    ● Extracting... (3.2s)        │ │
│  │   Customer: [▼ CUST] │  │    ○ Validating                  │ │
│  │   [Run Pipeline]     │  │    ○ Routing                     │ │
│  └──────────────────────┘  └──────────────────────────────────┘ │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │  Extraction Results                                          ││
│  │  ┌─────────────────┬──────────────────┬────────────┐        ││
│  │  │ Field           │ Value            │ Confidence │        ││
│  │  ├─────────────────┼──────────────────┼────────────┤        ││
│  │  │ consignee_name  │ Acme Corp.       │ ████░ 0.92 │        ││
│  │  │ hs_code         │ 61091000         │ █████ 0.98 │        ││
│  │  │ port_of_loading │ INNSA            │ █████ 0.95 │        ││
│  │  │ gross_weight    │ 1,250 KG         │ ███░░ 0.71 │        ││
│  │  └─────────────────┴──────────────────┴────────────┘        ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                 │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │  Validation Results                                          ││
│  │  ┌─────────────────┬────────┬──────────┬──────────┐         ││
│  │  │ Field           │ Status │ Found    │ Expected │         ││
│  │  ├─────────────────┼────────┼──────────┼──────────┤         ││
│  │  │ consignee_name  │ ❌ MIS │ Acme Corp│ Acme Glo │         ││
│  │  │ hs_code         │ ✅ OK  │ 61091000 │ 61091000 │         ││
│  │  │ port_of_loading │ ✅ OK  │ INNSA    │ INNSA    │         ││
│  │  │ gross_weight    │ ⚠️ UNC │ 1,250 KG │ --       │         ││
│  │  └─────────────────┴────────┴──────────┴──────────┘         ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                 │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │  Decision: REQUEST AMENDMENT                                 ││
│  │  Reasoning: 1 field mismatch detected (consignee_name).      ││
│  │             1 field uncertain (gross_weight).                 ││
│  │                                                              ││
│  │  ┌── Draft Amendment Email ──────────────────────────────┐   ││
│  │  │ Dear Shipping Unit,                                    │   ││
│  │  │                                                        │   ││
│  │  │ We have reviewed the submitted trade documents and     │   ││
│  │  │ found the following discrepancies:                     │   ││
│  │  │                                                        │   ││
│  │  │ 1. Consignee Name                                     │   ││
│  │  │    Found: "Acme Corp."                                 │   ││
│  │  │    Expected: "Acme Global Trading Ltd."                │   ││
│  │  │ ...                                                    │   ││
│  │  └────────────────────────────────────────────────────────┘   ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                 │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │  Query Verified Data                                         ││
│  │  [How many shipments were flagged this week?           ] [⏎] ││
│  │                                                              ││
│  │  Answer: 3 shipments were flagged for human review this      ││
│  │  week. 2 had consignee mismatches and 1 had an uncertain     ││
│  │  HS code.                                                    ││
│  │                                                              ││
│  │  SQL: SELECT COUNT(*) FROM shipments WHERE decision =        ││
│  │  'flag_for_review' AND created_at >= date('now', '-7 days')  ││
│  └──────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### Key Components

#### `DocumentUpload.jsx`
- File input accepting `.pdf`, `.png`, `.jpg`
- Dropdown to select customer (preloaded from backend `/api/customers`)
- "Run Pipeline" button that POSTs to `/api/pipeline/run`
- Shows upload progress and file name

#### `PipelineStatus.jsx`
- Polls `/api/pipeline/status/{run_id}` every 1 second
- Shows 4-step progress: Upload → Extracting → Validating → Routing
- Each step shows elapsed time when active
- Green check when complete, red X on error

#### `ExtractionView.jsx`
- Table with columns: Field Name, Extracted Value, Confidence
- Confidence shown as a colored bar:
  - Green (≥ 0.8), Yellow (0.6–0.8), Red (< 0.6)
- Confidence numeric value shown next to bar
- Null/missing fields shown with "—" and red confidence bar

#### `ValidationView.jsx`
- Table with columns: Field, Status, Found, Expected
- Status icons: ✅ match, ❌ mismatch, ⚠️ uncertain
- Mismatch rows highlighted in light red
- Uncertain rows highlighted in light yellow
- Shows overall validation score as percentage

#### `DecisionView.jsx`
- Large banner showing decision: "AUTO-APPROVED" (green), "FLAGGED FOR REVIEW" (yellow), "AMENDMENT REQUIRED" (red)
- Reasoning text below the banner
- If amendment, shows the `AmendmentDraft` component

#### `AmendmentDraft.jsx`
- Read-only text area showing the draft amendment email
- "Copy to Clipboard" button

#### `QueryInterface.jsx`
- Text input for natural language query
- Submit button
- Shows the answer in a card
- Expandable "Show SQL" section below the answer
- Shows raw result rows in a small table

### API Integration (`hooks/usePipeline.js`)

```javascript
// Custom hook that manages pipeline state
function usePipeline() {
  const [status, setStatus] = useState('idle');      // idle | uploading | running | complete | error
  const [result, setResult] = useState(null);         // Full pipeline result
  const [runId, setRunId] = useState(null);

  async function runPipeline(file, customerId) {
    setStatus('uploading');
    const formData = new FormData();
    formData.append('file', file);
    formData.append('customer_id', customerId);
    
    const { data } = await api.post('/api/pipeline/run', formData);
    setRunId(data.run_id);
    setStatus('running');
    
    // Poll for status
    const pollInterval = setInterval(async () => {
      const { data: statusData } = await api.get(`/api/pipeline/status/${data.run_id}`);
      setResult(statusData);
      if (statusData.status === 'complete' || statusData.status === 'error') {
        clearInterval(pollInterval);
        setStatus(statusData.status);
      }
    }, 1000);
  }

  return { status, result, runPipeline };
}
```

---

## 11. Backend API (FastAPI)

### `backend/main.py`

#### Endpoints

```python
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Trade Document Validator — Nova POC")

# CORS for frontend
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
async def startup():
    init_db()

# ─── Pipeline Endpoints ───

@app.post("/api/pipeline/run")
async def run_pipeline_endpoint(
    file: UploadFile = File(...),
    customer_id: str = Form("CUSTOMER_001")
):
    """
    1. Save uploaded file to disk (./uploads/{uuid}_{filename})
    2. Start pipeline in background task
    3. Return run_id immediately
    """
    # Save file
    file_path = f"./uploads/{uuid4()}_{file.filename}"
    with open(file_path, "wb") as f:
        f.write(await file.read())
    
    # Run pipeline (in background for polling, or sync for simplicity in POC)
    # For POC: run synchronously and return result
    result = await run_pipeline(file_path, customer_id)
    
    return {
        "run_id": result["run_id"],
        "status": result["status"],
        "extraction": result.get("extraction_result"),
        "validation": result.get("validation_result"),
        "routing": result.get("routing_result"),
        "total_cost_usd": result.get("total_cost_usd"),
        "total_latency_ms": result.get("total_latency_ms"),
        "errors": result.get("error_log", [])
    }

@app.get("/api/pipeline/status/{run_id}")
async def get_pipeline_status(run_id: str):
    """Return current state of a pipeline run (for polling)."""
    # Query from SQLite by run_id
    pass

# ─── Query Endpoint ───

@app.post("/api/query")
async def query_endpoint(request: QueryRequest):
    """
    Natural language query over verified data.
    Converts question to SQL, executes, returns answer.
    """
    response = await answer_question(request.question)
    return response

# ─── Customer Endpoints ───

@app.get("/api/customers")
async def list_customers():
    """Return list of available customer IDs and names (from rules config)."""
    return [
        {"id": "CUSTOMER_001", "name": "Acme Global Trading Ltd."},
    ]

# ─── Health ───

@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

---

## 12. Sample Data & Customer Rules

### Sample Documents to Create

Create two sample trade documents for testing:

#### 1. Clean Bill of Lading (`sample_docs/clean_bill_of_lading.pdf`)

Create a simple PDF with clearly readable fields:
- Shipper: "Rajesh Textiles Pvt. Ltd."
- Consignee: "Acme Global Trading Ltd."
- HS Code: "61091000"
- Port of Loading: "INNSA" (Nhava Sheva)
- Port of Discharge: "USLAX" (Los Angeles)
- Incoterms: "FOB"
- Description of Goods: "Men's cotton t-shirts, assorted colors, S/M/L"
- Gross Weight: "1,250 KG"
- Invoice Number: "INV-2024-0847"
- Vessel: "MSC OSCAR"
- Container: "MSCU1234567"

This document should PASS all validation rules for CUSTOMER_001.

#### 2. Messy Commercial Invoice (`sample_docs/messy_commercial_invoice.png`)

Create a lower-quality image (slightly rotated, lower resolution) with deliberate mismatches:
- Consignee: "Acme Corp." (MISMATCH — should be "Acme Global Trading Ltd.")
- HS Code: "6109" (MISMATCH — too short, should be 8 digits)
- Port of Discharge: "USLGB" (MISMATCH — wrong port)
- Incoterms: "CIF" (MISMATCH — should be "FOB" for this customer)
- Other fields correct

This document should FAIL validation and trigger an amendment request.

### Customer Rule Set

Defined in `backend/rules/customer_rules.py` as shown in Section 5 above. One customer (`CUSTOMER_001`) with rules for all 8 required fields.

---

## 13. Error Handling & Observability

### Error Handling Strategy

| Error Type | Handling | User Feedback |
|------------|----------|---------------|
| LLM API timeout | Retry up to 3x with exponential backoff (2s, 4s, 8s) | "Extraction is taking longer than usual, retrying..." |
| LLM returns unparseable JSON | Retry once with stricter prompt ("Return ONLY valid JSON") | "Processing document..." (transparent retry) |
| Document unreadable (all fields null) | Mark as error, skip to error_node | "Could not read this document. Please upload a clearer version." |
| Cost exceeds $0.50 per doc | Kill pipeline, mark as error | "Processing exceeded cost limits. Document flagged for manual review." |
| Database write fails | Log error, return result without persistence | "Results displayed but could not be saved. Please try again." |
| File upload fails | Return 400 immediately | "Could not read the uploaded file. Supported formats: PDF, PNG, JPG." |

### Logging

Every agent call logs:
```python
logger.info(f"[{run_id}] Agent={agent_name} | Model={model} | "
            f"Latency={latency_ms}ms | Tokens_in={input_tokens} | "
            f"Tokens_out={output_tokens} | Cost=${cost:.4f}")
```

### Cost Tracking

```python
# utils/llm_client.py

COST_TABLE = {
    "gpt-4o": {"input": 2.50 / 1_000_000, "output": 10.00 / 1_000_000},
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
}

def calculate_cost(token_usage: dict, model: str) -> float:
    rates = COST_TABLE.get(model, COST_TABLE["gpt-4o-mini"])
    return (token_usage["input"] * rates["input"]) + (token_usage["output"] * rates["output"])
```

---

## 14. How to Run

### Setup

```bash
# Clone and enter project
cd trade-doc-validator

# Backend setup
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# Initialize database
python -c "from models.database import init_db; init_db()"

# Start backend
uvicorn main:app --reload --port 8000

# Frontend setup (new terminal)
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

### Quick Test (CLI)

```bash
# Test the pipeline without the UI
cd backend
python -c "
import asyncio
from pipeline.orchestrator import run_pipeline

result = asyncio.run(run_pipeline(
    document_path='sample_docs/clean_bill_of_lading.pdf',
    customer_id='CUSTOMER_001'
))
print(f'Status: {result[\"status\"]}')
print(f'Decision: {result[\"routing_result\"].decision}')
print(f'Cost: ${result[\"total_cost_usd\"]:.4f}')
"
```

### Sample Queries to Run

After processing at least one document, test these queries:

1. "How many shipments have been processed?"
2. "How many shipments were flagged for review?"
3. "Show me all mismatched fields"
4. "What was the average confidence score for consignee extraction?"
5. "Which documents had amendment requests?"
6. "What is the total processing cost today?"

---

## Architecture Diagram (Text)

```
                           ┌──────────────┐
                           │   User/UI    │
                           │  (React App) │
                           └──────┬───────┘
                                  │ POST /api/pipeline/run
                                  │ (file + customer_id)
                                  ▼
                           ┌──────────────┐
                           │   FastAPI    │
                           │   Backend   │
                           └──────┬───────┘
                                  │
                                  ▼
                    ┌─────────────────────────────┐
                    │   LangGraph Orchestrator     │
                    │   (StateGraph pipeline)      │
                    └─────────────┬───────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
     ┌─────────────┐    ┌──────────────┐    ┌──────────────┐
     │  Extractor   │    │  Validator    │    │   Router     │
     │   Agent      │    │   Agent      │    │   Agent      │
     │             │    │             │    │             │
     │ GPT-4o     │    │ GPT-4o-mini │    │ GPT-4o-mini │
     │ (vision)   │    │ + rules     │    │ + decision  │
     │             │    │             │    │   tree      │
     └──────┬──────┘    └──────┬──────┘    └──────┬──────┘
            │                  │                  │
            │ ExtractionResult │ ValidationResult │ RouterResult
            │                  │                  │
            └───────────────────┼──────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │       SQLite          │
                    │  ┌─────────────────┐  │
                    │  │ shipments       │  │
                    │  │ extracted_fields│  │
                    │  │ validation_results│ │
                    │  └─────────────────┘  │
                    └───────────┬───────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │  Query Agent          │
                    │  (NL → SQL → Answer)  │
                    │  GPT-4o-mini          │
                    └───────────────────────┘
```

### Data Flow

```
PDF/Image → [Preprocessing: render to image, base64 encode]
          → [Extractor: GPT-4o vision → structured JSON with confidence]
          → [Quality Gate: if >50% low confidence → error path]
          → [Validator: rules + GPT-4o-mini → match/mismatch/uncertain per field]
          → [Router: decision tree + GPT-4o-mini → approve/flag/amend + reasoning]
          → [Store: SQLite persist]
          → [UI: display results + draft email + query interface]
```

### State Persistence Between Agents

```
PipelineGraphState (dict) flows through each node:
  extract_node: reads document_path → writes extraction_result
  check_extraction: reads extraction_result → decides pass/fail
  validate_node: reads extraction_result + customer_id → writes validation_result
  route_node: reads validation_result + extraction_result → writes routing_result
  store_node: reads all results → writes to SQLite
  
State is persisted to SQLite at store_node (on success) or error_node (on failure).
On restart, incomplete runs can be identified by status != 'complete' and status != 'error'.
```

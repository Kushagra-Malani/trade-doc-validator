"""
main.py — FastAPI application entry point for the Trade Document Validator.

Endpoints:
  POST /api/pipeline/run     — Upload a document and run the full pipeline
  GET  /api/pipeline/status/{run_id} — Poll pipeline status by run_id
  POST /api/query             — Natural language query over verified data
  GET  /api/customers         — List available customers
  GET  /api/health            — Health check
"""

import os
import logging
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.config import DATABASE_PATH
from backend.models.database import init_db, get_db
from backend.models.schemas import QueryRequest
from backend.agents.query_agent import answer_question
from backend.pipeline.orchestrator import run_pipeline
from backend.rules.customer_rules import CUSTOMER_RULES

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ─── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(title="Trade Document Validator — Nova POC")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("./uploads")


@app.on_event("startup")
async def startup():
    """Initialise database and ensure upload directory exists."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    logger.info("Startup complete — DB at %s, uploads at %s", DATABASE_PATH, UPLOAD_DIR)


# ─── Pipeline Endpoints ─────────────────────────────────────────────────────


@app.post("/api/pipeline/run")
async def run_pipeline_endpoint(
    file: UploadFile = File(...),
    customer_id: str = Form("CUSTOMER_001"),
):
    """
    Upload a trade document and run the full validation pipeline.

    1. Save uploaded file to ./uploads/{uuid}_{filename}
    2. Execute pipeline synchronously (POC — no background task)
    3. Return complete result with all agent outputs
    """
    # Validate file type
    ext = Path(file.filename or "").suffix.lower()
    if ext not in {".pdf", ".png", ".jpg", ".jpeg"}:
        raise HTTPException(
            status_code=400,
            detail="Could not read the uploaded file. Supported formats: PDF, PNG, JPG.",
        )

    # Save file
    file_id = str(uuid4())
    file_path = UPLOAD_DIR / f"{file_id}_{file.filename}"
    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"File upload failed: {exc}")

    # Run pipeline
    try:
        result = await run_pipeline(
            document_path=str(file_path),
            customer_id=customer_id,
        )
    except Exception as exc:
        logger.exception("Pipeline failed for %s", file_path)
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}")

    # Serialise agent results — they may be Pydantic models or None
    def _serialise(obj):
        if obj is None:
            return None
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        return obj

    status_val = result.get("status", "unknown")
    if hasattr(status_val, "value"):
        status_val = status_val.value

    return {
        "run_id": result.get("run_id"),
        "status": status_val,
        "extraction": _serialise(result.get("extraction_result")),
        "validation": _serialise(result.get("validation_result")),
        "routing": _serialise(result.get("routing_result")),
        "total_cost_usd": result.get("total_cost_usd", 0.0),
        "total_latency_ms": result.get("total_latency_ms", 0),
        "errors": result.get("error_log", []),
    }


@app.get("/api/pipeline/status/{run_id}")
async def get_pipeline_status(run_id: str):
    """Return current state of a pipeline run (for polling)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM shipments WHERE run_id = ?", (run_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")

        shipment = dict(row)

        # Fetch extracted fields
        fields = conn.execute(
            "SELECT * FROM extracted_fields WHERE document_id = ?",
            (shipment["document_id"],),
        ).fetchall()

        # Fetch validation results
        validations = conn.execute(
            "SELECT * FROM validation_results WHERE document_id = ?",
            (shipment["document_id"],),
        ).fetchall()

        # Fetch errors
        errors = conn.execute(
            "SELECT error_message FROM pipeline_errors WHERE run_id = ?",
            (run_id,),
        ).fetchall()

    return {
        "run_id": run_id,
        "status": shipment.get("status"),
        "decision": shipment.get("decision"),
        "decision_reasoning": shipment.get("decision_reasoning"),
        "amendment_draft": shipment.get("amendment_draft"),
        "overall_validation_score": shipment.get("overall_validation_score"),
        "total_cost_usd": shipment.get("total_cost_usd"),
        "total_latency_ms": shipment.get("total_latency_ms"),
        "document_type": shipment.get("document_type"),
        "extraction": {
            "fields": [dict(f) for f in fields],
        },
        "validation": {
            "field_results": [dict(v) for v in validations],
        },
        "errors": [dict(e)["error_message"] for e in errors],
    }


# ─── Query Endpoint ─────────────────────────────────────────────────────────


@app.post("/api/query")
async def query_endpoint(request: QueryRequest):
    """Natural language query over verified data."""
    try:
        response = await answer_question(request.question)
        return response.model_dump()
    except Exception as exc:
        logger.exception("Query failed")
        raise HTTPException(status_code=500, detail=f"Query error: {exc}")


# ─── Customer Endpoints ─────────────────────────────────────────────────────


@app.get("/api/customers")
async def list_customers():
    """Return list of available customer IDs and names."""
    return [
        {"id": cid, "name": data["customer_name"]}
        for cid, data in CUSTOMER_RULES.items()
    ]


# ─── Health ──────────────────────────────────────────────────────────────────


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

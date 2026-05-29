"""
orchestrator.py — LangGraph pipeline for the Trade Document Validator.

Graph:
  START → extract → check_extraction ─┬─ pass → validate → route → store → END
                                       └─ fail → error → END

Each node:
  1. Updates state ``status`` to its phase.
  2. Calls the corresponding agent.
  3. Accumulates cost / latency into state metrics.
  4. Persists intermediate state to SQLite after every node.
  5. Handles errors with retry logic (max 3 retries → error node).
"""

import uuid
import asyncio
import logging

from langgraph.graph import StateGraph, END

from backend.config import MAX_RETRIES, PIPELINE_TIMEOUT_SECONDS
from backend.pipeline.state import PipelineGraphState
from backend.models.schemas import PipelineStatus
from backend.models.database import save_pipeline_result
from backend.agents.extractor import extract_document
from backend.agents.validator import validate_extraction
from backend.agents.router import route_decision
from backend.utils.llm_client import calculate_cost

logger = logging.getLogger(__name__)


# ─── Node implementations ───────────────────────────────────────────────────


async def extract_node(state: PipelineGraphState) -> PipelineGraphState:
    """Call the Extractor Agent, update state with the result."""
    state["status"] = PipelineStatus.EXTRACTING
    try:
        result = await extract_document(
            file_path=state["document_path"],
            run_id=state["run_id"],
        )
        state["extraction_result"] = result
        state["total_cost_usd"] += calculate_cost(
            result.token_usage, result.extraction_model
        )
        state["total_latency_ms"] += result.extraction_time_ms
    except Exception as exc:
        state["error_log"] = state.get("error_log", []) + [
            f"Extraction error: {exc}"
        ]
        state["retry_count"] = state.get("retry_count", 0) + 1
        if state["retry_count"] >= MAX_RETRIES:
            state["status"] = PipelineStatus.ERROR

    # Persist intermediate state for crash recovery
    try:
        await save_pipeline_result(state)
    except Exception as db_err:
        logger.warning(
            "[%s] Could not persist state after extract_node: %s",
            state["run_id"],
            db_err,
        )

    return state


def extraction_quality_gate(state: PipelineGraphState) -> str:
    """
    Conditional edge: decide whether extraction quality is good enough to
    proceed to validation or whether we should abort to the error node.

    Fail if:
      - status is already ERROR (retries exhausted), OR
      - extraction_result is None, OR
      - >50% of fields have confidence < 0.5
    """
    if state.get("status") == PipelineStatus.ERROR:
        return "fail"

    result = state.get("extraction_result")
    if not result:
        state["error_log"] = state.get("error_log", []) + [
            "Extraction produced no result."
        ]
        return "fail"

    fields = result.fields if hasattr(result, "fields") else []
    if not fields:
        state["error_log"] = state.get("error_log", []) + [
            "Extraction returned zero fields."
        ]
        return "fail"

    low_conf_count = sum(1 for f in fields if f.confidence < 0.5)
    if low_conf_count > len(fields) * 0.5:
        state["error_log"] = state.get("error_log", []) + [
            "Extraction quality too low — majority of fields below "
            f"confidence threshold ({low_conf_count}/{len(fields)} < 0.5)."
        ]
        return "fail"

    return "pass"


async def validate_node(state: PipelineGraphState) -> PipelineGraphState:
    """Call the Validator Agent."""
    state["status"] = PipelineStatus.VALIDATING
    try:
        result = await validate_extraction(
            extraction=state["extraction_result"],
            customer_id=state["customer_id"],
            run_id=state["run_id"],
        )
        state["validation_result"] = result
        state["total_cost_usd"] += calculate_cost(
            result.token_usage, result.validation_model
        )
        state["total_latency_ms"] += result.validation_time_ms
    except Exception as exc:
        state["error_log"] = state.get("error_log", []) + [
            f"Validation error: {exc}"
        ]
        state["status"] = PipelineStatus.ERROR

    # Persist intermediate state
    try:
        await save_pipeline_result(state)
    except Exception as db_err:
        logger.warning(
            "[%s] Could not persist state after validate_node: %s",
            state["run_id"],
            db_err,
        )

    return state


async def route_node(state: PipelineGraphState) -> PipelineGraphState:
    """Call the Router Agent."""
    state["status"] = PipelineStatus.ROUTING
    try:
        result = await route_decision(
            validation=state["validation_result"],
            extraction=state["extraction_result"],
            customer_id=state["customer_id"],
            run_id=state["run_id"],
        )
        state["routing_result"] = result
        state["total_cost_usd"] += calculate_cost(
            result.token_usage, result.routing_model
        )
        state["total_latency_ms"] += result.routing_time_ms
    except Exception as exc:
        state["error_log"] = state.get("error_log", []) + [
            f"Routing error: {exc}"
        ]
        state["status"] = PipelineStatus.ERROR

    # Persist intermediate state
    try:
        await save_pipeline_result(state)
    except Exception as db_err:
        logger.warning(
            "[%s] Could not persist state after route_node: %s",
            state["run_id"],
            db_err,
        )

    return state


async def store_node(state: PipelineGraphState) -> PipelineGraphState:
    """Persist final successful result to SQLite."""
    state["status"] = PipelineStatus.COMPLETE
    try:
        await save_pipeline_result(state)
    except Exception as exc:
        logger.error(
            "[%s] Failed to persist final result: %s", state["run_id"], exc
        )
        state["error_log"] = state.get("error_log", []) + [
            f"Database write error: {exc}"
        ]
    return state


async def error_node(state: PipelineGraphState) -> PipelineGraphState:
    """Handle pipeline errors — persist the error state to SQLite."""
    state["status"] = PipelineStatus.ERROR
    try:
        await save_pipeline_result(state)
    except Exception as exc:
        logger.error(
            "[%s] Failed to persist error state: %s", state["run_id"], exc
        )
    return state


# ─── Graph builder ───────────────────────────────────────────────────────────


def build_pipeline():
    """
    Build and compile the LangGraph StateGraph.

    START → extract → check_extraction ─┬─ pass → validate → route → store → END
                                         └─ fail → error → END
    """
    graph = StateGraph(PipelineGraphState)

    # Add nodes
    graph.add_node("extract", extract_node)
    graph.add_node("check_extraction", extraction_quality_gate_node)
    graph.add_node("validate", validate_node)
    graph.add_node("route", route_node)
    graph.add_node("store", store_node)
    graph.add_node("error", error_node)

    # Edges
    graph.set_entry_point("extract")
    graph.add_edge("extract", "check_extraction")

    graph.add_conditional_edges(
        "check_extraction",
        extraction_quality_gate,
        {
            "pass": "validate",
            "fail": "error",
        },
    )

    graph.add_edge("validate", "route")
    graph.add_edge("route", "store")
    graph.add_edge("store", END)
    graph.add_edge("error", END)

    return graph.compile()


async def extraction_quality_gate_node(
    state: PipelineGraphState,
) -> PipelineGraphState:
    """
    Pass-through node that sits between extract and the conditional edge.
    The actual branching logic lives in ``extraction_quality_gate()``.
    """
    return state


# ─── Pipeline runner ─────────────────────────────────────────────────────────


async def run_pipeline(
    document_path: str,
    customer_id: str,
    shipment_id: str | None = None,
) -> PipelineGraphState:
    """
    Execute the full pipeline on a single document.

    Creates the initial state, compiles the graph, and runs it with a
    60-second asyncio timeout.

    Returns the final PipelineGraphState with all agent outputs.
    """
    pipeline = build_pipeline()

    initial_state: PipelineGraphState = {
        "shipment_id": shipment_id or str(uuid.uuid4())[:8],
        "document_id": str(uuid.uuid4())[:8],
        "document_path": document_path,
        "customer_id": customer_id,
        "run_id": str(uuid.uuid4()),
        "status": PipelineStatus.PENDING,
        "retry_count": 0,
        "error_log": [],
        "extraction_result": None,
        "validation_result": None,
        "routing_result": None,
        "total_cost_usd": 0.0,
        "total_latency_ms": 0,
    }

    logger.info(
        "[%s] Pipeline started — doc=%s customer=%s",
        initial_state["run_id"],
        document_path,
        customer_id,
    )

    try:
        result = await asyncio.wait_for(
            pipeline.ainvoke(initial_state),
            timeout=PIPELINE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        initial_state["status"] = PipelineStatus.ERROR
        initial_state["error_log"].append(
            f"Pipeline timed out after {PIPELINE_TIMEOUT_SECONDS}s."
        )
        await save_pipeline_result(initial_state)
        logger.error(
            "[%s] Pipeline timed out after %ds",
            initial_state["run_id"],
            PIPELINE_TIMEOUT_SECONDS,
        )
        return initial_state

    logger.info(
        "[%s] Pipeline finished — status=%s cost=$%.4f latency=%dms",
        result.get("run_id", "?"),
        result.get("status", "?"),
        result.get("total_cost_usd", 0),
        result.get("total_latency_ms", 0),
    )

    return result

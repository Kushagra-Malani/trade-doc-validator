"""
database.py — SQLite storage layer for the Trade Document Validator.

Implements the 4-table schema from Section 8 of the architecture:
  - shipments
  - extracted_fields
  - validation_results
  - pipeline_errors

Provides:
  - init_db()                — Create tables on startup
  - get_db()                 — Context manager yielding a connection
  - save_pipeline_result()   — Persist full pipeline state to all tables
  - query_db()               — Execute read-only SQL and return list[dict]
"""

import sqlite3
import logging
from pathlib import Path
from contextlib import contextmanager

from backend.config import DATABASE_PATH

logger = logging.getLogger(__name__)

# ─── Schema SQL ──────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS shipments (
    id TEXT PRIMARY KEY,
    shipment_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    document_type TEXT,
    customer_id TEXT NOT NULL,
    status TEXT NOT NULL,
    decision TEXT,
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
    status TEXT NOT NULL,
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
"""


# ─── Connection helpers ─────────────────────────────────────────────────────


@contextmanager
def get_db():
    """
    Context manager that yields a sqlite3 Connection with row_factory set
    to sqlite3.Row.  Commits on clean exit, always closes.
    """
    # Ensure the parent directory for the database file exists
    db_path = Path(DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─── Initialisation ─────────────────────────────────────────────────────────


def init_db() -> None:
    """Create all tables if they don't already exist. Call once on startup."""
    with get_db() as conn:
        conn.executescript(SCHEMA_SQL)
    logger.info("Database initialised at %s", DATABASE_PATH)


# ─── Write operations ───────────────────────────────────────────────────────


async def save_pipeline_result(state: dict) -> None:
    """
    Persist the full pipeline state to SQLite.

    Inserts/replaces into:
      1. shipments        — one row per document run
      2. extracted_fields — one row per extracted field
      3. validation_results — one row per validated field
      4. pipeline_errors  — one row per error message
    """
    with get_db() as conn:
        # ── 1. Shipment record ───────────────────────────────────────────
        extraction = state.get("extraction_result")
        validation = state.get("validation_result")
        routing = state.get("routing_result")

        document_type = None
        if extraction:
            document_type = (
                extraction.document_type
                if hasattr(extraction, "document_type")
                else extraction.get("document_type")
            )

        decision = None
        decision_reasoning = None
        amendment_draft = None
        if routing:
            if hasattr(routing, "decision"):
                decision = routing.decision.value if hasattr(routing.decision, "value") else routing.decision
                decision_reasoning = routing.reasoning
                amendment_draft = routing.amendment_email_draft
            else:
                decision = routing.get("decision")
                decision_reasoning = routing.get("reasoning")
                amendment_draft = routing.get("amendment_email_draft")

        overall_score = None
        if validation:
            overall_score = (
                validation.overall_score
                if hasattr(validation, "overall_score")
                else validation.get("overall_score")
            )

        conn.execute(
            """
            INSERT OR REPLACE INTO shipments
            (id, shipment_id, document_id, document_type, customer_id, status,
             decision, decision_reasoning, amendment_draft, overall_validation_score,
             total_cost_usd, total_latency_ms, run_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                state["document_id"],          # id  (use document_id as PK)
                state["shipment_id"],
                state["document_id"],
                document_type,
                state["customer_id"],
                state["status"] if isinstance(state["status"], str) else state["status"].value,
                decision,
                decision_reasoning,
                amendment_draft,
                overall_score,
                state.get("total_cost_usd", 0.0),
                state.get("total_latency_ms", 0),
                state["run_id"],
            ),
        )

        # ── 2. Extracted fields ──────────────────────────────────────────
        if extraction:
            fields = (
                extraction.fields
                if hasattr(extraction, "fields")
                else extraction.get("fields", [])
            )
            for field in fields:
                if hasattr(field, "field_name"):
                    conn.execute(
                        """
                        INSERT INTO extracted_fields
                        (document_id, field_name, extracted_value, confidence, source_location)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            state["document_id"],
                            field.field_name,
                            field.value,
                            field.confidence,
                            field.source_location,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO extracted_fields
                        (document_id, field_name, extracted_value, confidence, source_location)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            state["document_id"],
                            field.get("field_name"),
                            field.get("value"),
                            field.get("confidence"),
                            field.get("source_location"),
                        ),
                    )

        # ── 3. Validation results ────────────────────────────────────────
        if validation:
            field_results = (
                validation.field_results
                if hasattr(validation, "field_results")
                else validation.get("field_results", [])
            )
            for result in field_results:
                if hasattr(result, "field_name"):
                    status_val = result.status.value if hasattr(result.status, "value") else result.status
                    conn.execute(
                        """
                        INSERT INTO validation_results
                        (document_id, field_name, status, extracted_value,
                         expected_value, reason, confidence)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            state["document_id"],
                            result.field_name,
                            status_val,
                            result.extracted_value,
                            result.expected_value,
                            result.reason,
                            result.confidence,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO validation_results
                        (document_id, field_name, status, extracted_value,
                         expected_value, reason, confidence)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            state["document_id"],
                            result.get("field_name"),
                            result.get("status"),
                            result.get("extracted_value"),
                            result.get("expected_value"),
                            result.get("reason"),
                            result.get("confidence"),
                        ),
                    )

        # ── 4. Pipeline errors ───────────────────────────────────────────
        error_log = state.get("error_log", [])
        for error_msg in error_log:
            conn.execute(
                """
                INSERT INTO pipeline_errors (document_id, run_id, error_message)
                VALUES (?, ?, ?)
                """,
                (state["document_id"], state["run_id"], error_msg),
            )

    logger.info(
        "Pipeline result saved — doc_id=%s status=%s decision=%s",
        state["document_id"],
        state["status"] if isinstance(state["status"], str) else state["status"].value,
        decision,
    )


# ─── Read operations ────────────────────────────────────────────────────────


def query_db(sql: str) -> list[dict]:
    """
    Execute a read-only SQL query and return results as a list of dicts.

    Raises ValueError if the SQL contains mutation keywords.
    """
    # Safety: reject anything that is not a SELECT
    forbidden = {"INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE"}
    upper_sql = sql.upper().strip()
    for keyword in forbidden:
        if keyword in upper_sql.split():
            raise ValueError(f"Only SELECT queries are allowed. Found forbidden keyword: {keyword}")

    with get_db() as conn:
        cursor = conn.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

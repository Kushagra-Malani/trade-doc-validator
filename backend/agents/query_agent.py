"""
Query Agent — Natural Language → SQL → Answer

Input:  Natural language question (string)
Output: QueryResponse with the SQL generated, raw results, and a human-readable answer

Model:  GPT-4o-mini

Safety:
  - Only SELECT queries are allowed.
  - The LLM generates the SQL, but the application validates it before execution.
  - If the SQL contains INSERT/UPDATE/DELETE/DROP/ALTER, it is rejected.
"""

import json
import logging

from backend.config import MODEL_QUERY
from backend.models.schemas import QueryResponse
from backend.models.database import query_db
from backend.utils.llm_client import call_llm, call_llm_json

logger = logging.getLogger(__name__)

# ─── SQL generation prompt (Section 9) ───────────────────────────────────────

SQL_SYSTEM_PROMPT = """\
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
4. Return ONLY the SQL query, no explanation."""

SQL_USER_PROMPT_TEMPLATE = """\
Question: {question}

Generate the SQL query:"""

# ─── Answer generation prompt (Section 9) ────────────────────────────────────

ANSWER_PROMPT_TEMPLATE = """\
Given this question: "{question}"
And these query results: {json_results}

Provide a clear, concise answer to the question based on the data.
If the results are empty, say so clearly. Do not make up data.
Keep the answer under 3 sentences."""

# ─── SQL validation ─────────────────────────────────────────────────────────

FORBIDDEN_KEYWORDS = {"INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE"}


def _validate_sql(sql: str) -> str:
    """
    Strip markdown fences, validate that the SQL is a SELECT query,
    and return the cleaned SQL string.

    Raises ValueError for non-SELECT or dangerous statements.
    """
    # Strip common markdown code-fence wrapping returned by LLMs
    cleaned = sql.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last fence lines
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    upper = cleaned.upper()
    for kw in FORBIDDEN_KEYWORDS:
        # Check as whole word to avoid false positives (e.g. "UPDATED_AT")
        if kw in upper.split():
            raise ValueError(
                f"SQL validation failed — forbidden keyword '{kw}' detected. "
                "Only SELECT queries are allowed."
            )

    if not upper.lstrip().startswith("SELECT"):
        raise ValueError(
            "SQL validation failed — query does not start with SELECT."
        )

    return cleaned


# ─── Main entry point ───────────────────────────────────────────────────────


async def answer_question(
    question: str,
    model: str | None = None,
    run_id: str = "unknown",
) -> QueryResponse:
    """
    Convert a natural-language question to SQL, execute it, and return a
    grounded answer.

    1. Send question to LLM to generate SQL.
    2. Validate SQL (only SELECT allowed).
    3. Execute SQL against SQLite via query_db().
    4. Send results + original question back to LLM for a human-readable answer.
    5. Return QueryResponse with sql, answer, and raw rows.
    """
    model = model or MODEL_QUERY

    # ── Step 1: Generate SQL ─────────────────────────────────────────────
    sql_messages = [
        {"role": "system", "content": SQL_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": SQL_USER_PROMPT_TEMPLATE.format(question=question),
        },
    ]

    sql_response = await call_llm(
        messages=sql_messages,
        model=model,
        run_id=run_id,
        agent_name="QueryAgent (SQL gen)",
    )
    raw_sql = sql_response["content"]

    # ── Step 2: Validate SQL ─────────────────────────────────────────────
    try:
        sql = _validate_sql(raw_sql)
    except ValueError as exc:
        logger.warning("[%s] QueryAgent — SQL rejected: %s", run_id, exc)
        return QueryResponse(
            question=question,
            sql_generated=raw_sql,
            answer=f"I could not generate a safe query for that question. {exc}",
            rows=[],
        )

    # ── Step 3: Execute SQL ──────────────────────────────────────────────
    try:
        rows = query_db(sql)
    except Exception as exc:
        logger.error("[%s] QueryAgent — SQL execution error: %s", run_id, exc)
        return QueryResponse(
            question=question,
            sql_generated=sql,
            answer=f"The query could not be executed: {exc}",
            rows=[],
        )

    # ── Step 4: Generate human-readable answer ───────────────────────────
    answer_messages = [
        {
            "role": "user",
            "content": ANSWER_PROMPT_TEMPLATE.format(
                question=question,
                json_results=json.dumps(rows, default=str),
            ),
        },
    ]

    answer_response = await call_llm(
        messages=answer_messages,
        model=model,
        run_id=run_id,
        agent_name="QueryAgent (answer gen)",
    )
    answer_text = answer_response["content"]

    logger.info(
        "[%s] QueryAgent — question='%s' rows_returned=%d",
        run_id,
        question[:80],
        len(rows),
    )

    return QueryResponse(
        question=question,
        sql_generated=sql,
        answer=answer_text,
        rows=rows,
    )

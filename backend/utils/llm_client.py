"""
llm_client.py — Centralised OpenAI client for the Trade Document Validator.

Provides:
  - call_llm()        — single entry point for all LLM calls with retry logic,
                         token counting, cost calculation, and structured logging
  - calculate_cost()  — per-call cost computation using the architecture's COST_TABLE

Retry policy: 3 retries, exponential backoff 2 s → 4 s → 8 s.
"""

import json
import time
import asyncio
import logging
from typing import Optional

import tiktoken
from openai import AsyncOpenAI, APIError, APITimeoutError, RateLimitError

from backend.config import OPENAI_API_KEY, MAX_RETRIES

logger = logging.getLogger(__name__)

# ─── OpenAI async client (singleton) ────────────────────────────────────────

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    """Lazy-initialise and return the global AsyncOpenAI client."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _client


# ─── Cost table from Section 13 (USD per token) ─────────────────────────────

COST_TABLE: dict[str, dict[str, float]] = {
    "gpt-4o": {
        "input": 2.50 / 1_000_000,
        "output": 10.00 / 1_000_000,
    },
    "gpt-4o-mini": {
        "input": 0.15 / 1_000_000,
        "output": 0.60 / 1_000_000,
    },
}


def calculate_cost(token_usage: dict, model: str) -> float:
    """
    Compute USD cost for a single LLM call.

    Args:
        token_usage: ``{"input": int, "output": int}``
        model:       model name key into COST_TABLE

    Returns:
        Cost in USD as a float.
    """
    rates = COST_TABLE.get(model, COST_TABLE["gpt-4o-mini"])
    return (
        token_usage.get("input", 0) * rates["input"]
        + token_usage.get("output", 0) * rates["output"]
    )


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """
    Count the number of tokens in *text* for the given model using tiktoken.
    Falls back to ``cl100k_base`` encoding when the model is not registered.
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


# ─── Main LLM call function ─────────────────────────────────────────────────


async def call_llm(
    messages: list[dict],
    model: str = "gpt-4o-mini",
    response_format: Optional[dict] = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    run_id: str = "unknown",
    agent_name: str = "unknown",
) -> dict:
    """
    Centralised LLM call with retry, token counting, cost tracking, and logging.

    Args:
        messages:        OpenAI chat-completion messages list.
        model:           Model to use.
        response_format: Optional ``{"type": "json_object"}`` for structured output.
        temperature:     Sampling temperature.
        max_tokens:      Maximum tokens in the completion.
        run_id:          Pipeline run identifier (for log correlation).
        agent_name:      Calling agent name (for log correlation).

    Returns:
        dict with keys:
          - content        (str)  — raw text from the model
          - token_usage    (dict) — {"input": int, "output": int}
          - cost_usd       (float)
          - latency_ms     (int)
          - model          (str)

    Raises:
        RuntimeError: if all retries are exhausted.
    """
    client = _get_client()
    backoff_seconds = [2, 4, 8]  # exponential backoff schedule

    last_error: Optional[Exception] = None

    for attempt in range(MAX_RETRIES):
        start = time.perf_counter()
        try:
            kwargs: dict = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if response_format:
                kwargs["response_format"] = response_format

            response = await client.chat.completions.create(**kwargs)
            elapsed_ms = int((time.perf_counter() - start) * 1000)

            # ── Extract usage ────────────────────────────────────────────
            usage = response.usage
            token_usage = {
                "input": usage.prompt_tokens if usage else 0,
                "output": usage.completion_tokens if usage else 0,
            }
            cost = calculate_cost(token_usage, model)
            content = response.choices[0].message.content or ""

            # ── Structured log ───────────────────────────────────────────
            logger.info(
                "[%s] Agent=%s | Model=%s | Latency=%dms | "
                "Tokens_in=%d | Tokens_out=%d | Cost=$%.4f",
                run_id,
                agent_name,
                model,
                elapsed_ms,
                token_usage["input"],
                token_usage["output"],
                cost,
            )

            return {
                "content": content,
                "token_usage": token_usage,
                "cost_usd": cost,
                "latency_ms": elapsed_ms,
                "model": model,
            }

        except (APIError, APITimeoutError, RateLimitError) as exc:
            last_error = exc
            wait = backoff_seconds[attempt] if attempt < len(backoff_seconds) else backoff_seconds[-1]
            logger.warning(
                "[%s] Agent=%s | Attempt %d/%d failed (%s). Retrying in %ds …",
                run_id,
                agent_name,
                attempt + 1,
                MAX_RETRIES,
                type(exc).__name__,
                wait,
            )
            await asyncio.sleep(wait)

        except Exception as exc:
            # Unexpected errors — don't retry
            logger.error(
                "[%s] Agent=%s | Unexpected error: %s",
                run_id,
                agent_name,
                exc,
                exc_info=True,
            )
            raise

    raise RuntimeError(
        f"[{run_id}] Agent={agent_name} — all {MAX_RETRIES} retries exhausted. "
        f"Last error: {last_error}"
    )


async def call_llm_json(
    messages: list[dict],
    model: str = "gpt-4o-mini",
    temperature: float = 0.0,
    max_tokens: int = 4096,
    run_id: str = "unknown",
    agent_name: str = "unknown",
) -> dict:
    """
    Convenience wrapper that requests JSON output and parses the response.

    Returns:
        dict with the same keys as ``call_llm`` but ``content`` is replaced
        by ``parsed`` (the parsed JSON object).  The raw string is kept as
        ``raw_content``.
    """
    result = await call_llm(
        messages=messages,
        model=model,
        response_format={"type": "json_object"},
        temperature=temperature,
        max_tokens=max_tokens,
        run_id=run_id,
        agent_name=agent_name,
    )

    try:
        parsed = json.loads(result["content"])
    except json.JSONDecodeError as exc:
        logger.error(
            "[%s] Agent=%s | Failed to parse JSON response: %s",
            run_id,
            agent_name,
            exc,
        )
        raise ValueError(f"LLM returned invalid JSON: {exc}") from exc

    result["parsed"] = parsed
    result["raw_content"] = result.pop("content")
    return result

"""
config.py — Centralized configuration for the Trade Document Validator.

Loads all environment variables using python-dotenv and exports typed constants
consumed by every module in the backend.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ─── Load .env from project root ────────────────────────────────────────────
# Walk up from backend/ to find the .env at the project root
_project_root = Path(__file__).resolve().parent.parent
_env_path = _project_root / ".env"
load_dotenv(dotenv_path=_env_path)

# ─── OpenAI ─────────────────────────────────────────────────────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

# ─── Model assignments per agent ────────────────────────────────────────────
MODEL_EXTRACTION: str = os.getenv("MODEL_EXTRACTION", "gpt-4o")
MODEL_VALIDATION: str = os.getenv("MODEL_VALIDATION", "gpt-4o-mini")
MODEL_ROUTING: str = os.getenv("MODEL_ROUTING", "gpt-4o-mini")
MODEL_QUERY: str = os.getenv("MODEL_QUERY", "gpt-4o-mini")

# ─── Database ───────────────────────────────────────────────────────────────
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "./data/trade_docs.db")

# ─── Pipeline settings ─────────────────────────────────────────────────────
MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
PIPELINE_TIMEOUT_SECONDS: int = int(os.getenv("PIPELINE_TIMEOUT_SECONDS", "60"))
COST_LIMIT_PER_DOC: float = float(os.getenv("COST_LIMIT_PER_DOC", "0.50"))

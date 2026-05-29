# Antigravity Build Instructions — Trade Document Validator POC

## What This Project Is

A multi-agent trade document validation pipeline for GoComet's Nova platform. Three AI agents work in sequence:
1. **Extractor** — reads a trade document (PDF/image) with GPT-4o vision, outputs structured JSON with confidence scores
2. **Validator** — compares extracted fields against customer-specific rules, produces match/mismatch/uncertain per field
3. **Router** — decides auto-approve, flag for review, or draft amendment email

Plus a **storage layer** (SQLite), **query layer** (natural language → SQL), and **minimal UI** (React).

## Architecture Reference

Read `POC_Architecture_Design.md` for the complete technical blueprint. Every file, function, data model, prompt, and interaction is specified there.

## Build Order

Follow this exact sequence. Each step should be independently testable before moving on.

### Step 1: Backend Skeleton
- Create the project structure as specified in Section 1 of the architecture
- Set up `requirements.txt`, `.env.example`, `config.py`
- Set up FastAPI app with CORS, health endpoint
- Set up SQLite database with the schema from Section 8
- **Test:** `curl http://localhost:8000/api/health` returns `{"status": "ok"}`

### Step 2: Data Models
- Implement all Pydantic models from Section 3 (`schemas.py`)
- These are the contracts between all agents — get them right first
- **Test:** Import all models, instantiate with sample data, validate serialization

### Step 3: Utilities
- `document_processor.py`: PDF → image rendering (PyMuPDF), base64 encoding, image preprocessing (Pillow contrast/sharpen)
- `llm_client.py`: Centralized OpenAI client with retry logic (3 retries, exponential backoff), token counting, cost calculation
- **Test:** Process a sample PDF into base64 image string

### Step 4: Extractor Agent
- Implement `agents/extractor.py` as specified in Section 4
- Use GPT-4o with vision, structured JSON output
- Include confidence scores for every field
- Include the low-confidence fallback (preprocess and retry)
- **Test:** Run on `sample_docs/clean_bill_of_lading.pdf`, verify all 8+ fields extracted with high confidence

### Step 5: Customer Rules
- Implement `rules/customer_rules.py` as specified in Section 5
- Define CUSTOMER_001 with rules for all required fields
- Support match types: exact, fuzzy, regex, presence, contains
- **Test:** Import rules, verify structure

### Step 6: Validator Agent
- Implement `agents/validator.py` as specified in Section 5
- Hybrid approach: deterministic matching for simple rules + LLM for fuzzy matching
- Uncertainty handling: extraction confidence < 0.6 → uncertain, never silent approval
- **Test:** Run on extraction output from Step 4, verify match/mismatch/uncertain results

### Step 7: Router Agent
- Implement `agents/router.py` as specified in Section 6
- Deterministic decision tree + LLM for amendment email drafting
- Generate clear, professional amendment emails listing every discrepancy
- **Test:** Run on validation output from Step 6, verify correct decision + reasoning

### Step 8: LangGraph Pipeline
- Implement `pipeline/state.py` and `pipeline/orchestrator.py` as specified in Section 7
- Wire up: extract → check_extraction → validate → route → store
- Include quality gate (conditional edge after extraction)
- Include error node path
- Global 60-second timeout
- **Test:** Run full pipeline on both sample documents via CLI

### Step 9: Storage Layer
- Implement `models/database.py` with all CRUD operations from Section 8
- `save_pipeline_result()` persists to all 3 tables
- `query_db()` executes read-only SQL
- **Test:** After pipeline run, query SQLite and verify data is persisted

### Step 10: Query Agent
- Implement `agents/query_agent.py` as specified in Section 9
- NL → SQL with GPT-4o-mini, SQL validation (SELECT only), execute, answer generation
- **Test:** Ask "How many shipments have been processed?" and get a correct answer

### Step 11: API Endpoints
- Wire up all FastAPI endpoints from Section 11
- `/api/pipeline/run` — file upload + run pipeline
- `/api/pipeline/status/{run_id}` — get status
- `/api/query` — natural language query
- `/api/customers` — list customers
- **Test:** Full pipeline via API calls (curl or Postman)

### Step 12: React Frontend
- Build all components from Section 10
- `DocumentUpload` → `PipelineStatus` → `ExtractionView` → `ValidationView` → `DecisionView` → `QueryInterface`
- Confidence bars with color coding (green/yellow/red)
- Validation status icons (✅❌⚠️)
- Decision banner with color coding
- Amendment draft display
- **Test:** Upload document through UI, see full pipeline results

### Step 13: Sample Documents
- Create or source 2 sample trade documents:
  1. A clean Bill of Lading PDF that passes all CUSTOMER_001 rules
  2. A messy/low-quality Commercial Invoice image with deliberate mismatches
- Use reportlab or similar to generate the clean PDF if real samples aren't available
- **Test:** Both documents produce expected pipeline outcomes

### Step 14: README
- Clear setup instructions (copy from Section 14 of architecture)
- How to run backend + frontend
- How to test via CLI
- Sample queries to try
- **Test:** A fresh laptop can follow the README and get the system running

## Critical Rules for the Build

1. **Never silently approve uncertain fields.** If extraction confidence is low or validation is ambiguous, the system MUST surface this. This is the #1 trust requirement.

2. **Each agent writes only its own output section** of PipelineGraphState. No agent mutates another agent's output.

3. **The Router's amendment email must be specific.** Not "some fields don't match" — it must list field name, found value, expected value for every discrepancy.

4. **Confidence scores are mandatory** on every extracted field. A field without a confidence score is a bug.

5. **The query layer only executes SELECT queries.** Validate generated SQL before execution. Reject anything that modifies data.

6. **Cost tracking is per-run.** Every LLM call logs its token usage and cost. The total cost per document is displayed in the UI.

7. **The UI doesn't need to be pretty. It needs to be real.** Show actual data from actual pipeline runs, not mock data.

## Tech Decisions — Do Not Change These

| Choice | Why |
|--------|-----|
| GPT-4o for extraction | Best vision model for document understanding |
| GPT-4o-mini for validation/routing/query | Cost-efficient for non-vision tasks |
| LangGraph for orchestration | Graph-based pipeline with conditional routing |
| SQLite for storage | Zero-config, portable, sufficient for POC |
| FastAPI for backend | Async, fast, Pydantic-native |
| React for frontend | Standard, fast to build |
| Structured JSON output | Reliable parsing between agents |

## Environment

- Python 3.11+
- Node.js 18+
- OpenAI API key with GPT-4o and GPT-4o-mini access
- No Docker needed for POC
- Must run on a standard laptop

## What Success Looks Like

Upload a trade document → see fields extracted with confidence → see validation results → see decision with reasoning → see amendment draft if applicable → query the stored data with natural language. All five behaviors (A through E from the assignment) working end-to-end on real input.

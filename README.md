# Trade Document Validator — Nova POC

Multi-agent trade document validation pipeline for GoComet's Nova platform.
Three AI agents work in sequence to extract, validate, and route trade documents.

## Architecture

```
PDF/Image → Extractor (GPT-4o vision) → Validator (rules + GPT-4o-mini) → Router (decision tree + GPT-4o-mini) → SQLite
```

| Agent     | Model        | Purpose                                    |
|-----------|--------------|--------------------------------------------|
| Extractor | GPT-4o       | Vision-based field extraction with confidence scores |
| Validator | GPT-4o-mini  | Rule-based + fuzzy field validation        |
| Router    | GPT-4o-mini  | Decision tree + amendment email drafting    |
| Query     | GPT-4o-mini  | Natural language → SQL → answer            |

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- OpenAI API key with GPT-4o and GPT-4o-mini access

### Backend

```bash
# From the project root
pip install -r requirements.txt

# Create .env from template
copy .env.example .env
# Edit .env and add your OPENAI_API_KEY

# Start backend
uvicorn backend.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

### Both at once (Windows)

```bash
# Terminal 1: Backend
uvicorn backend.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend
npm run dev
```

## Usage

1. Open http://localhost:5173
2. Upload a trade document (PDF, PNG, or JPG)
3. Select a customer (default: CUSTOMER_001 — Acme Global Trading Ltd.)
4. Click "Run Pipeline"
5. View results: extraction → validation → routing decision
6. Query stored data using natural language

## API Endpoints

| Method | Endpoint                    | Description                      |
|--------|-----------------------------|----------------------------------|
| POST   | `/api/pipeline/run`         | Upload file + run pipeline       |
| GET    | `/api/pipeline/status/{id}` | Poll pipeline status             |
| POST   | `/api/query`                | Natural language query            |
| GET    | `/api/customers`            | List available customers         |
| GET    | `/api/health`               | Health check                     |

## Sample Queries

After processing at least one document:

- "How many shipments have been processed?"
- "How many shipments were flagged for review?"
- "Show me all mismatched fields"
- "What was the average confidence score for consignee extraction?"
- "Which documents had amendment requests?"
- "What is the total processing cost today?"

## Quick CLI Test

```bash
python -c "
import asyncio
from backend.pipeline.orchestrator import run_pipeline

result = asyncio.run(run_pipeline(
    document_path='backend/sample_docs/clean_bill_of_lading.pdf',
    customer_id='CUSTOMER_001'
))
print(f'Status: {result[\"status\"]}')
print(f'Cost: ${result[\"total_cost_usd\"]:.4f}')
"
```

## Project Structure

```
trade-doc-validator/
├── backend/
│   ├── main.py                    # FastAPI entry point
│   ├── config.py                  # Environment config
│   ├── models/
│   │   ├── schemas.py             # Pydantic data models
│   │   └── database.py            # SQLite storage layer
│   ├── agents/
│   │   ├── extractor.py           # GPT-4o vision extraction
│   │   ├── validator.py           # Rule-based + fuzzy validation
│   │   ├── router.py              # Decision tree + amendment drafts
│   │   └── query_agent.py         # NL → SQL → answer
│   ├── pipeline/
│   │   ├── state.py               # LangGraph state definition
│   │   └── orchestrator.py        # LangGraph pipeline
│   ├── rules/
│   │   └── customer_rules.py      # Customer validation rules
│   └── utils/
│       ├── llm_client.py          # OpenAI client + retry + cost
│       └── document_processor.py  # PDF/image preprocessing
├── frontend/
│   ├── src/
│   │   ├── App.jsx                # Main layout
│   │   ├── components/            # All UI components
│   │   ├── hooks/usePipeline.js   # Pipeline state hook
│   │   └── utils/api.js           # API client
│   └── index.html
├── requirements.txt
├── .env.example
└── Makefile
```

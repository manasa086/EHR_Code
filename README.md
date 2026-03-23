# EHR Clinical Data Reconciliation Engine

A full-stack application that uses AI to reconcile conflicting medication records across healthcare systems and validate patient data quality.

---

## How to Run Locally

### Backend (Python / FastAPI)

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API docs available at: http://localhost:8000/docs

### Frontend (React / Tailwind)

```bash
cd frontend
npm install
npm run dev
```

Open: http://localhost:5173

---

## Environment Variables

**backend/.env**
```
API_KEY=dev-secret-key        # sent as X-API-Key header
USE_MOCK_AI=true              # set to false to use Claude API
ANTHROPIC_API_KEY=            # your key when USE_MOCK_AI=false
```

**frontend/.env**
```
VITE_API_KEY=dev-secret-key
VITE_API_BASE=http://localhost:8000/api
```

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/reconcile/medication` | Reconcile conflicting medication records |
| POST | `/api/validate/data-quality` | Score a patient record across 4 quality dimensions |
| POST | `/api/decisions` | Record clinician approve/reject decision |
| GET  | `/api/decisions` | List all recorded decisions |
| GET  | `/health` | Health check |

All endpoints require `X-API-Key` header.

---

## LLM API Choice

**Anthropic Claude** (`claude-sonnet-4-6`)

- Chosen because Claude handles structured JSON output reliably and understands clinical reasoning context well
- The system prompt frames Claude as a clinical pharmacist / data analyst to improve reasoning quality
- Currently using rule-based mocks; switching to real Claude requires setting `USE_MOCK_AI=false` and providing `ANTHROPIC_API_KEY`

---

## Architecture Decisions & Trade-offs

**In-memory cache** — SHA256 hash of the request body. Same request never hits the AI API twice per server lifetime. Trade-off: cache resets on restart. A Redis layer would fix this for production.

**Rule-based mock** — The AI service layer (`services/ai_service.py`) is structured so mock and real implementations share the same interface. Switching from mock to Claude is a single-file change with no router changes needed.

**Source scoring** — Reconciliation ranks sources by `date × reliability_weight`. High reliability × most recent wins. This is intentional: a fresh pharmacy fill (medium reliability) should not override a same-day clinical encounter (high reliability).

**Pydantic models** — All request/response shapes are validated at the boundary. The frontend never needs to defensively parse unexpected shapes.

**Approve/Reject** — Decisions are stored in memory per-process and POSTed to `/api/decisions`. In production this would persist to a database and feed back into confidence calibration.

---

## What I'd Improve With More Time

- Wire in Claude API with structured output (tool use) for more nuanced reasoning
- Persistent storage (PostgreSQL) for decisions and audit trail
- Confidence calibration: use historical decision data to re-weight source reliability scores
- Duplicate record detection: fuzzy-match medication names across sources (e.g. "Aspirin" vs "ASA")
- Docker Compose setup for one-command startup
- Add webhook support so downstream systems can subscribe to reconciliation events

---

## Running Tests

```bash
cd backend
pytest -v
```

10 tests covering reconciliation logic and data quality scoring.

---

## Estimated Time Spent

~6 hours total: architecture planning (1h), backend + tests (2.5h), frontend (2h), README (0.5h)

# EHR Clinical Data Reconciliation Engine

A full-stack mini clinical data reconciliation engine that reconciles conflicting medication records across healthcare systems and validates patient data quality that is powered by a two-layer AI pipeline (rule-based engine + Anthropic Claude).

---

## Table of Contents

1. [How to Run Locally](#how-to-run-locally)
2. [Sample Data](#sample-data)
3. [LLM API Choice](#llm-api-choice)
4. [Key Design Decisions & Trade-offs](#key-design-decisions--trade-offs)
5. [What I'd Improve With More Time](#what-id-improve-with-more-time)
6. [Estimated Time Spent](#estimated-time-spent)

---

## How to Run Locally

### Option A — Docker (recommended, one command)

```bash
# Copy and fill in your Anthropic key
cp backend/.env.example backend/.env
# Edit backend/.env: set ANTHROPIC_API_KEY and USE_MOCK_AI=false (or leave true for mocks)

docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |

---

### Option B — Local (without Docker)

**Prerequisites:** Python 3.11+, Node 20+

**1. Backend**

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Copy and fill in your Anthropic key
cp .env.example .env            # then edit .env with your values
uvicorn main:app --reload --port 8000
```

**2. Frontend**

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

---

### Environment Variables

**`backend/.env`**

```env
API_KEY=dev-secret-key          # sent as X-API-Key header by the frontend
USE_MOCK_AI=false                # set false to call Claude API
ANTHROPIC_API_KEY=              # required when USE_MOCK_AI=false
```

**`frontend/.env`**

```env
VITE_API_KEY=dev-secret-key
VITE_API_BASE=http://localhost:8000/api
```

---

### Running Tests

```bash
cd backend
pytest -v
```

There are five test files covering the full backend:

**`test_reconcile.py`** : Tests the rule-based reconciliation fallback engine in isolation. Checks that the engine correctly picks the most recent and reliable medication source, that confidence scores always land between 0 and 1, that all five required fields are present in the response, and that `clinical_safety_check` is always `NEEDS_REVIEW` (the fallback cannot assess clinical safety across arbitrary lab names and medications, that is left entirely to Claude).

**`test_validate.py`** : Tests the rule-based data quality fallback in isolation. Verifies that implausible blood pressure values are caught, that an empty allergy list gets flagged as incomplete, that the overall score stays in the 0–100 range, that all four scoring dimensions (completeness, accuracy, timeliness, clinical_plausibility) are always present, and that a complete and recent record scores above 70.

**`test_cache.py`** : Tests the `InMemoryCache` that sits in front of every Claude API call. Confirms that stored values are returned correctly, that missing keys return `None`, that key order does not affect hash identity (so `{"a":1, "b":2}` and `{"b":2, "a":1}` hit the same slot), that different payloads get different cache slots, that `clear()` wipes everything, and that writing to an existing key overwrites it cleanly.

**`test_api_endpoints.py`** : End-to-end HTTP tests against the running FastAPI app using `TestClient`. Covers auth (missing key → 422, wrong key → 401, correct key → 200), the full request/response shape for both `/api/reconcile/medication` and `/api/validate/data-quality`, cache hit behaviour, a graceful fallback to the rule-based engine when Claude throws an exception, the decisions endpoints (record approve/reject, list all decisions), and the unauthenticated `/health` check.

**`test_claude_integration.py`** : Tests the Claude API integration layer using `AsyncMock` so no real API calls are made. Verifies that a valid Claude response is parsed and returned correctly, that confidence scores outside 0–1 are clamped, that a missing API key raises a `RuntimeError`, that malformed JSON from Claude propagates as an exception, that the public `reconcile_medication` and `validate_data_quality` functions fall back to the rule-based result on a network timeout or any unexpected exception, and that mock mode short-circuits Claude entirely.

---

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/cases` | List all patient cases |
| `POST` | `/api/cases` | Create a new case |
| `PUT` | `/api/cases/{id}` | Update a user-created case |
| `POST` | `/api/reconcile/medication` | Reconcile conflicting medication records |
| `POST` | `/api/validate/data-quality` | Score a record across 4 quality dimensions |
| `POST` | `/api/decisions` | Record a clinician approve/reject decision |
| `GET` | `/api/decisions` | List decisions (filterable by `case_id` and `type`) |
| `GET` | `/api/events` | SSE stream for real-time updates |
| `GET` | `/health` | Health check (unauthenticated) |

All endpoints except `/health` and `/api/events` require an `X-API-Key` header.

---

## Sample Data

When the application starts it loads cases from `backend/data/sample_cases.json`, these are the eight pre-built clinical cases that appear in the UI straight away, no setup needed. You can browse all of them in that file to understand the data shape.

The sample cases were generated from real OMOP synthetic data using the script at `backend/scripts/generate_cases_pyhealth.py`. That script reads OMOP CSV files from `backend/data/omop/`, decodes condition IDs to readable names, maps lab measurements, and writes the final cases to `sample_cases.json`. If you ever need to regenerate the sample data from a fresh OMOP export, just run that script from the `backend/` directory.

Users can also create their own cases directly from the UI. Any case a user adds or edits is saved to a separate file, `backend/data/user_cases.json` (or a Docker named volume in the containerised setup), completely isolated from the sample data. This separation is intentional, sample cases are read-only and cannot be edited or deleted from the UI, while user-created cases are fully editable. Both sets are merged and served together by `GET /api/cases`.

---

## LLM API Choice

**Anthropic Claude : `claude-sonnet-4-6`**

Claude was chosen for three reasons:

**1. Reliable structured JSON output.**
Both tasks require a strict JSON schema back from the model. Claude reliably returns valid JSON when instructed to with `"Return ONLY valid JSON"`, and the service defensively extracts JSON by scanning for `{` / `}` in case Claude ever wraps output in markdown fences.

**2. Strong clinical reasoning.**
Claude understands clinical context well enough to role-play as a clinical pharmacist or data quality specialist. The prompts give Claude a specific clinical role, which improves the quality and relevance of its reasoning over a generic prompt.

**3. Configurable via env var.**
The model name is read from `ANTHROPIC_MODEL` (defaulting to `claude-sonnet-4-6`), so it can be swapped to Opus or Haiku without a code change useful for balancing cost vs. quality in production.

**Model settings:** `temperature: 0` for deterministic, reproducible clinical outputs. `max_tokens: 2000` enough for structured JSON with verbose reasoning. Timeout: 120s (Claude can take 20–60s for a 2000-token response).

---

## Key Design Decisions & Trade-offs

> The full reasoning behind each decision, including alternatives considered and trade-offs is documented in [docs/architecture_decisions.md](docs/architecture_decisions.md).

### 1. Two-layer AI pipeline (rule-based engine as silent fallback only)

The rule-based engine always runs first and produces a guaranteed valid result. This result is held in memory as a silent fallback, it is **never sent to Claude**. Claude receives only the raw patient data and makes every decision (medication selection, confidence score, safety check, reasoning) independently from scratch. If Claude fails for any reason (timeout, bad JSON, API error), the rule-based result is returned unchanged.

**Why:** Sending the rule-based output to Claude would anchor its decisions to hardcoded rules that assume specific lab names and medication patterns, producing wrong results for cases that don't match those assumptions. Claude must form its own clinical judgement from raw data only. The rule-based engine exists solely to ensure the system is never blocked by AI unavailability.

**Trade-off:** Two compute steps per request. Mitigated by the in-memory cache — identical requests return instantly without touching Claude at all.

### 2. Rule-based output entirely excluded from Claude's input

No rule-based data is passed to Claude. Claude receives only the raw request payload (`patient_data` for reconciliation, `patient_record` for data quality). All output fields,  `reconciled_medication`, `confidence_score`, `clinical_safety_check`, `reasoning`, `recommended_actions`, `overall_score`, `breakdown`, `issues_detected`, `summary` which come exclusively from Claude's own response.

**Why:** Even passing partial rule-based output (e.g. just the confidence score) causes Claude to anchor to it rather than form an independent assessment. A real second opinion requires Claude to see only the raw clinical data — nothing pre-computed.

### 3. SHA-256 in-memory cache keyed on full request payload

Every AI call is gated by a cache that hashes the entire request dict (all case fields, not just the medication sources) with SHA-256 and sorted keys. Identical payloads return instantly.

**Why:** Claude calls cost API credits and take 20–120 seconds. The full payload (including demographics, allergies, vitals) is included in the key so that editing any field on a case forces a fresh Claude call.

**Trade-off:** In-memory only cache resets on restart. No TTL or size limit. Acceptable for a session-based clinical workflow; a Redis layer with TTL would be the production replacement.

### 4. Two-file case storage

Default sample cases (`sample_cases.json`) are read-only and ship with the project. User-created cases (`user_cases.json`) go into a separate file in a Docker named volume, invisible on the host filesystem.

**Why:** Prevents users from accidentally overwriting the clinical reference data. The `USER_DATA_DIR` env var decouples the storage path from the code the same binary works in Docker and locally without branching on `IS_DOCKER`.

### 5. API key authentication at the router level

`verify_api_key` is attached as a `dependencies=[Depends(...)]` at the router level, not per-route. One line protects every current and future route in a router.

**Why:** Per-route auth is easy to accidentally omit when adding a new endpoint. Router-level dependency makes it impossible to add an unprotected route without explicitly opting out.

**SSE exception:** `EventSource` in the browser does not support custom headers, so `/api/events` accepts the key as a `?api_key=` query param instead.

### 6. SSE for real-time updates instead of polling

A singleton `SSEBroadcaster` holds one `asyncio.Queue` per connected browser tab. Every write operation broadcasts a named SSE event. A 25-second heartbeat keeps connections alive through proxies.

**Why:** Polling would add unnecessary load. SSE is simpler than WebSockets for a unidirectional push use case and works well with FastAPI's async model. Named events (`reconciliation_done`, `case_created`, etc.) let the frontend subscribe selectively.

### 7. Pydantic models as the contract boundary

Every request and response is a Pydantic `BaseModel`. This gives automatic 422 validation, type-safe `model_dump()` for cache key generation, and auto-generated OpenAPI docs at `/docs` with zero extra work.

---

## What I'd Improve With More Time

**1. Persist decisions to a database.**
Currently decisions survive in memory until the server restarts. PostgreSQL with SQLAlchemy would give a full audit trail, enable analytics on approval rates per case, and feed decision history back into confidence calibration.

**2. Confidence calibration from historical decisions.**
When clinicians consistently reject reconciliations from a particular source system, that system's reliability weight should decrease automatically. The data is being collected the feedback loop isn't wired yet.

**3. Fuzzy medication name matching.**
"Aspirin", "ASA", and "Acetylsalicylic acid" are the same drug. The current reconciliation engine does exact string comparison. A fuzzy matcher (e.g. RxNorm API lookup or token-set ratio) would catch these cross-system naming differences.

**4. Claude structured output (tool use).**
Instead of `"Return ONLY valid JSON"` in the system prompt, use Claude's native tool/function calling to enforce the JSON schema at the API level. This removes the need for defensive `find("{")` / `rfind("}")` parsing.

**5. User authentication and multi-tenancy.**
Right now there is one API key for all users. A proper auth layer (JWT, OAuth) would give per-user audit trails, role-based access (clinician vs. pharmacist vs. admin), and the ability to scope decisions to individual users.

**6. Redis cache with TTL.**
Replace the in-memory dict with Redis so the cache survives server restarts and can be shared across horizontally scaled instances. A 1-hour TTL would prevent stale results from being served indefinitely.

**7. End-to-end and integration tests for the frontend.**
Current test coverage is backend-only. Cypress or Playwright tests would catch regressions in the full navigate -> run AI -> approve/reject flow.

---

## Estimated Time Spent

| Area | Time |
|---|---|
| Architecture planning & data modelling | 3.5 h |
| Backend — routers, models, rule-based engine | 3.5 h |
| Backend — Claude integration, cache, SSE | 2 h |
| Backend — tests (cache, endpoints, Claude) | 2 h |
| Frontend — Cases page with full CRUD & validation | 3 h |
| Frontend — Reconciliation & Data Quality pages | 2 h |
| Frontend — SSE hook, live notices, decision restore | 1 h |
| Docker Compose, volumes, nginx config | 1 h |
| Documentation (document files, README) | 1 h |
| **Total** | **~19 h** |

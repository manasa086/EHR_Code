# Architecture Decisions

---

### 1. FastAPI over Flask/Django

FastAPI was chosen because it is async-native (required for non-blocking Claude API calls and SSE streaming), generates OpenAPI docs automatically at `/docs`, and enforces request/response types via Pydantic with zero extra code. Flask would have required async bolted on; Django would have been overkill for a focused API service.

→ See [OpenAPI Docs](#openapi-docs) below for URLs and why they are useful.

---

### 2. Two-layer AI pipeline (rule-based engine as silent fallback only)

The rule-based engine always runs first and produces a guaranteed valid result. This result is held in memory as a silent fallback it is **never sent to Claude as input**. Claude receives only the raw patient data and makes all decisions independently. If Claude fails for any reason (timeout, bad JSON, API error), the rule-based result is returned as-is.

This means the system is never blocked by AI unavailability clinicians always get a structured output. Claude's job is to reason from raw clinical data, not to review or validate pre-computed values.

---

### 3. Rule-based output entirely excluded from Claude's input

No rule-based data is passed to Claude. Claude receives only the raw request payload (`patient_data` for reconciliation, `patient_record` for data quality). Every output field — `reconciled_medication`, `confidence_score`, `clinical_safety_check`, `reasoning`, `recommended_actions`, `overall_score`, `breakdown`, `issues_detected`, `summary` — comes exclusively from Claude's own response.

Sending any rule-based output to Claude — even just the confidence score — would anchor its decisions to hardcoded rules that assume specific lab names and medication patterns. This produces wrong results for cases that don't match those assumptions. Excluding rule-based output entirely forces genuine independent clinical judgement and makes Claude's assessment a real second opinion rather than a rubber stamp.

---

### 4. SHA-256 in-memory cache on full payload

Every AI call is gated by a cache that hashes the entire request, not just the patient ID or medication sources, but every field including demographics, allergies, and vitals. Identical payloads return instantly without touching Claude.

Hashing the full payload ensures that editing any field on a case forces a fresh Claude call. An ID-only key would silently serve stale results after a case edit.

---

### 5. Two-file case storage

Sample cases (`sample_cases.json`) and user-created cases (`user_cases.json`) live in separate files. Sample cases are read-only (`editable: false`). User cases go into a Docker named volume, invisible on the host filesystem.

This prevents users from accidentally overwriting clinical reference data, and keeps user-generated data out of git. The `USER_DATA_DIR` env var decouples the storage path from the code — no `if IS_DOCKER` branching needed.

---

### 6. Router-level API key authentication

`verify_api_key` is applied via `dependencies=[Depends(...)]` at the router level, not per-route. One line protects every current and future route in that router.

Per-route auth is easy to accidentally omit when adding a new endpoint. Router-level dependency makes an unprotected route impossible without explicitly opting out.

---

### 7. SSE over polling or WebSockets

A singleton `SSEBroadcaster` pushes named events (`reconciliation_done`, `case_created`, etc.) to every connected browser tab via Server-Sent Events.

SSE is simpler than WebSockets for a unidirectional push use case and works natively with FastAPI's async streaming. Polling would have added unnecessary backend load. WebSockets would have added unnecessary bidirectional complexity.

---

### 8. Pydantic models as the contract boundary

Every request and response is a Pydantic `BaseModel`. This gives automatic 422 validation on bad input, type-safe `model_dump()` for cache key generation, and auto-generated OpenAPI docs, all with no extra code.

It also makes the contract between router and service layer explicit. The router accepts a typed model; the service receives a plain dict. The boundary is always clear.

→ See [OpenAPI Docs](#openapi-docs) below for URLs and why they are useful.

---

### 9. Prompts centralised in `prompts.py`

Both Claude system prompts live in `backend/prompts.py` as named constants. `ai_service.py` imports them.

Keeping prompts in one file means they can be reviewed, versioned, and edited without hunting through service code. It also makes it easy to see both prompts side by side and ensure they follow consistent design patterns.

---

### 10. Vite + React over Next.js

The frontend is a pure client-side SPA with three routes. There is no need for server-side rendering, static generation, or a Node.js server at runtime. Vite builds to static files served by Nginx in Docker which is a simpler, smaller production footprint with no Node process to manage.

---

### OpenAPI Docs

You can view the OpenAPI docs at the following URLs when the backend is running locally:
- **Swagger UI** (interactive, you can test endpoints directly from the browser): http://localhost:8000/docs

These docs are useful for three reasons: they let a frontend developer or QA engineer test any endpoint directly in the browser without needing Postman or curl; they serve as always-up-to-date API documentation since they are generated from the actual code rather than written by hand; and they make it easy for a new developer joining the project to understand what every endpoint accepts and returns without reading the source code.

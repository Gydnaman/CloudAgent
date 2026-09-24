# CloudAgent Stage A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver an isolated, local Mock customer-support Agent demo with a secure session boundary, persisted run events and Vue workbench.

**Architecture:** A modular monolith uses FastAPI as the HTTP boundary, LangGraph as the deterministic workflow, PostgreSQL for app records/checkpoints, and Vue for the workbench. The application owns the RunEvent/SSE contract and every model, knowledge and tool implementation is Mock-only.

**Tech Stack:** Python 3.12, uv, FastAPI 0.141, Pydantic v2, LangGraph 1.2, AsyncPostgresSaver 3.1.2, PostgreSQL 18, Vue 3.5, TypeScript, Vite, Node.js 24 LTS, Alembic.

**Spec:** `docs/specifications/stage-a.md`

## Global Constraints

- Follow `docs/technical-proposals/phase-a.md`; re-review any change to technology, public API or event semantics.
- Require `langgraph-checkpoint >=4.1.1,<5`; re-check the resolved lock and current advisories before dependency lock.
- Demo auth only runs in local environment when explicitly enabled; 32-byte opaque token, SHA-256 digest only, eight-hour expiry.
- AuthContext is immutable and run-scoped; never store it, token, secrets, system prompt or full prompt in graph state, checkpoint, event or log.
- Only Mock LLM/Knowledge/Tool adapters; tool allowlist, schema and resource ownership checked server-side.
- PostgreSQL is the only app database; never fall back to SQLite; Compose binds Web/API to loopback, one API worker.
- Persist each event before publishing it; one run has one terminal event; close/start/terminal paths share per-run gate.
- Do not use personal, customer or production business data.

---

### Task 1: Bootstrap the CloudAgent project

**Files:**
- Create: `backend/pyproject.toml`, `backend/uv.lock`, `backend/Dockerfile`
- Create: `backend/app/main.py`, `backend/app/config.py`, `backend/app/api/health.py`
- Create: `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/versions/0001_stage_a.py`
- Create: `compose.yaml`, `.env.example`, `.gitignore`, root `package.json`, `README.md`

**Interfaces:**
- `GET /api/v1/health/live` reports process liveness.
- `GET /api/v1/health/ready` succeeds only after DB connection, schema migration and checkpoint setup succeed.
- `DATABASE_URL` is the single app persistence setting; `APP_ENV`, `DEMO_AUTH_ENABLED`, `WEB_ORIGINS` are validated at startup.

- [ ] Define package constraints and generate a lockfile on Python 3.12; ensure the checkpoint floor excludes 4.1.0.
- [ ] Define SQLAlchemy async engine/session lifecycle and Alembic metadata imports.
- [ ] Add initial explicit migration for Conversation, Message, AgentRun and RunEvent constraints.
- [ ] Add Compose Postgres healthcheck, one-shot migration dependency, single API worker, and loopback port bindings.
- [ ] Document the run and reset commands and synthetic-data warning.

### Task 2: Implement demo sessions and authorization boundary

**Files:**
- Create: `backend/app/auth/sessions.py`, `backend/app/auth/context.py`
- Create: `backend/app/api/session_routes.py`, `backend/app/persistence/models.py`, `backend/app/persistence/repositories.py`
- Create: `backend/tests/test_sessions.py`, `backend/tests/test_session_close.py`

**Interfaces:**
- `create_session(subject_id) -> SessionCreated` returns the raw token once; DB stores only digest and expiry.
- `resolve_session(session_id, token, *, allow_closed_replay=False) -> DemoRunContext` verifies digest in constant time, expiry and closure state.
- `close_session(session_id, token) -> CloseReceipt` atomically closes the session and stores nullable `close_run_id`.

- [ ] Write failing tests for token binding, 8-hour expiry, closed-session denial and idempotent close replay.
- [ ] Implement the minimal repository and session endpoints to satisfy them.
- [ ] Add fixtures for synthetic Product/Billing subjects and owned/unowned account IDs.
- [ ] Confirm public DTOs and logs never expose token digest or AuthContext.

### Task 3: Implement deterministic customer-support graph

**Files:**
- Create: `backend/app/agent/graph.py`, `backend/app/agent/state.py`, `backend/app/agent/runtime.py`
- Create: `backend/app/providers/mock_llm.py`, `backend/app/knowledge/mock_knowledge.py`, `backend/app/tools/mock_account.py`, `backend/app/policy/authorization.py`
- Create: `backend/app/domain/events.py`, `backend/app/domain/scenarios.py`
- Create: `backend/tests/test_routes_and_tools.py`, `backend/tests/test_run_events.py`

**Interfaces:**
- `AgentRuntime.start(context, message, run_id) -> AsyncIterator[RunEvent]` emits only application-owned events.
- `DemoRunContext` is immutable and injected via `StateGraph(context_schema=...)`/`Runtime.context` per call.
- `AuthorizationPolicy.check(subject, action, resource) -> Decision` gates the read-only `read_account_usage` adapter.

- [ ] Write failing scenario tests for Product hit/empty, Billing allow/deny and unsupported intent.
- [ ] Implement graph nodes, event order and Mock fixtures; no third-party SDK calls.
- [ ] Persist state and one terminal event under the per-run gate.
- [ ] Add run timeout, global concurrency cap and interrupted-run reconciliation.

### Task 4: Implement sessions, idempotent run creation and fetch-SSE API

**Files:**
- Create: `backend/app/api/run_routes.py`, `backend/app/application/run_service.py`, `backend/app/application/event_writer.py`, `backend/app/api/sse.py`
- Create: `backend/tests/test_run_api.py`, `backend/tests/test_sse.py`

**Interfaces:**
- `POST /api/v1/sessions/{session_id}/runs/stream` accepts JSON message + `Idempotency-Key`, returns SSE after durable `run.started`.
- `GET /api/v1/runs/{run_id}` and `/events` validate the owning session token.
- SSE frames use `id`, `event`, one-line JSON `data`, blank-line delimiters, heartbeat every 15 seconds.

- [ ] Write failing tests for request normalization/hash, duplicate key, changed body conflict and same-session concurrency.
- [ ] Implement row-lock validation, database uniqueness fallback and registered run launch.
- [ ] Implement shared gate for startup/close/terminal commit, including close-response-loss replay.
- [ ] Parse/stream only events whose database commit succeeded; bound DB retry and query persisted events after EOF.
- [ ] Export OpenAPI from FastAPI and confirm request/response schemas reflect required headers.

### Task 5: Pass UX Gate and build the Vue workbench

**Files:**
- Create: `docs/DESIGN.md`, `docs/EXPERIENCE.md`
- Create: `frontend/package.json`, `frontend/index.html`, `frontend/src/main.ts`, `frontend/src/router.ts`, `frontend/src/style.css`
- Create: `frontend/src/api/client.ts`, `frontend/src/api/sse.ts`, `frontend/src/pages/ChatPage.vue`, `frontend/src/pages/RunsPage.vue`, `frontend/src/pages/RunDetailPage.vue`, `frontend/src/pages/ProvidersPage.vue`
- Create: `frontend/tests/sse.test.ts`

**Interfaces:**
- API client sends token only in `X-Demo-Session-Token`, never URL or event payload.
- `consumeRunStream(response, handlers, signal)` parses arbitrarily split UTF-8 frames and reports EOF without terminal for recovery.
- Frontend displays one of mock, loading, empty, deny, error, cancelled or completed states; no live adapter UI action.

- [ ] Complete UX Gate artifacts before page code.
- [ ] Write failing SSE parser tests for multibyte split, multiple events per chunk and incomplete final frame.
- [ ] Implement shared API DTO client and streaming parser.
- [ ] Build chat composer/timeline, run details, provider status and catalog surfaces using synthetic fixtures.
- [ ] Verify CSP blocks third-party scripts and browser connection allowlist is local.

### Task 6: Integrate the vertical slice and handoff

**Files:**
- Modify: `compose.yaml`, `README.md`, `backend/app/main.py`, `frontend/src/router.ts`
- Generate: `docs/api/openapi.json`, `frontend/src/api/generated/types.gen.ts`

- [ ] Connect DB migrations, saver setup, graph, endpoints and frontend in lifespan/config.
- [ ] Add acceptance coverage for SSE loss, idempotency races, close/start schedule race, capacity limits and CSP.
- [ ] Run backend tests, API type drift check, typecheck/build and Compose config checks.
- [ ] Complete README demo flow for Product, Billing allow/deny, unsupported, empty knowledge and close replay.

---

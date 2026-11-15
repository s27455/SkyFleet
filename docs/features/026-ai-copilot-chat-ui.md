# Feature 026 — AI Copilot Chat UI

**Status:** Finalized (2026-11-15). Backend endpoint, access control and Operations tab implemented and verified offline with fake transports; no paid Anthropic request was made for this feature.
**Project:** SkyFleet  
**Dependencies:** Feature 024 (AI Foundation & Cost Guardrails, committed `76f2237`); Feature 025 (Fleet Context & Read-Only Intelligence, committed `b8a72a3`)  
**Scope:** Secure, read-only, operator-facing AI chat for the local SkyFleet MVP.

## 1. Goal

Allow a SkyFleet operator to ask natural-language questions about the current simulation from the frontend and receive grounded answers based on the Feature 025 fleet snapshot, using the Feature 024 AI gateway and its existing persistent budget controls.

This is a **read-only assistant**, not an autonomous agent. No model tools, operational commands, dispatch actions, database mutations, or AI-controlled drone operations are permitted.

## 2. User stories

- As an operator, I can open an AI Copilot panel and ask about current drone availability, active missions, hub occupancy, pending orders, incidents, and operational warnings.
- I can see when a response refers to a snapshot and whether that snapshot is degraded or truncated.
- I receive a clear explanation when AI is disabled, the simulation is unavailable, the request is rate-limited, the budget is exhausted, or the provider fails.
- I can submit one question at a time and cannot accidentally trigger duplicate paid requests through repeated clicks or UI retries.
- I understand that the Copilot cannot execute actions or guarantee correctness beyond the supplied snapshot.

## 3. Scope and non-goals

### In scope

1. A minimal frontend chat panel integrated into the existing React/TypeScript UI, following existing styling and component conventions.
2. One authenticated, explicitly enabled backend route for asking a question, with a bounded request/response contract.
3. A narrowly scoped local-MVP authentication or access-control mechanism **selected only after Gate A inspects the existing app and deployment model**.
4. Reuse of `ask_fleet_question` from Feature 025 and the Feature 024 gateway; do not duplicate context construction, budget logic, provider transport, or ledger writes.
5. Server-side validation, safe error mapping, loading/disabled states, and visible cost-control messaging.
6. Snapshot provenance and quality indicators (`captured_at`, `data_status`, `truncated`, `limitations`) surfaced to the user using trusted backend metadata, not claims extracted from the model's prose.
7. Question-aware retention of named drone IDs when a context must be truncated, if safely feasible within the existing deterministic budget and data contract.
8. Offline integration and browser QA with a fake Anthropic transport; a paid smoke test is a separately approved Gate C activity.

### Out of scope

- Multi-user accounts, registration, password reset, OAuth, role management, or cloud deployment.
- Public or anonymously callable paid AI endpoint.
- Agent/tool calling, drone commands, database writes, automatic actions, or AI recommendations executed by the application.
- Streaming responses, conversation persistence, embeddings, RAG, file uploads, and external web access.
- Changing the existing $4 internal lifetime ceiling, 10 requests/hour, 30-second minimum gap, one concurrent request, 16 KiB input cap, 400-token output cap, or provider retry policy.
- Refactoring unrelated frontend/backend modules or addressing the existing unrelated mypy error.

## 4. Security and cost requirements (mandatory)

### 4.1 Access control before endpoint exposure

Gate A must investigate current frontend/backend origins, how the app is started, existing API conventions, local-only vs network binding, and any existing authentication/session mechanisms. It must recommend a minimal design and threat model. **Do not implement or expose a paid endpoint until the access-control approach is explicitly approved in Gate B.**

Requirements for the chosen design:

- Reject unauthenticated requests **before** building a fleet snapshot or reserving AI budget.
- Never send `ANTHROPIC_API_KEY`, local backend secrets, or privileged credentials to the browser bundle or responses.
- Do not assume CORS, a hidden URL, localhost binding, or a client-supplied static token alone constitutes sufficient authentication.
- Evaluate CSRF protection if using cookies; evaluate token exposure and storage if using bearer credentials.
- Keep AI disabled by default, including in development; document how an operator deliberately enables it.
- Preserve localhost-only binding for the MVP unless a separately reviewed deployment plan requires otherwise.
- Ensure error responses and logs do not expose secrets, raw prompts, stack traces, or internal database content.
- Use the backend gateway as the single authority for request throttling, concurrency, cost reservation, accounting, and provider calls. UI disabling is only an additional safeguard.

### 4.2 One request, no retries

- A deliberate user submission may trigger at most one gateway call.
- Disable submission while a request is pending. No automatic retries on timeouts, provider errors, refresh, or reconnect.
- Protect against double submission; distinguish frontend prevention from server-side guarantees. Gate A should assess whether request-id/idempotency handling is warranted and feasible without weakening Feature 024 controls.
- Never retry an ambiguous provider failure without operator inspection of ledger and provider Console.
- No automatic model call on page load, panel open, simulation tick, polling, or navigation.

### 4.3 Configuration and pricing

- Construct the context service and gateway from the **same effective Settings** instance to prevent mismatched limits.
- Preserve Feature 024 model/pricing freshness checks and fail-closed behavior.
- Provider Console spend limits and disabled auto-reload remain essential independent controls; the application's internal ceiling is not a provider-side guarantee.
- Do not print, store in frontend state, or commit the real API key.

## 5. Grounding and prompt safety

- Route questions through Feature 025's authoritative read-only snapshot and existing fixed system prompt.
- Separate trusted instructions from the question and fleet data unambiguously; assess the current `Fleet context:` / `Question:` delimiter collision noted in Feature 025. Treat all user text and database-derived content as untrusted data.
- Do not rely on prompt wording alone for security: no tools or write-capable APIs are available to the model.
- Provide the model with clear temporal context and require uncertainty when the snapshot is stale, degraded, truncated, or missing a requested drone.
- For a question containing a valid drone ID, investigate deterministic ID extraction and **pinning that drone in the rendered context** ahead of routine rows when byte-budget reduction is needed. Never exceed the 40-row cap or 16 KiB total request cap. If a named drone cannot be included, report that fact explicitly instead of inventing details.
- Avoid sending conversation history by default. V1 requests are independent, one question plus one current snapshot.
- Model answers must be displayed as untrusted text, not injected as HTML. Avoid unsafe Markdown/HTML rendering and link execution.

## 6. Proposed API contract (to be validated in Gate A)

Suggested route: `POST /api/ai/copilot/ask` (name and prefix subject to existing conventions).

Request:

```json
{
  "question": "Which drones need attention?"
}
```

Constraints: question is a nonempty string after validation, at most 500 characters and within the Feature 024 total input-byte cap. Additional fields are rejected or ignored according to established API validation conventions; no model, system prompt, tool definitions, or budget overrides may be supplied by the browser.

Illustrative successful response:

```json
{
  "answer": "...",
  "snapshot": {
    "captured_at": "2026-11-15T14:03:07Z",
    "data_status": "complete",
    "truncated": false,
    "limitations": []
  }
}
```

The response schema should be typed and should carry metadata directly from the server-side snapshot. **Gate A must verify whether Feature 025's current service returns that metadata or requires a small, backwards-compatible extension.** Do not return full raw fleet context to the browser unless specifically justified.

Suggested error categories: `AI_DISABLED`, `UNAUTHORIZED`, `INVALID_QUESTION`, `RATE_LIMITED`, `BUDGET_EXHAUSTED`, `CONTEXT_UNAVAILABLE`, `CONTEXT_TOO_LARGE`, `PROVIDER_UNAVAILABLE`, `AI_HALTED`, and `INTERNAL_ERROR`. Map to appropriate HTTP statuses without revealing internal exception text. Define the exact mapping during Gate A.

## 7. Frontend experience

- Integrate an accessible Copilot entry point into the existing Operations interface without disrupting the map or operational controls.
- Provide a compact panel with an initial empty state, one question field, send action, response area, and clear pending/error states.
- Show a clear label: **Read-only AI Copilot — cannot control drones**.
- Display snapshot timestamp and a visible warning for degraded or truncated context.
- Show disabled/unavailable status without triggering any paid call.
- Prevent duplicate submission while pending and do not silently retry.
- Render answer as plain text or strictly sanitized supported formatting; never interpret model output as executable markup.
- Avoid inventing cost figures in the UI. If displaying request costs, use authoritative ledger data or omit the figure in v1.
- Follow existing accessibility, responsive-layout, and styling patterns.

## 8. Testing and acceptance criteria

### Offline backend tests

- Authentication is enforced before any database read, reservation, or provider invocation.
- Disabled AI returns a safe response with zero provider calls.
- Invalid, oversized, or malformed questions are rejected without spending.
- A successful authenticated request invokes the existing fleet-context service and gateway exactly once.
- The request uses the same Settings for both components and respects all Feature 024 guardrails.
- Safe, stable mapping of gateway/context errors; no secret or traceback leakage.
- Snapshot provenance/limitations come from server data, not model-generated prose.
- Prompt delimiter injection and malicious-looking data remain inert.
- Question-specific drone pinning works when applicable; omitted requested data is disclosed.
- Concurrent submissions, provider timeout, ambiguous outcome, budget halt, and rate limits do not cause retries or extra charges.
- All tests use fake model transport unless a single paid test is separately approved.

### Frontend and browser tests

- Open/close panel, ask a question, see loading and grounded answer, handle errors, and view snapshot quality warnings.
- Submit button and keyboard behavior do not produce duplicate requests.
- No request occurs on page load, open, or navigation.
- AI-disabled mode is understandable and does not leak configuration secrets.
- Model output cannot inject HTML/script or trigger an action.
- Map, simulation controls, and existing Operations navigation continue to work.

### Regression checks

- Full backend pytest and PostgreSQL suites, Ruff, formatting and mypy (report existing unrelated error separately).
- Existing Feature 024 and 025 tests remain green.
- No new migrations unless Gate A finds an unavoidable requirement and receives separate approval.
- Dev database and ledger remain unchanged throughout offline gates.

## 9. Delivery gates

### Gate A — read-only investigation and design

1. Inspect existing backend API/router/auth patterns, frontend layout and state management, local dev origins, and deployment assumptions.
2. Identify the minimum viable secure access-control solution and alternatives, with threat model and trade-offs.
3. Trace the exact `ask_fleet_question` API, gateway construction, settings usage, and available snapshot metadata.
4. Design exact endpoint and response types, error mapping, and frontend component integration.
5. Propose delimiter neutralization and named-drone retention within existing byte caps.
6. Provide file-by-file implementation plan and tests.
7. **Do not modify files, call Anthropic, run migrations, restart, commit, or push. Stop for approval.**

### Gate B — offline implementation

After explicit approval of the authentication design, implement the minimum endpoint, security checks, typed contract, frontend panel, and offline tests. No paid provider calls. No push or commit until Gate D.

### Gate C1 — integration and browser QA (offline)

Verify authentication, failure modes, snapshot freshness, question handling, frontend UX, and regressions using fake transport. Test disabled/default mode and zero unintended provider calls.

### Gate C2 — optional paid smoke test (separate approval)

Only if explicitly authorized after C1: one bounded real request, one model call, no retry, preflight checks of local settings, ledger, model/pricing freshness, prepaid Console balance, spend limit, and auto-reload OFF. Confirm actual provider usage and ledger after the call. Never infer provider charges solely from local reservations. If any outcome is ambiguous, stop without retrying.

### Gate D — documentation and local commit

Update spec, ADR if needed, architecture context and progress tracker. Review diff, secret hygiene, tests, and scope. Commit only Feature 026 changes locally. **Do not push without explicit approval.**

## 10. Open design decisions for Gate A

1. What is the safest minimal authentication/access-control scheme for this local SkyFleet MVP, given its existing architecture?
2. Where should the Copilot panel live in the Operations UI?
3. Should the API return a server-derived `snapshot` metadata object, and how should it be surfaced from Feature 025?
4. How should a named drone be recognized and pinned without ambiguous matches or extra database queries?
5. How should questions containing `Fleet context:` or `Question:` be delimited safely?
6. Which status/error codes and messages match the existing API conventions?
7. Is server-side idempotency necessary for the intended local single-operator threat model, or are the existing gateway concurrency/rate limits plus frontend in-flight protection sufficient?

## 11. Definition of done

Feature 026 is complete when a locally authenticated operator can deliberately submit a question through the UI, receive a grounded response based on a read-only current snapshot, see provenance and limitations, and safely handle disabled/error/budget states, with no write-capable model behavior, no exposed secrets, and no unapproved paid calls. All applicable automated and browser QA checks must pass, documentation must be updated, and the work must be committed locally without push.

**Important:** This document is a proposed specification. Gate A must validate implementation assumptions against the actual SkyFleet repository before Gate B is approved.

## Gate A decisions (approved 2026-11-15)

Local operator Bearer token with strict Origin validation and constant-time comparison, kept only in the server's Git-ignored `backend/.env` and typed into the UI, where it stays in memory; Copilot as the fifth Operations tab with its state above the tabs; `FleetAnswer` extended with limitations, omitted and named drones, snapshot `schema_version` 2; operator questions normalised to one line; up to eight `DRN-n` ids pinned right after the flagged drones and disclosed when missing or omitted; a fixed error-code mapping; no server-side idempotency in v1 (the gateway limits plus a frontend guard); a minimal unauthenticated status endpoint (a generic boolean); and, added at approval, a small bounded in-memory throttle of failed authentication attempts.

## Gate B record (2026-11-15)

### What was built

**Backend.** `app/copilot/` (`access.py`, `schemas.py`, `service.py`), `app/api/routes/copilot.py` (`GET /api/ai/copilot/status`, `POST /api/ai/copilot/ask`), `app/fleet_context/question.py`; changes to `config.py` (`ai_access_token`, a `SecretStr` with `repr=False`), `main.py` (the router, `Authorization` added to the allowed CORS headers, a validation handler scoped to `/api/ai/` that never echoes a rejected question, the per-app throttle), `fleet_context` (`NamedDrone`, the roster tier, `FleetAnswer.limitations/omitted/named_drones`, schema version 2) and the fixed system prompt (1,415 to 1,682 bytes: how to read `named_drones`, and that the question is one line of operator text). No migration, no new dependency.

**Frontend.** `types/copilot.ts`, `api/copilot.ts`, `features/copilot/{useCopilot.ts, CopilotTab.tsx, limitationText.ts}`, an optional `headers` argument on `apiSend`, the `copilot` tab in `tabs.ts` and the wiring in `App.tsx`.

### Security design

- **Order of checks (all before any database read, snapshot, reservation or provider call):** `Origin` must be present and in the CORS allow-list (403 `ORIGIN_NOT_ALLOWED`); AI must be enabled (503 `AI_DISABLED`); the configuration and the token must be usable, a missing or under-32-character token closing the endpoint for everybody (503 `AI_MISCONFIGURED`); the failed-attempt throttle must not be blocking (429 `AUTH_THROTTLED`); the bearer token must match (401 `UNAUTHORIZED`, identical for a missing and a wrong token). The check is the first dependency of the route, so the Copilot service, and with it the gateway, is not even created for a refused request (tests count SQL statements and service creations: zero).
- **Token:** compared in constant time on SHA-256 digests; never logged, returned, put in a URL, cookie, storage or frontend variable; the frontend hook never exposes its value to components and keeps it in memory only.
- **Throttle:** a bounded (10 timestamps) in-memory sliding window of 60 s, process-local, with no database writes; after 10 failures everything is refused until the oldest failure leaves the window, the correct token included; it only adds a refusal and cannot accept anything. It resets when the API restarts. Trade-off: someone who can reach the API can lock the operator out for at most one window. Origin, disabled and misconfiguration refusals do not feed it.
- **Not authentication, and not relied on:** CORS, loopback binding, a hidden URL. The backend stays bound to `127.0.0.1`.
- **Known nuance:** FastAPI parses a request body before it runs dependencies, so malformed JSON from an unauthenticated caller gets a generic 422; it touches no database, service or provider.
- **Model output:** shown as a plain text node (markup, links and scripts stay inert); no Markdown, no HTML.
- **One request:** the route has one `ask` call, the service one `ask_fleet_question` call, the frontend one `askCopilot` call site (source tests forbid loops, timers, `AbortController` and any second path); the hook ignores a submission while one is pending (a ref, so two clicks in the same tick still send one); nothing is sent on page load, tab opening or navigation, and the only request made when the tab appears is the harmless availability probe.
- **Unclear outcomes:** a provider timeout or 5xx, a lost connection, an unreadable success and a non-Copilot 5xx are all shown with the warning that the request may have been charged and will not be retried automatically; a provider rejection says no charge is expected.

### Error mapping (`detail: {code, message}`, fixed messages, plus `retry_after_seconds` / `charge_possible` where they apply)

403 `ORIGIN_NOT_ALLOWED`; 503 `AI_DISABLED`; 503 `AI_MISCONFIGURED`; 401 `UNAUTHORIZED` (with `WWW-Authenticate: Bearer`); 429 `AUTH_THROTTLED`; 422 `INVALID_QUESTION`; 413 `CONTEXT_TOO_LARGE`; 429 `RATE_LIMITED` (too soon, hourly quota, one in flight); 409 `BUDGET_EXHAUSTED`; 409 `AI_HALTED`; 503 `PROVIDER_UNAVAILABLE` (back-off); 503 `ACCOUNTING_UNAVAILABLE`; 503 `CONTEXT_UNAVAILABLE`; 502 `PROVIDER_UNAVAILABLE` (`charge_possible` true or false); 500 `INTERNAL_ERROR`. `AUTH_THROTTLED`, `AI_MISCONFIGURED`, `ORIGIN_NOT_ALLOWED` and `ACCOUNTING_UNAVAILABLE` are additions to the spec's list. No exception text, row data, prompt or credential reaches a response or a log (only a code, an exception type or a setting NAME).

### Response contract

`{answer, answer_cut_off, snapshot: {captured_at, data_status, truncated, limitations[], omitted{drones,hubs,active_incidents,recovered_alerts}, named_drones[{id, exists, listed}]}}`, all snapshot fields copied from the server-side snapshot as rendered; no cost, token count, provider id or raw context.

### Operator runbook (deliberate enabling; never in chat, URLs or a frontend variable)

In the Git-ignored `backend/.env`: `SKYFLEET_AI_ENABLED=true`, `ANTHROPIC_API_KEY=...`, and `SKYFLEET_AI_ACCESS_TOKEN=<a new secret>` generated once on the operator's own machine with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Restart the API (a change to `.env` does not trigger its reload), open Operations, then Copilot, enter the token. To disable: set `SKYFLEET_AI_ENABLED=false` (or remove the token or the key) and restart; the endpoint then answers 503 and the tab says it is unavailable. The Console spend limit and auto-reload settings remain essential.

### Verification (offline, fake transports only)

Backend ruff and format clean; `mypy .` reports one error in the unmodified `tests/weather/test_rain_warning.py:208` (pre-existing); `pytest` 1524 passed (181 new); `pytest -m postgres` 105 passed (2 new, including eight racing POSTs that produce exactly one provider request and a flood of wrong tokens that touches nothing). Frontend typecheck, `oxlint` and Prettier (on `src`) clean; `vitest` 986 passed in 71 files (57 and 2 new); production build succeeds and the bundle contains none of `SKYFLEET_AI_ACCESS_TOKEN`, `ANTHROPIC`, `sk-ant` or `x-api-key`. Mutation checks: removing the access dependency, the Origin check, the constant-time comparison, the throttle (not blocking, or failures not recorded), the disabled check or the misconfiguration check each fails tests; removing the double-submit guard, rendering the answer as HTML or storing the token in `localStorage` each fails a frontend test. The live API (which hot-reloaded by itself) answers `{"available": false}` by default, 403 without an allowed Origin and 503 `AI_DISABLED` with one; the development ledger is unchanged (migration 0019, one request, from Feature 024).

### Deviations from Gate A

The service builds its own session factory (no `get_session_factory` dependency was added); the frontend adds `CONNECTION_LOST` and `UNKNOWN` failure codes for an unusable server answer; the hook exposes `hasToken`, never the token; a named drone that is itself among more than 40 flagged drones can still fall outside the cap (flagged drones outrank named ones by design) and is then reported as `listed: false`.

### Known limits and risks

The throttle is process-local; the operator token is one shared secret for one local operator (no accounts); the Copilot needs the API restarted after `.env` changes; `backend/.env.example` could not be edited by the implementer (permission settings), so the placeholder lines for `SKYFLEET_AI_ACCESS_TOKEN` must be added by hand; the first real request that carries a fleet context still needs the owner's approval (Gate C2); the model's compliance with the prompt is untested.

## Final QA and finalization record (2026-11-15)

A combined, deliberately focused Gate C and D (usage conserved): the critical authentication and cost-safety paths were verified with the existing tests, one gap was closed, and no critical or high-severity defect was found.

### Critical paths, verified by existing offline tests (fake transports only)

- **Authentication before anything:** a missing, wrong, truncated, extended or mis-schemed token, a foreign or missing Origin, disabled AI and a missing or short token or key are all refused with zero SQL statements, zero service creations and zero provider calls; authentication also precedes body validation; the check is the first dependency of the route.
- **Cost safety:** two POSTs give one provider request (the gateway's gap), eight racing POSTs on PostgreSQL give exactly one provider request and one ledger row with nothing reserved, a provider timeout or 5xx is charged in full and never retried, a rejection is refunded, a halted gateway, an exhausted budget, a failing snapshot and an oversized request each refuse without a provider call, and every refusal maps to a fixed code with no internal text.
- **Throttle:** ten failures lock everybody out, the correct token included, until the window passes; only failed authentication feeds it; a wrong token never succeeds; memory stays bounded.
- **Frontend main interaction:** nothing is sent on load, tab opening or navigation; one request per submission however it is triggered; the token only in the Authorization header and in memory (no storage, cookie, URL or DOM); the answer shown as inert plain text; state kept across tab switches and a map selection, even for a request still in flight; every failure explained, with the charge warning for every unclear outcome and no automatic retry.
- **Gap found and closed:** every API test injected a fake gateway, so the production path (the un-overridden dependency building the gateway from the app's own settings) was untested. Two tests now run it for real with only the SDK-bound transport replaced by a recorder: the key and the timeout reach the transport from the app's own `Settings`, the service holds that same object, two POSTs produce one provider request, and a refused request creates neither the service nor the transport.

### Verification

Full suites ran at Gate B (backend 1524 offline and 105 PostgreSQL tests, frontend 986 tests in 71 files, ruff, format, mypy with the one known unrelated error, oxlint, Prettier, typecheck, production build); afterwards only the two wiring tests were added, and they, the whole `tests/copilot` suite including its PostgreSQL tests (141) and the targeted frontend tests (72) were run again. The development database and the AI ledger were not touched (migration 0019, one request from Feature 024); no migration, dependency or service restart was needed.

### Not done, on purpose

No real-browser QA harness (the interaction is covered by jsdom tests against a fake backend; a browser pass remains an owner check); no paid request (a separately approved activity); `backend/.env.example` still lacks the placeholder `SKYFLEET_AI_ACCESS_TOKEN` lines (the permission settings deny edits to that file; the owner adds them by hand).

### Remaining limitations

The throttle is process-local and resets on restart; the token is one shared secret for one local operator; enabling needs `.env` changes and an API restart; a named drone that is itself among more than 40 flagged drones can be unlisted (reported as such); the first real request carrying a fleet context needs the owner's approval, and the model's compliance with the prompt is untested.

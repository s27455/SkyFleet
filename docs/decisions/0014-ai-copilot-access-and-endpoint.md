# 0014 — AI Copilot: access control and endpoint (Feature 026)

**Status:** Accepted for the local MVP and implemented. The Copilot is read-only (one question, one answer, no model tool and no action), disabled by default, and every request is checked, bounded and accounted by the Feature 024 gateway. It was verified with fake transports only; no real request carries a fleet context yet.

## Context

The API had no authentication, and this is the first endpoint that can spend money. CORS, loopback binding and a hidden URL authenticate nobody: any page in the browser can send requests to `localhost`, and any local process can too.

## Decisions

- **One operator token.** `SKYFLEET_AI_ACCESS_TOKEN` (at least 32 characters) lives only in the Git-ignored `backend/.env`. The operator types it into the Copilot tab, which keeps it in memory only (never localStorage, sessionStorage, a cookie, a URL or a frontend variable) and sends it as `Authorization: Bearer`. The server compares SHA-256 digests in constant time and never logs or returns it. A missing or short token closes the endpoint for everybody.
- **Strict Origin.** `Origin` must be present and in the CORS allow-list, which stops a foreign page and a DNS-rebinding page (a browser always sends it on a POST). Cookies were rejected: they reach every localhost page and need CSRF defences and server state.
- **Order, all before any database read, snapshot, reservation or provider call:** Origin, enabled, configured, throttle, token. The check is the first dependency of the route, so a refused request does not even create the Copilot service.
- **A small throttle of failed attempts:** a bounded (10 entries, 60 s), in-memory, process-local window with no database writes. After 10 failures every request, the correct token included, is refused until the oldest failure leaves the window. It only adds a refusal; the token's entropy is the real protection. Trade-off: someone who can reach the API can lock the operator out for at most one window.
- **Contract.** `POST /api/ai/copilot/ask` with `{question}` and nothing else; `GET /api/ai/copilot/status` returns only `{"available": bool}`. The response carries the answer, whether it was cut off and the snapshot facts (`captured_at`, `data_status`, `truncated`, `limitations`, `omitted`, `named_drones`) taken from the server, never from the model; no cost, token count, provider id or raw context. Errors are `{code, message}` with fixed messages and fixed statuses (403, 503, 401, 429, 422, 413, 409, 502, 500); no exception text, prompt or credential reaches a response or a log.
- **One request, no retry, no idempotency store.** One gateway call per question; the gateway's 30 s gap and one-in-flight rule already cap paid calls however many times a POST is repeated (a double click, a reload, a browser retrying on a stale socket). The frontend ignores a submission while one is pending and never retries; an unclear outcome (provider timeout or 5xx, lost connection, unreadable success) is shown with a warning that the request may have been charged and must not be retried until the ledger and the provider Console have been checked.
- **Same Settings.** The Copilot service builds the gateway and the fleet context from one `Settings` object.
- **The question and the named drones** (Feature 025's service): one line, the words "fleet context" refused, up to eight `DRN-n` ids ranked right after the flagged drones and reported as `exists`/`listed` (snapshot schema 2).
- **Frontend.** A fifth Operations tab whose state lives above the tabs, so neither a tab switch nor a map selection loses a draft, an answer or a request on its way; nothing is sent on load, tab opening or navigation (only the harmless availability probe when the tab is first shown); the answer is a plain text node.

## Consequences

- Enabling the Copilot is deliberate: `SKYFLEET_AI_ENABLED=true`, a provider key and the operator token in `backend/.env`, then an API restart (a `.env` change does not trigger its reload). Disabling is the reverse.
- The token is one shared secret for one local operator; accounts, roles, sessions and remote access are out of scope, and the backend stays bound to `127.0.0.1`. Anyone who can read `backend/.env` can read the key as well.
- The first real request that carries a fleet context needs the owner's approval: its real token count validates the reservation bound, and the Console spend limit stays the real provider cap.
- Malformed JSON from an unauthenticated caller gets a generic 422 (FastAPI parses the body before dependencies); it reveals nothing and touches no database, service or provider.

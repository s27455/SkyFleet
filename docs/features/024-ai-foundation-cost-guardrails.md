# Feature 024 — AI Foundation & Cost Guardrails

**Project:** SkyFleet MVP  
**Status:** Finalized (2026-11-15). Foundation implemented and verified offline and on PostgreSQL; migration `0019` applied to the development database; ONE paid smoke test succeeded (owner-observed and checked in the ledger). AI remains disabled by default and is wired to nothing: no endpoint, no agent, no tools.
**Priority:** Security and cost containment  
**Scope:** Backend foundation only; no chat UI or paid model requests in this feature unless explicitly approved later.

## Goal

Prepare a safe, minimal, read-only integration foundation for an Anthropic-powered operational assistant. The owner has purchased **USD 5 in prepaid API credits** for MVP demonstration. Prevent accidental or abusive API use through application-level protections. Do not assume prepaid credit, provider limits, or alerts constitute an absolute spending cap.

## Preconditions

- Verify that feature number 024 is available in the repository; report conflicts before changing files.
- Confirm Anthropic Console auto-reload is disabled (operator action; do not alter billing settings programmatically).
- Never request, print, log, commit, or expose the API key. Do not insert real credentials into prompts or source code.
- Keep the integration disabled by default until configuration and safety tests pass.

## Gate A — Read-only investigation (first action)

Inspect current FastAPI settings, dependency management, service architecture, environment templates, `.gitignore`, logging, test patterns, authentication/access controls, and deployment assumptions. Determine whether the backend can be reached by untrusted clients. Check the current official Anthropic API documentation for a supported economical Haiku model, Messages API request/response usage accounting, pricing, timeout behavior, and SDK support. Do not guess model IDs or pricing.

Deliver an architecture proposal, exact file list, threat/cost analysis, test plan, and Gate B implementation steps. **Stop for explicit approval.** No edits, installs, service restarts, commits, migrations, or paid API calls in Gate A.

## Gate B — Proposed implementation (approval required)

### 1. Configuration and secret hygiene

- Server-side environment configuration: `SKYFLEET_AI_ENABLED=false` by default, Anthropic API key, model ID, input/output token ceilings, request timeout, rate limits, and budget controls.
- Never expose the key to frontend bundles or API responses. Add only placeholder variable names to an environment example; ensure real `.env` files are Git-ignored.
- Startup should not fail when AI is disabled and no key is set. When enabled but misconfigured, fail closed with an understandable diagnostic that contains no secret.

### 2. Fail-closed gateway

- Centralize Anthropic calls behind one backend service/interface, with a mockable transport.
- Do not implement direct browser-to-Anthropic requests, arbitrary tools, shell execution, database writes, or model-directed API actions.
- Enforce a fixed allowlist of models and hard upper bounds for request text, prompt/context size, and output tokens.
- Restrict request concurrency and enforce a global server-side request quota (initial proposal: 10 requests/hour), plus a short cooldown per caller where caller identity is reliably available.
- Prevent unlimited retries. Handle timeouts, rate limits, invalid credentials, insufficient credits, and upstream outages safely.
- Protect any eventual AI endpoint from anonymous public abuse; investigate existing authentication first. If no safe access control exists, leave the endpoint disabled until one is implemented.

### 3. Spending guardrails

- Define a conservative application-side **USD 4 estimated spend ceiling**, retaining approximately USD 1 of the prepaid balance as buffer. This is a project-side safety threshold, not a guarantee of billing outcomes.
- Check and reserve a pessimistic maximum cost *before* making each call, based on bounded input and output tokens and current documented prices. Use atomic reservation so concurrent requests cannot overrun the local budget.
- Reconcile reservations against provider-reported usage after successful calls. For ambiguous failures/timeouts, account conservatively rather than automatically refunding unknown spend.
- Define restart-safe persistence for budget accounting before enabling paid calls. Investigate the smallest suitable persistence mechanism and whether it needs a migration; **do not implement a migration without separate approval**.
- Fail closed if accounting persistence is unavailable or inconsistent. Record safe operational metrics (request counts, token usage, estimated costs) without logging prompts, responses, credentials, or personal data.
- Document that pricing can change and that Anthropic Console billing controls must be checked separately.

### 4. Tests (no paid API calls)

- AI disabled and missing key; malformed configuration; secret redaction.
- Rate limiting, request size, output-token cap, concurrency, and cost-reservation race conditions.
- Exhausted budget, accounting-store failures, restart persistence, ambiguous timeout accounting, and upstream errors.
- Verify that all tests use mocks/fakes and cannot contact Anthropic.
- Existing backend tests and lint/type checks remain passing, with any pre-existing issues reported separately.

## Acceptance criteria

1. Default SkyFleet behavior remains unchanged when AI is disabled.
2. No API key appears in frontend code, logs, Git history, HTTP errors, or tests.
3. No paid call is possible without explicit enabling and valid configuration.
4. Enforced request/token/concurrency limits and conservative, restart-safe budget checks are tested.
5. AI integration is read-only and cannot execute actions in SkyFleet.
6. No new UI is required for this feature.
7. Full implementation report documents limitations, assumptions, and the operator's steps for safe activation.

## Out of scope

- Chat UI, conversation history, retrieval/search, vector databases, autonomous actions, agent tools, public access, deployment, and actual paid smoke tests.
- Fleet context construction (Feature 025), chat interface (026), suggested questions (027), and end-to-end hardening/demo QA (028).

## Later rollout

**025** Fleet Context & Read-Only Intelligence → **026** AI Copilot Chat UI → **027** Operational Insights & Suggested Questions → **028** AI Copilot Hardening & Demo QA. Confirm numbering against repository before creating additional specs.

## Operator safety checklist

- Anthropic Console: auto-reload OFF; confirm current credit balance and available billing alerts/limits.
- Create a dedicated SkyFleet key and keep it secret. If exposed, revoke and rotate it immediately.
- Do not place credentials in Claude Code prompts or chat transcripts.
- Do not enable AI until the read-only architecture review, cost controls, and tests are approved.

## Gate B1 record (2026-11-15)

### Verified against the official documentation (fetched 2026-11-15; no discrepancy found)

- Model `claude-haiku-5-5` (a pinned snapshot, no date suffix), 1M context, 128K output; adaptive thinking by default and it accepts `thinking: {"type": "disabled"}`.
- Prices per million tokens: prompts up to 100,000 tokens $0.10 input, $0.50 output, $0.01 cache read, $0.125 / $0.20 cache write (5 min / 1 h); prompts over 100,000 tokens $0.50, $2.50, $0.05, $0.625 / $1. The prompt length counts cache reads and writes.
- Python SDK `anthropic` 2.8.0 (installed; `httpx2` is its HTTP library). Errors expose `status_code`, `type`, `error_code` and `request_id`, and the SDK says not to match on message wording. A spend-cap 429 has no `retry-after`.

### MVP limits (all enforced; settings can only tighten them)

16 KiB total model input (system instructions, context and question, measured in UTF-8 bytes of what is sent); question at most 500 characters; output at most 400 tokens; 10 requests per hour globally; at least 30 s between any two requests; one provider request in flight; internal lifetime ceiling USD 4.00; SDK retries off; AI disabled by default; request timeout 30 s; a 15-minute back-off after a key, balance, spend-limit or invalid-request failure.

### What was built (`backend/app/ai/`, no endpoint, nothing calls it)

- `pricing.py`: the allowlist; the model id and its prices live in one structure (integer nano-USD per token), with the date they were verified; entries older than 90 days make the gateway refuse until someone re-verifies them.
- `request.py`: the fixed read-only system prompt, the request builder and the size limits; documents the three assumptions behind the token bound (below).
- `anthropic_transport.py`: the only SDK import; `max_retries=0`, a fixed base URL (an `ANTHROPIC_BASE_URL` can never redirect the key), the key passed explicitly from a `SecretStr`, no tools, no `tool_choice`, no streaming, `thinking` disabled, errors classified only from status, type and code.
- `readiness.py`: every configuration problem, by setting name only (never a value or a secret); nothing is checked while AI is disabled, so a missing key never stops the API or the worker.
- `budget.py` and `models.py`: the durable accounting (below). `gateway.py`: the single entry point `AiGateway.ask(question, context)`. `errors.py` and `types.py`.
- `config.py`: the AI settings under the spec's names (`SKYFLEET_AI_ENABLED`, `SKYFLEET_AI_MODEL`, ... and the standard `ANTHROPIC_API_KEY`), `SecretStr` for the key with `repr=False`.

### Budget-safety design

- **Reservation before every call.** In one transaction `reserve` locks the single budget row (`SELECT ... FOR UPDATE`), sweeps abandoned reservations, verifies the books, checks the limits and the ceiling, adds the worst-case cost to `reserved` and writes a `RESERVED` log row. The lock is held to the commit, so two requests cannot pass the same check. Nothing is sent unless that commit succeeded; a database error means no request (`AccountingUnavailableError`).
- **Worst case per request.** Reserved input tokens = the UTF-8 bytes of everything sent + 1,024 allowance for the provider's framing; plus the full 400 output tokens. For the largest request that is 17,408 x $0.0000001 + 400 x $0.0000005 = $0.0019408; the $4 ceiling pays for 2,061 of them, and the hourly quota allows at most 10 per hour (about $0.019 per hour, $0.47 per day, at the very worst).
- **Settlement.** Success: the provider-reported cost is charged and the rest released. Rejected before generation (401, 402, 403, 400/404/413/422, any 429): refunded. Unclear (timeout, dropped connection, 5xx, 529, unclassified): the whole reservation stays as spent, never refunded on a guess. An unsettled reservation older than the timeout plus 60 s (a crash) is swept to `UNKNOWN` and charged in full. A late report of a swept request can only add cost, never lower the charge.
- **The assumptions are checked, not trusted.** The bound assumes (A1) a token covers at least one byte, (A2) the provider's framing adds fewer than 1,024 tokens for a tool-free request and (A3) the prompt stays below the 100,000-token price tier. None is guaranteed in writing, so the provider's own prompt and output token counts are compared with the reservation after every call: if either is exceeded the real cost is charged, the budget row is halted (`ESTIMATE_EXCEEDED`) and every later request is refused until a person looks. A wrong assumption therefore costs at most one request.
- **The books must agree.** `spent` must equal the sum of the charged amounts and `reserved` the sum of the held reservations; on every reservation this is verified and a mismatch (a hand edit, a deleted log row) halts the store (`ACCOUNTING_INCONSISTENT`).
- **Failure handling.** A failed settlement never hides an answer or a provider error; the reservation simply stays held and the next sweep charges it in full, so the books can only become more conservative.
- **What is stored and logged:** numbers and fixed codes only (token counts, nano-USD, status, model, byte size, an error kind, the provider request id). No key, prompt, context or answer is stored or logged; the tests search the tables and the log output for markers to prove it.

### Proposed migration (draft, NOT applied): `backend/migrations/drafts/0019_ai_budget.py`

It sits outside `migrations/versions/`, so Alembic cannot see it (`alembic heads` is still `0018`); promoting it is a Gate B2 step with its own approval. It adds two tables and changes nothing else.

`ai_budget_state` (one row, `name = 'anthropic'`, created by the gateway on first use; nothing is seeded)

| Column | Type | Null | Default |
|---|---|---|---|
| `name` | varchar(32), primary key | no | |
| `spent_nano_usd` | bigint, check >= 0 | no | 0 |
| `reserved_nano_usd` | bigint, check >= 0 | no | 0 |
| `halted` | boolean | no | false |
| `halt_reason` | varchar(64) | yes | |
| `updated_at` | timestamptz | no | |

`ai_request_log` (one row per attempt; never deleted)

| Column | Type | Null | Default |
|---|---|---|---|
| `id` | integer, primary key, autoincrement | no | |
| `created_at` | timestamptz | no | |
| `finished_at` | timestamptz | yes | |
| `model` | varchar(64) | no | |
| `status` | varchar(16), check in ('RESERVED','SUCCEEDED','REJECTED','AMBIGUOUS','UNKNOWN') | no | |
| `request_bytes` | integer | no | |
| `reserved_nano_usd` | bigint, check >= 0 | no | |
| `charged_nano_usd` | bigint, check >= 0 | no | 0 |
| `prompt_tokens` | integer | yes | |
| `output_tokens` | integer | yes | |
| `error_code` | varchar(48) | yes | |
| `provider_request_id` | varchar(64) | yes | |

Indexes: `ix_ai_request_log_created_at (created_at)` and `ix_ai_request_log_status_created_at (status, created_at)`. Downgrade drops both tables (and with them the spend history).

### Test isolation (no real credentials, no network)

A suite-wide autouse fixture removes the AI environment variables for every test, makes constructing a real `anthropic.Anthropic` client fail, and fails any connection to a non-loopback address (the local PostgreSQL stays reachable). The AI tests build their settings with `_env_file=None`, a fake key and fake transports only. An architecture test checks that `app/ai` imports no domain module, that the SDK is imported by one module, that nothing outside `app/ai` uses it and no AI route exists, and that no key-shaped string is in the repository.

### Open items for Gate B2

PostgreSQL concurrency and restart tests against a temporary database (they need the migration promoted); the ADR and architecture note; a change to the existing schema guard `tests/hubs/test_migrations.py` that already expires the draft-table exception once `0019` is in `versions/`; adding the placeholder lines to `backend/.env.example` (see below); a re-verification of the prices and the model id against the official documentation immediately before AI is ever enabled; any paid smoke test needs its own approval.

`backend/.env.example` could **not** be edited in this gate: this project's permission settings deny edits to environment files, and that was respected. The lines to add by hand (placeholder names only, no values) are:

```
# --- AI assistant (Feature 024): OFF by default. Placeholder names only, never real values. ---
# Put the real key ONLY in your local, Git-ignored backend/.env. Never commit it, never paste it
# into a chat or a prompt, and never set ANTHROPIC_LOG=debug.
SKYFLEET_AI_ENABLED=false
# ANTHROPIC_API_KEY=
# SKYFLEET_AI_MODEL=claude-haiku-5-5
```

### Verification (offline)

Backend ruff and format clean; `mypy .` reports one error in the unmodified `tests/weather/test_rain_warning.py:208` (pre-existing); `pytest` 1260 passed (143 new AI tests and one for the schema-guard exception); `pytest -m postgres` 70 passed. Mutation checks: disabling the estimate-exceeded breaker, the books verification, or the no-retry setting each makes tests fail. The development database is unchanged (revision 0018, no AI tables) and the API stayed healthy.

## Gate B2 record (2026-11-15)

### Preflight (all passed)

- Target: the Docker PostgreSQL `skyfleet` on localhost:55432 (user `skyfleet`), the database `DATABASE_URL` resolves to; Alembic revision `0018`, one head; a metadata comparison against the models showed no drift; the working tree held only the Gate B1 changes; `ai_enabled` false and no key configured.
- Found and fixed in this gate: `migrations/env.py` did not import `app.ai.models`, so once the tables existed Alembic's comparison would have reported them as unknown. It now imports them like every other model package.

### Backup (before the migration)

- File: `C:\Users\Tomek\skyfleet-backups\skyfleet_pre0019_20261115_134541.dump` (custom format, outside the repository), 662,876 bytes.
- SHA-256: `3b452881ffdefff575ad69a2f4786c6af6277939f0171b5b88a2a560c7e9ac92` (also saved beside it as `.sha256`); the checksum computed inside the container equals the one of the copied file.
- `pg_restore --list` read all 74 entries, including the data of `orders`, `drones`, `missions`, `hubs`, `drone_models` and `alembic_version`. No restore was performed.
- A first attempt failed (Git Bash rewrote `/tmp` inside the `docker exec` argument, so `pg_dump` could not open its output); it created nothing but an empty-file checksum stub, which was removed. The second attempt's copy was first created with a mangled file name and renamed; its checksum was then verified.

### Migration

- Migration `0019` was promoted from `migrations/drafts/` to `migrations/versions/0019_ai_budget.py` (docstring updated; the drafts folder is gone). The offline SQL (`alembic upgrade 0018:0019 --sql`) was reviewed first: two `CREATE TABLE`, two `CREATE INDEX` and the `alembic_version` update, in one transaction; nothing touches an existing table.
- Applied to the development database only; no downgrade, reset, reseed or truncate.
- Verified on PostgreSQL: revision `0019` (head); `ai_budget_state` and `ai_request_log` exist with their primary keys, the five CHECK constraints, both indexes and the defaults of the schema above; both tables are empty (0 and 0); a metadata comparison of the live database against the models shows 0 differences; no existing table lost rows (row counts compared with the snapshot taken before; `mission_flights`, `missions`, `operational_events` and `orders` grew by a few rows because the simulation worker keeps running; everything else identical); the API answered 200. An MD5 of the `orders` rows was not usable as an integrity check, because live orders change status while the simulation runs.
- Tests updated for the new head: `tests/hubs/test_migrations.py` (the temporary draft-table exception is removed; the AI models are imported so the schema comparison covers them), `tests/ai/test_ai_migration.py` (replaces the draft test: `0019` is the single head, revises `0018`, equals the models on SQLite, enforces its constraints, downgrades cleanly) and the two older round-trip tests that downgrade to `0017` / `0016` (`test_drone_recovery_postgres.py`, `test_random_incidents_postgres.py`), which now exclude the two AI tables from "nothing else changed" exactly as they already did for the migration above them.

### PostgreSQL concurrency and budget tests (`tests/ai/test_ai_postgres.py`, 16 tests, run on a temporary database, never on the development one)

Eight real threads released together against the real row lock: exactly one of eight simultaneous requests is granted (the rest are refused by the one-in-flight or interval rule) and exactly one row and one reservation exist; racing requests that settle every outcome as an unclear failure stop at exactly five granted for a ceiling of five reservations, with spent equal to the ceiling and nothing reserved; the hourly quota of three is never exceeded under a race; a stale reservation is charged exactly once when eight requests race to sweep it; a late settlement of a swept request cannot lower the charge; the budget survives disposing every connection (a restart) and is shared by two engines acting as the API and the worker; the CHECK constraints reject bad rows on PostgreSQL; the migrated schema equals the models; through the gateway an unclear failure (timeout, connection, server, overloaded, unknown) is charged in full, a rejection is refunded and a success charged exactly, and racing asks cause one provider call in total. All transports are fakes. Mutation check: removing the budget-row lock makes the ceiling and hourly-quota race tests fail on PostgreSQL in two runs (the one-at-a-time and stale-sweep tests still passed without it, so they are not the guard for that lock). Three consecutive runs of the file passed.

### Verification

Backend ruff and format clean; `mypy .` reports one error in the unmodified `tests/weather/test_rain_warning.py:208` (pre-existing, unrelated); `pytest` 1259 passed (86 PostgreSQL-marked deselected); `pytest -m postgres` 86 passed.

### Documentation

`docs/decisions/0012-ai-foundation-and-cost-guardrails.md` (new) and a paragraph in `context/architecture-context.md` §3.3. `context/progress-tracker.md` is left for the finalization step.

### Remaining risks and open items

- Only the budget-row lock is proven on PostgreSQL by the ceiling and quota race tests; a second lock layer (the log-row locks in the sweep and settlement) and timing explain why other races passed without it.
- The SDK timeout is per phase, not a total wall clock, so a pathologically slow response could outlive the 90 s stale cutoff; spend is still not undercounted (the sweep charges in full), only the one-in-flight guarantee would loosen.
- `backend/.env.example`: the edit is denied by the permission settings; add these lines by hand (placeholders only):

```
# --- AI assistant (Feature 024): OFF by default. Placeholder names only, never real values. ---
# Put the real key ONLY in your local, Git-ignored backend/.env. Never commit it, never paste it
# into a chat or a prompt, and never set ANTHROPIC_LOG=debug.
SKYFLEET_AI_ENABLED=false
# ANTHROPIC_API_KEY=
# SKYFLEET_AI_MODEL=claude-haiku-5-5
```

- Before AI is ever enabled: re-verify the model id and prices against the official documentation, set the Console spend limit (about USD 5) with auto-reload off, use a dedicated key stored only in `backend/.env`, and obtain approval for any paid smoke test. Wiring the gateway to an endpoint or agent needs authentication first and is a separate feature.
- The API (`--reload`) and the worker were not restarted; neither imports `app.ai`, so no restart is needed for this migration.

## Gate C1 record (2026-11-15)

### Stale-reservation risk: cause and fix

- **Cause.** A reservation older than `timeout + 60 s` (90 s) was swept to `UNKNOWN` and charged in full, which also emptied the in-flight count. The SDK timeout applies per phase (connect, write, read, pool), not to the whole call, so a slow response could outlive 90 s and a second provider request could start while the first was still active. Spend was never undercounted (the sweep charged in full); the one-at-a-time guarantee was what loosened.
- **Fix (two small changes, no background worker, no new table or migration).** (1) The lease is now `max(600 s, 4 x timeout + 60 s)`: the Anthropic SDK documents a 10-minute cap for non-streaming requests, and four phases at the transport timeout is the other bound (600 s at every timeout the readiness check allows). (2) A sweep no longer frees the slot: while any row was swept as `stale_reservation` less than one lease ago, `reserve` refuses with `ConcurrencyLimitError` (retry-after given). A second provider request therefore starts at least two leases (20 minutes) after an unsettled first one, never within the lease of one that may still be running. Cost of the safety: after a real crash the assistant is unavailable for up to about 20 minutes.
- **Accounting unchanged.** Success charges the real cost, rejection refunds, unclear failures and sweeps charge the full reservation, a late report only adds cost. A late report from a swept request moves the quarantine forward (conservative), never back.
- **Residual.** A connection that deliberately trickles bytes for more than 20 minutes would still be outside what the lease covers; the provider and SDK document a 10-minute ceiling, and a transport-level wall-clock watchdog was rejected as added threads and complexity.

### Re-verification against the official documentation (fetched 2026-11-15; no discrepancy)

Model `claude-haiku-5-5` is a pinned snapshot (the dateless ID is its own snapshot), 1M context, 128K max output, retirement not sooner than 7 October 2027, and it accepts `thinking: {"type": "disabled"}` (only `xhigh`/`max` effort or a per-message effort change are rejected, and the gateway sends no effort). Prices per million tokens for prompts up to 100,000 tokens: input $0.10, output $0.50, cache read $0.01, cache write $0.125 (5 min) / $0.20 (1 h); over 100,000 tokens: $0.50, $2.50, $0.05, $0.625, $1. All equal the allowlist entry. The 1.1x US-only multiplier applies only when `inference_geo` is sent, which the transport never does. A user-set Console spend limit returns 400; a tier spend-cap 429 has no `retry-after`; both are classified as before. `max_tokens` and the other request fields are unchanged.

### Tests

New: lease value and hand-off to the budget; the slot stays closed one more lease after a sweep (with the exact retry-after); no grant within two leases of an unsettled request (probe every 7 s over three leases); a late report does not reopen the slot early; a gateway-level regression where the first provider call stays in the air while a second caller asks at 100, 590, 700 and 1,250 s (all refused, one provider call in total at 1,301 s, the first request charged in full as `UNKNOWN`); PostgreSQL: eight racing threads against a stale reservation charge it once and start nothing, and exactly one request starts after the quarantine. Mutation checks: restoring a 90 s lease or removing the quarantine makes these fail.

### Verification (offline, fake transports only)

Backend ruff and format clean; `mypy .` reports one error in the unmodified `tests/weather/test_rain_warning.py:208` (pre-existing, unrelated); `pytest` 1265 passed (86 PostgreSQL-marked deselected); `pytest -m postgres` 86 passed on temporary databases. The development database was not written to by this gate (Alembic `0019`, both AI tables still empty). No service was restarted.

### Gate C2 inputs

A one-off script (outside the repository) was drafted and dry-run only in the two modes that cannot send or touch the database (missing authorization flag, and AI disabled). Cost of the single test request: at most USD 0.00033390 reserved with the default 400-token output cap, USD 0.00014990 with `SKYFLEET_AI_MAX_OUTPUT_TOKENS=32`; the expected real cost is about USD 0.00001 to 0.00005. `backend/.env.example` remains protected; the manual lines are listed in the Gate B2 record.

## Gate C2 preparation (2026-11-15)

- **Temporary files (untracked; both are deleted at the end of Feature 024, never committed):** `backend/tmp_gate_c2_smoke_test_024.py` and `backend/tests/ai/test_ai_smoke_script.py` (the tests skip themselves once the script is gone).
- **Command (from `backend/`, key in the Git-ignored `backend/.env`):** `SKYFLEET_AI_ENABLED=true uv run python -m tmp_gate_c2_smoke_test_024 --yes-send-one-paid-request`. Two independent keys are needed: AI enabled for that one process by the environment variable (every persistent configuration keeps it `false`) and the explicit flag.
- **Behavior:** one `AiGateway.ask` call; no loop, retry, fallback, thread or background task (a static test of the file enforces one `ask`, no loop, no threading, asyncio, subprocess or HTTP-library import, no use of the key, no `os.environ` writes). The question is a fixed constant (`Reply with exactly the single word: OK`) and the output is hard-coded to 32 tokens (a settings copy, not persisted). It refuses, in order, without the flag (2), while `ANTHROPIC_LOG` is set (7), when AI is not enabled for the process (3), on any readiness problem (4: key missing, model not on the allowlist, stale prices, a limit above its maximum; names only), when the budget cannot be read (6) and when the gateway is halted (5); exit 1 if the one request fails, 0 on success. It prints only ids, token counts, costs, codes and the short reply.
- **Maximum reservation:** USD 0.00014990 (149,900 nano-USD: 315 request bytes + 1,024 allowance = 1,339 reserved input tokens at $0.10/MTok plus 32 output tokens at $0.50/MTok). It is an application-level estimate computed from our price table and token bound, not a billing guarantee; the provider's own token counts are checked against it after the call and a violation charges the real cost and halts the gateway.
- **Verified without sending:** 13 new tests (every refusal path, exactly one request of at most 32 tokens with the fixed prompt, a failed request is not repeated and is charged conservatively, the key never appears in any output, the structural checks); a mutation check (a retry loop around `ask`) makes two of them fail; the real module was run in four modes that cannot send (no flag; flag with AI disabled; flag with AI enabled for the process but the key forced blank; `ANTHROPIC_LOG` set) and the development ledger stayed empty.
- **Still open for Gate C2:** the owner configures the key and the Console limits, then explicitly approves the single request; afterwards the temporary files are removed and the Gate C2 result is recorded.

## Gate C2 result and finalization (2026-11-15)

### The one paid smoke test

Run by the owner with the temporary script (AI enabled for that one process only, flag required, output capped at 32 tokens, fixed prompt `Reply with exactly the single word: OK`). Reported result: model `claude-haiku-5-5`, reply `OK`, 109 input and 4 output tokens, charged USD 0.00001290, ledger row 1, nothing reserved afterwards, gateway not halted.

Verified afterwards with read-only queries on the development database: `ai_request_log` holds exactly one row, `SUCCEEDED`, model `claude-haiku-5-5`, 315 request bytes, reserved 149,900 nano-USD (the documented maximum, USD 0.0001499), charged 12,900 nano-USD (= 109 x 100 + 4 x 500, the allowlist prices), 109 prompt and 4 output tokens, no error code, a provider request id recorded; `ai_budget_state` holds one row (`anthropic`): spent 12,900, reserved 0, not halted. The books agree (sum of charged = spent, held reservations = reserved). The real cost was 0.9 % of the maximum reservation, so the estimate was a safe, loose upper bound for this request. The Anthropic Console figures were checked by the owner, not by the implementer.

### Cleanup and configuration

- The temporary script `backend/tmp_gate_c2_smoke_test_024.py` and its tests `backend/tests/ai/test_ai_smoke_script.py` were deleted and never committed. No other Anthropic call was made.
- AI is disabled by default: the code default of `ai_enabled` is false and the effective value with the local `backend/.env` is false (checked as booleans only; the key was never read or printed). A key is present in the Git-ignored `backend/.env`; the owner decides whether to keep or revoke it.
- `backend/.env.example` could not be edited by the implementer (permission settings deny it); the owner added the placeholder-only AI lines themselves (`SKYFLEET_AI_ENABLED=false`, commented `ANTHROPIC_API_KEY=` and `SKYFLEET_AI_MODEL=claude-haiku-5-5`), which the final review confirmed.

### Final verification (offline, fake transports only; the real client and any non-loopback connection are blocked in tests)

Backend ruff and format clean; `mypy .` reports one error in the unmodified `tests/weather/test_rain_warning.py:208` (pre-existing, unrelated); `pytest` 1265 passed (86 PostgreSQL-marked deselected; 149 of them in `tests/ai`); `pytest -m postgres` 86 passed on temporary databases (16 of them the AI budget concurrency tests). Alembic is at `0019` (head).

### Known limits and follow-ups

- Nothing calls the gateway. The Fleet Operations Agent, tools, an endpoint and any UI are separate features; an endpoint needs authentication first (the API has none).
- After a crash during a request the assistant is closed for about 20 minutes (lease plus quarantine, see Gate C1).
- Prices and the model id were verified on 2026-11-15; the gateway refuses prices older than 90 days, and they must be re-verified before AI is enabled again after that.
- The Console spend limit and auto-reload settings are the real provider-side cap and are the owner's to maintain; the internal USD 4 ceiling is an application-level limit.
- A halted gateway (`ai_budget_state.halted`) stays closed until a person clears it; there is no tool for that yet (a direct, deliberate database update).
- `ai_request_log` is never pruned (at most 10 rows per hour).

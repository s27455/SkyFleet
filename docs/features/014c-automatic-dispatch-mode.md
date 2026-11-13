# Feature 014C — Automatic Dispatch Mode

**Status:** Implemented (backend and frontend) and verified by automated tests, including concurrency tests on PostgreSQL; the full loop was not run end to end by the implementer and QA and code-review agents were not run. Committed in `5556be1`.

## Implementation notes (verified)
- Loop owner: the Simulation Worker. The API (toggle) and the worker (loop) are separate processes, so the mode is stored in the database: new table `dispatch_auto_state` (migration 0006, one row `auto-dispatch`; no row means OFF). Code: `backend/app/dispatch/{auto,models}.py`, `backend/app/worker.py`, `backend/app/config.py`, `backend/app/dispatch/schemas.py`, `backend/app/api/routes/dispatch.py`.
- The worker resets the mode to OFF when it starts and runs no pass until that reset has succeeded. The API does not reset it. While ON, the worker runs a pass every `DISPATCH_AUTO_INTERVAL_SECONDS` (default 3). A pass takes the 014A recommendations and executes each pair with the 014B `execute_dispatch`; the stored mode is read again before every execution, so turning it OFF stops further attempts while a running execution may finish. Flights and missions already started are never touched.
- Endpoints: `GET /api/dispatch/auto/status` (`enabled`, `worker_running`, `last_check_at`, `last_outcome`), `POST /api/dispatch/auto/enable` and `POST /api/dispatch/auto/disable` (both idempotent). Enable returns 503 `SIMULATION_WORKER_UNAVAILABLE` when the worker heartbeat is stale; the reported `enabled` is true only while the mode is ON and the worker heartbeat is fresh.
- Failures are controlled one-line outcomes: a mission whose start failed stays `ASSIGNED` and is reported (no automatic cancellation); a stale worker stops the pass; one failing pair does not stop the others. The outcome is logged only when it changes.
- Frontend: a compact Auto dispatch switch in the header (`frontend/src/features/dispatch/AutoDispatchControl.tsx`, `src/api/dispatch.ts`, `src/types/dispatch.ts`). It shows the server-reported mode and last outcome, re-reads the status regularly, never flips before the backend confirms, ignores repeated clicks while a change is pending, and shows backend errors, a worker-not-running warning, and loading and error states.
- Decisions (confirmed by the product owner): worker-owned loop with database-backed state and migration 0006; reset to OFF on worker startup only; enable refused when the heartbeat is stale; the planner is used unchanged and return-Hub capacity is not reserved.

## Verification
- Passed: default backend suite 385 passed (20 PostgreSQL-marked tests deselected); `pytest -m postgres` 20 passed on the local Docker PostgreSQL in a temporary database, including migration 0006 and four overlapping passes starting exactly four missions with no drone or order started twice; `ruff`, `ruff format --check` and `mypy` clean. Frontend: 369 tests passed, `typecheck`, `lint`, `format:check` and the production build clean. New tests: 24 default backend, 3 PostgreSQL, 12 frontend. One existing test helper (`App.test.tsx`) was extended to answer the new status URL.
- Live-test finding: on the development database the status endpoint returned 500 because migration 0006 had not been applied (`relation "dispatch_auto_state" does not exist`); the browser then reported CORS errors because an unhandled 500 carries no CORS header. `alembic upgrade head` was applied to the development database (additive: one empty table; no data changed) and the endpoint then returned 200 with the mode OFF.
- Not run: the QA and code-review agents; an end-to-end run of the loop (enable, observe an automatic start, disable) and a browser check by the implementer; the manual demo checklist is still to be walked through by the operator.
- Known limitations: a worker started before this feature has no loop and must be restarted (which also resets the mode to OFF); if the worker process is down no dispatch happens at all, and restarting it resets the mode, so the operator turns it ON again; only drones at exactly 100% battery can be dispatched and nothing recharges them yet (014D); a mission whose start failed blocks that order and drone until the operator starts or cancels it; two workers running by mistake would not create duplicates (014B locks) but would do redundant work.

## Goal
Enable an operator-controlled automatic dispatch loop that continuously processes eligible orders across independent Hubs using the existing 014A recommendation logic and 014B execution logic. Keep the implementation small, observable, and safe for an MVP demo.

## Existing components to reuse
- **014A:** `GET /api/dispatch/recommendations` and the recommendation service (per-Hub FIFO, deterministic candidate selection, 100% battery requirement, planner validation).
- **014B:** `POST /api/dispatch/execute` and its service (revalidation, locking, duplicate prevention, worker availability checks, mission creation and start).
- Existing FastAPI application, simulation worker, API client, and frontend styling/patterns.

Before coding, inspect how the backend and simulation worker are started. Choose **one** owner for the dispatch loop; do not run independent competing loops in the API and worker. Prefer the smallest reliable integration with the current architecture, and explain the choice in the Initialize plan.

## Operator behavior
1. Automatic Dispatch is **OFF by default**, including after a backend/worker restart. No dispatch may occur just because the application starts.
2. An operator can turn Automatic Dispatch **ON/OFF** from a small frontend control. The UI displays the current server-reported mode, not an assumed local value.
3. When ON, the system periodically evaluates eligible orders across all Hubs and attempts to execute recommendations. Each Hub has its own FIFO priority; an unavailable Hub never blocks others.
4. When OFF, the system stops scheduling **new** automatic dispatches. Already started flights continue normally; switching OFF must not cancel missions.
5. The operator can see basic status: ON/OFF, last attempt/check, and a concise outcome or error. Refreshing the page must reflect actual server state.
6. Manual mission operations remain available and unchanged.

## Dispatch rules
- Reuse 014A for selection and 014B for execution; **do not duplicate** planner, energy, capacity, or mission-start logic.
- Only 100%-charged, physically docked, IDLE drones without active missions can be dispatched; 014B must revalidate at execution time.
- Process recommendations deterministically. Attempt independent eligible pairs without globally blocking other Hubs.
- An unserviceable order remains pending; it does not block other feasible orders. Avoid tight retry loops or repeatedly generating excessive logs for the same blocked order.
- A failed or stale recommendation is handled as a controlled outcome; the next periodic pass can reassess current state. Do not introduce automatic cancellation, manual-recovery bypasses, or a new compensation framework.
- Never start the same order or drone twice, including overlapping ticks, repeated ON requests, concurrent API calls, or manual operations. Preserve existing 014B transaction/locking guarantees.
- Respect the existing planner's return-Hub behavior **unchanged**. For this MVP assume sufficient landing capacity; do not add reservations, virtual occupancy, saturation management, or relocation.

## Suggested minimal API (adapt to existing conventions)
- `GET /api/dispatch/auto/status` — server-reported enabled flag and minimal operational information.
- `POST /api/dispatch/auto/enable` — explicitly enable automatic mode; idempotent.
- `POST /api/dispatch/auto/disable` — explicitly disable automatic mode; idempotent.

Use a single backend source of truth for mode and loop ownership. For the MVP, process-local state is acceptable **only if** the application runs in a documented single-owner configuration and restarts reliably reset to OFF. Do not silently rely on independent in-memory toggles across multiple processes. If the existing architecture requires a different minimal mechanism, present that choice in the Initialize plan before implementation.

## Frontend scope
- Add a compact Auto Dispatch ON/OFF control and status indication to an existing relevant screen, following current UI conventions.
- Show loading and error states; do not optimistically claim mode changed before the API confirms it.
- Refresh status on page load and periodically while the screen is open.
- Optional: show last dispatch outcome if readily available from the status endpoint. **No** new dashboard, complex queue editor, or manual assignment form in this feature.

## Worker and lifecycle safety
- Check worker availability through existing 014B behavior. If the simulation worker is unavailable, do not create stuck missions or crash the loop; expose a concise status/error and retry on a later tick while enabled.
- Do not let an unhandled exception permanently kill the dispatcher.
- Avoid CPU-heavy polling; use a modest, configurable interval suitable for a demo (e.g., 2–5 seconds). Do not introduce a message broker or external scheduler solely for this MVP.
- Ensure start/stop and shutdown behavior is deterministic. No dispatch when mode is OFF.

## Acceptance criteria
1. With mode OFF, new ready orders remain untouched even while the backend and worker run.
2. Turning ON causes an eligible order to be assigned and started automatically without Swagger/manual execution.
3. Multiple Hubs are independent; no ready drone at Hub A does not prevent dispatch at Hub B.
4. Per-Hub FIFO is respected for feasible orders; temporarily unserviceable orders do not block other feasible orders.
5. A drone at 99% battery, in MAINTENANCE/CHARGING/IN_FLIGHT, or already assigned is never automatically dispatched.
6. Two eligible orders and two eligible drones can be processed without duplicate drone/order assignment.
7. Repeated enable/disable requests and overlapping ticks do not cause duplicate missions.
8. Turning OFF prevents further new automatic dispatches while in-progress flights continue.
9. Restart resets mode to OFF and the UI reflects it.
10. Worker unavailable: no stuck new mission; status exposes the problem; operation can resume after worker recovery without requiring a code change.
11. Existing 014A/014B APIs, manual mission operations, and flight simulation continue working.

## Testing and verification
- Focused backend tests: OFF default, ON/OFF idempotency, independent Hubs, FIFO, blocked orders, battery/status exclusions, worker unavailable, overlapping ticks, restart behavior.
- Integration test using existing PostgreSQL concurrency coverage where needed; do not replace 014B locking with new logic.
- Minimal frontend test for toggle/status and API error handling if existing test infrastructure supports it.
- Run required repository quality checks; avoid unrelated refactors and optional duplicate agent reviews unless mandated by workflow.
- Provide a short manual demo checklist: start API + worker, verify OFF, create eligible order, enable, observe automatic start, disable, verify no further new starts.

## Explicit non-goals
- Automatic battery charging (014D).
- Fleet rebalancing/relocation (014E).
- New return-Hub capacity management.
- AI incident response, route optimization, or a new mission planner.
- A comprehensive management dashboard or manual dispatch UI.
- Background auto-dispatch enabled on startup.

## Workflow and checkpoints
1. **Initialize:** inspect only relevant code, propose the minimal loop owner/state approach and API/UI touchpoints, list files and tests, then **stop for approval**.
2. **Start Implementation:** implement only approved scope, run focused checks, and **stop for review**; do not commit yet.
3. **Finish:** only after explicit approval, follow the repository's existing Finish workflow and report commit/status.

## Implementation note
The exact dispatch loop ownership and state storage must be confirmed from the repository during Initialize; do not assume a single-process API if the current runtime uses multiple workers or a separate simulation process.

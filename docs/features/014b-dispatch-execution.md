# Feature 014B — Dispatch Execution

**Status:** Implemented (backend only) and verified by automated tests, including concurrency tests on PostgreSQL; QA and code-review agents not run. Not committed.

## Implementation notes (verified)
- Endpoint `POST /api/dispatch/execute` with body `{order_id, drone_id}`; 201 returns the existing mission response (status `IN_FLIGHT`). Code: `backend/app/dispatch/service.py` (`execute_dispatch`), `backend/app/dispatch/schemas.py`, `backend/app/api/routes/dispatch.py`; tests: `backend/tests/dispatch/test_dispatch_execution.py` (SQLite) and `backend/tests/dispatch/test_dispatch_postgres.py` (opt-in `-m postgres`). No migration.
- Flow: check the order and drone exist (404); refuse if the order already has an active mission (409 `DISPATCH_ALREADY_ASSIGNED`, with the mission id); refuse when the worker heartbeat is stale before creating anything (503 `SIMULATION_WORKER_UNAVAILABLE`); call the existing `confirm_mission` (row locks, planner revalidation, unique active-mission indexes); call the existing `start_mission`.
- The 100% battery rule is enforced inside `confirm_mission` under the row lock through a new optional `require_full_charge` argument (default off, so manual missions are unchanged), raising `DroneNotFullyChargedError` (409 `DRONE_NOT_FULLY_CHARGED`). Planner rejections return 409 `MISSION_NOT_ELIGIBLE` with the planner's reasons. This is the only change to existing mission code (`backend/app/missions/service.py`).
- Failed start: `start_mission` writes only in its final transaction and rolls back on any error, so a failure means no flight began. The mission is kept `ASSIGNED` and the error (409 `DISPATCH_START_FAILED`) names it and points to the existing `POST /api/missions/{id}/start` and `/cancel` endpoints. A retry for the same order gets `DISPATCH_ALREADY_ASSIGNED`, so no duplicate is created. Only expected errors are described to the client; unexpected ones are reported as "unexpected error".
- Ambiguous outcome: if a commit errors after the database applied it, the mission's real status is re-read and an `IN_FLIGHT` mission is reported as started. There is no retry or compensation framework.
- Decisions (confirmed by the product owner): no automatic cancellation of a mission whose start failed; no FIFO enforcement in this endpoint (selection belongs to 014A and 014C); the planner is used unchanged and return-Hub capacity is not reserved.

## Verification
- Passed: default backend suite 361 passed (17 PostgreSQL-marked tests deselected); `pytest -m postgres` 17 passed on the local Docker PostgreSQL in a temporary database; `ruff`, `ruff format --check` and `mypy` clean. 22 tests are new: 18 on SQLite (success, each rejection creating no mission, unknown ids, no worker, repeated request, failed start kept `ASSIGNED` and recoverable by a manual start, start that committed before erroring, manual missions still accepting a drone below 100%, recommendations unchanged) and 4 on PostgreSQL (two drones for one order, two orders for one drone, eight identical requests, independent pairs, each racing real sessions: exactly one mission starts).
- Not run: QA and code-review agents; the endpoint was not called against the development database (it would start a real flight); no manual Swagger run.
- Known limitations: nothing recharges drones yet (014D), so only drones at exactly 100% can be dispatched; return-Hub landing places are not reserved.

## Goal
Execute a selected dispatch recommendation safely on demand, reusing the existing mission creation and start services. This is a backend-only, explicitly triggered operation; **not** automatic dispatch scheduling.

## Context
Feature 014A provides read-only `GET /api/dispatch/recommendations`, with per-Hub FIFO, deterministic drone selection, a strict 100% battery rule, and existing planner validation. Its recommendations are snapshots, not reservations. Existing mission services already implement creation/start and some transactional locking/replanning; inspect and reuse those paths rather than duplicating them.

## Scope
- Provide one explicit backend operation to execute a selected `order_id` + `drone_id` recommendation (propose a route consistent with the repository's API conventions during Initialize; do not assume the route name in advance).
- Validate that the requested pair is still dispatchable **at execution time**: ready order at its origin Hub, drone IDLE and physically docked at that Hub, battery exactly 100%, no conflicting active mission, and eligible according to the existing planner.
- Reuse the existing mission creation and mission start mechanisms, including their transactional safeguards and state transitions. Do not implement separate mission lifecycle logic.
- Return the resulting mission ID and meaningful status, or an explicit actionable error if the pair is no longer eligible.
- Preserve the existing manual mission endpoints and the 014A read-only recommendations endpoint.
- Document what happens if mission creation succeeds but starting fails; avoid duplicate creation on retries and do not silently leave an unrecoverable assignment. Prefer existing recovery/cancellation mechanisms; surface a clear result.

## Required safety behavior
1. **No double assignment:** concurrent or repeated requests must not create two active missions for the same order or drone. Use existing database transaction/locking and revalidation where possible; do not rely on an in-memory claimed set for execution.
2. **Stale recommendation:** reject or safely resolve a pair whose order/drone availability changed since preview; never trust a previous recommendation blindly.
3. **100% battery rule:** enforce this specifically for dispatch execution, even though the general planner may allow flights with less battery. Do not change manual mission behavior unless required for safety.
4. **No available worker:** determine the current start-service behavior and handle failure transparently. Avoid misleading success responses or duplicate assignments on retry.
5. **No new return-Hub capacity system:** use the existing planner unchanged. Assume sufficient capacity for this MVP; no reservations, virtual occupancy, saturation prevention, or optimization.
6. **No broad refactor:** modify only files needed for this feature.

## Out of scope
- Periodic polling/scheduler, automatic execution of entire queues, ON/OFF switch, and frontend controls (014C).
- Charging or battery regeneration (014D).
- Fleet relocation/rebalancing (014E).
- New mission states, separate dispatch worker, dock reservations, and redesign of the planner.

## Acceptance criteria
- A valid recommended pair creates **one** mission and starts it through existing services; response identifies the mission.
- A pair with 99% battery, MAINTENANCE/IN_FLIGHT status, wrong Hub, active mission, or non-ready/already-assigned order is rejected without creating a new mission.
- Two simultaneous requests for the same order or drone cannot produce duplicate active assignments; verify with focused concurrency tests where the existing test infrastructure permits.
- A repeated request does not create a second mission; its response/error is clear and deterministic.
- Planner rejection prevents execution, with a useful reason.
- A failed start is reported explicitly and leaves a state that can be understood/recovered using existing mechanisms.
- Existing manual mission endpoints and `GET /api/dispatch/recommendations` continue to work.
- Focused backend tests pass; run repository-required quality checks. Do not require unrelated frontend work.

## Implementation workflow and checkpoints
1. **Initialize:** inspect the specific existing mission create/start functions, transaction boundaries, worker start behavior, and relevant tests. Propose a minimal API contract and a short implementation plan. **Stop for approval before editing code.**
2. **Start Implementation:** implement only the approved plan, with focused tests. Do not commit. Stop and report changed files, test results, and any unresolved risks.
3. **Finish:** only after explicit user approval, follow the repository's existing Finish workflow. Avoid including unrelated uncommitted Feature 013 files in any commit.

## Notes for demo
- Execution is triggered manually through the backend API in 014B; the operator UI and unattended dispatch loop come later.
- Because charging is not implemented yet, drones below 100% remain ineligible until 014D (or manually reset in test data).

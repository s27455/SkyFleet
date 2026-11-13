# Feature 014D — Automatic Drone Charging

**Status:** Implemented (backend only) and verified by automated tests, including tests on PostgreSQL; not run live on development data, and QA and code-review agents were not run. Not committed.

## Implementation notes (verified)
- Code: `backend/app/simulation/charging.py` (new), `backend/app/worker.py` and `backend/app/config.py`; tests: `backend/tests/simulation/test_charging.py` (SQLite) and `backend/tests/simulation/test_charging_postgres.py` (opt-in `-m postgres`). No migration and no frontend change (`CHARGING` already exists in the frontend types and status labels).
- The worker runs one charging step every tick, in its own try/except, whatever the Automatic Dispatch mode is. Per drone, under its row lock: an `IDLE` drone below 100% that is docked (same presence rule as the planner) and has no `ASSIGNED` or `IN_FLIGHT` mission becomes `CHARGING` (that tick adds nothing); a `CHARGING` drone gains `rate x elapsed`; at 100% the battery is clamped to exactly 100 and the drone becomes `IDLE`; a `CHARGING` drone already at 100% becomes `IDLE`. `IN_FLIGHT`, `MAINTENANCE`, undocked drones and drones with an active mission never charge, and `MAINTENANCE` is never cleared.
- Rate: `SIM_CHARGE_RATE_PCT_PER_MINUTE`, default 20 (demo-accelerated: the drone model's own figure is 80% in 45 minutes, about 1.8 per minute). One number for every drone; no charger slots.
- Restart and clock safety without persisted charging state: the battery column is a whole number, so the fractional remainder is carried in the worker's memory. The first tick after a worker start counts one nominal tick (not the time since landing); the time between ticks is clamped to five nominal ticks and a backwards clock adds nothing; a manual battery edit becomes the new starting point. Charging does not touch dispatch eligibility: the planner already requires `IDLE`, so a charging drone is never recommended or dispatched.
- Decisions (approved with the plan): tick-based charging without a migration, rate default 20% per minute, and the Management-edit limitation below accepted as a follow-up.

## Verification
- Passed: default backend suite 404 passed (23 PostgreSQL-marked tests deselected); `pytest -m postgres` 23 passed on the local Docker PostgreSQL in a temporary database; `ruff`, `ruff format --check` and `mypy` clean. 22 tests are new: 19 on SQLite (start without a jump; steady rise to exactly 100 and `IDLE`; fractional rates; restart mid-charge without a burst; long gap and backwards clock; each non-charging case; manual battery and maintenance edits mid-charge; a flown mission landing, then `CHARGING`, then `IDLE` at the same Hub; with dispatch ON a charged drone is sent on a later pass; with dispatch OFF charging continues and nothing starts; the worker charges each tick) and 3 on PostgreSQL (charging racing with mission confirmation never leaves a drone both claimed and charging; overlapping steps keep the battery between 0 and 100; a drone charges to 100 and becomes `IDLE`).
- Not run: the frontend checks (frontend untouched); a live run on the development database and the manual demo checklist; the QA and code-review agents. The concurrency tests are probabilistic, so a pass does not prove the absence of a rare ordering.
- Behavior changes to expect: when the worker is restarted with this code, the seeded drones below 100% start charging (this changes development drone data and starts no mission); manual missions can no longer be created for a drone below 100% because it is `CHARGING`; Feature 011 treats `CHARGING` as busy, so an operator cannot edit the battery, set maintenance or delete a charging drone until it is `IDLE` (follow-up, out of scope here).
- Known limitations: the fractional remainder (less than one tick of charge) is lost on a worker restart and charging pauses while the worker is down; two workers running by mistake would each add charge, doubling the rate without corrupting data.

## Goal
Complete the automatic delivery cycle by charging docked drones after flight until their battery reaches exactly 100%, at which point they become eligible for the existing Automatic Dispatch (014A–014C). Keep the feature minimal and backend-first.

## Context
- 014A recommends only IDLE, physically docked drones with exactly 100% battery, no active mission, and a feasible plan.
- 014B revalidates the 100% rule under database locks before creating/starting a mission.
- 014C runs in the separate Simulation Worker, which already advances flights and dispatches periodically. Automatic Dispatch is OFF by default and operator-controlled.
- Flight simulation currently lands a drone as IDLE with residual battery and a return Hub; CHARGING is an existing drone status, but there is no charging behavior.
- MAINTENANCE is a separate manual/fault state, not a routine post-flight state.

## Required behavior
1. A drone physically docked at a Hub, not on an active mission, with battery below 100% automatically enters CHARGING. This includes drones already docked and below 100% when the new worker starts, so the current development fleet can recover without manual battery edits.
2. Charging increases battery gradually over simulated/real elapsed time using one configurable, documented charging rate. Use a sensible MVP default and make the rate easy to adjust; avoid a complicated battery or charger model.
3. On reaching 100%, clamp to exactly 100%, change status to IDLE, and stop charging. The next 014C pass can dispatch the drone if Automatic Dispatch is ON and other 014A/014B requirements are met.
4. CHARGING drones must never be recommended or dispatched. Do not mark a drone IDLE before it reaches 100%.
5. IN_FLIGHT, MAINTENANCE, undocked drones, and drones with active missions must not charge. Never automatically clear MAINTENANCE or change an in-flight drone's battery.
6. Charging works independently of Automatic Dispatch ON/OFF. Turning dispatch OFF stops new assignments, not charging or ongoing flights.
7. Preserve existing flight behavior: delivery, return-Hub selection, landing, order/mission completion, and battery consumption must continue working.
8. Charging state and progress must survive worker restarts without double-counting elapsed time or creating instant full batteries. Handle the first charging tick and clock anomalies safely.
9. Use the existing Hub capacity/planner behavior unchanged. No charger-slot limits, dock reservations, relocation, or fleet rebalancing.

## Implementation guidance
- Inspect the existing worker tick, flight landing transaction, drone status model, battery column precision, docked_hub/presence helpers, and current migrations before choosing the smallest safe design.
- Prefer integrating charging into the existing Simulation Worker rather than creating another scheduler or service process.
- Use database transactions/appropriate row locking and persisted charging timing only if needed for correct restart-safe, race-safe progress. If schema changes are necessary, propose the smallest Alembic migration and explain why; do not assume a specific schema design before the code audit.
- Avoid overlapping charging and dispatch mutations for the same drone. Reuse existing repository conventions, locking and configuration patterns.
- Make updates idempotent per tick and avoid unnecessary writes/log spam when no battery or status change is due.
- If an operator manually edits a drone's battery or status, ensure the next tick responds safely without overriding MAINTENANCE or corrupting mission state.

## Scope
**In:** backend charging lifecycle, minimal configuration/persistence as needed, worker integration, automated tests, concise documentation, and only the minimal UI adjustment needed if existing Management status/battery display cannot represent CHARGING correctly.

**Out:** charger capacity or queues, battery degradation, energy pricing, charger allocation, maintenance automation, relocation/rebalancing (014E), redesigned map markers, completed-delivery marker cleanup, broader status UX polish, and changes to 014A/014B dispatch eligibility.

## Verification / acceptance criteria
- A drone that lands with less than 100% begins CHARGING at its actual return Hub, increases battery over successive worker ticks, reaches exactly 100%, and becomes IDLE.
- A previously docked IDLE drone with less than 100% starts charging after worker startup, without an instant jump to 100%.
- Automatic Dispatch ON: after a charged drone reaches 100%, a waiting feasible order at that Hub can be dispatched on a later pass without manual intervention.
- Automatic Dispatch OFF: charging continues but no new mission starts.
- MAINTENANCE, IN_FLIGHT, undocked and active-mission drones do not charge.
- Restarting the worker during charging resumes safely; no negative battery, >100% battery, duplicate charging or unexpected immediate completion.
- Existing 014A recommendations, 014B execution, 014C ON/OFF, flight simulation, manual mission flows and return-Hub behavior remain correct.
- Include focused unit/integration tests, real PostgreSQL tests where concurrency/persistence matters, and run the repository's required backend checks. If frontend is touched, run its relevant tests/typecheck/lint/build.
- Provide a short manual demo checklist: observe landing -> CHARGING -> 100% -> IDLE -> automatic next mission when ON. Do not trigger real development missions during implementation without operator approval.

## Workflow / approval boundary
Use the existing repository workflow: **Initialize → review plan → Start Implementation → live verification → Finish**.

At Initialize, audit the relevant code and propose the minimal implementation plan, including whether a migration is needed and the proposed charging rate. **Do not modify code or database and do not start implementation until the operator approves the plan.** Do not commit until Finish is approved.

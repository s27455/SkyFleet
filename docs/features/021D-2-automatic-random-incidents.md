# Feature 021D-2 — Automatic Random Incidents

**Project:** SkyFleet B2B drone-delivery simulator  
**Status:** Implemented and verified (automated checks and owner browser QA passed); not yet committed — see §18  
**Dependency:** Feature 021D-1 completed and committed  
**Scope:** Simulation worker, incident scheduling, API, frontend control, tests and documentation

## 1. Goal

Make the existing disabled **Random Incidents** control functional. When enabled by an operator, the simulation worker periodically attempts realistic incidents without requiring manual scenario triggers. Existing manual incidents must continue to work.

This is a bounded MVP addition, not a redesign of simulation physics or dispatch.

## 2. Current baseline (to verify in the repository)

- A disabled Random Incidents switch exists in `SimulationEventsPanel` and is reachable through the Scenario menu.
- Manual incident triggers exist for LPR helicopter, recipient unavailable and drone failure.
- The worker already schedules automatic order generation and can provide a reference pattern for independent ON/OFF state and failure isolation.
- ADR 0004 §5 proposes attempts every 3–5 minutes, per-type cooldowns of 2–3 minutes, and at most one active incident per mission.

**Implementation prerequisite:** Inspect the actual code and ADR before finalizing persistence, transaction boundaries, event fields, eligibility and worker integration. The items above reflect prior repository-analysis reports, not an independent inspection of the current files.

## 3. Included / excluded

### Included

1. Operator-controlled Random Incidents ON/OFF switch with backend-confirmed state.
2. Real-time randomized scheduling and per-type cooldowns.
3. Automatic LPR helicopter, recipient-unavailable and drone-failure attempts.
4. Mission eligibility checks, overlap protection and fleet-health guard.
5. Operator-visible outcome/status and reuse of existing alert/event mechanisms.
6. Automated tests and browser QA.

### Excluded

- Automatic Rain Warning (can ground the entire fleet).
- Automatic Cancel Order (requires deliberate operator selection).
- Changes to flight physics, route selection, dispatch queues, battery/energy formulas or manual incident semantics.
- New third-party dependencies or a new generalized event platform.

## 4. Operator experience

- The existing **Random Incidents** switch becomes interactive, inside the compact Scenarios menu.
- Its checked state is driven by a successful API response, not an optimistic-only local toggle.
- Show loading, backend/worker unavailable and request-failed states; preserve accessible labeling and keyboard interaction.
- Show whether the mode is enabled, and a concise last-attempt result when available: triggered, skipped (no eligible target / cooldown / fleet guard) or error.
- Do not imply that an incident is guaranteed every interval: the worker makes an **attempt**, which may be skipped.
- Existing critical incident alerts and Rain Warning remain visible outside the Operations tabs.

## 5. Scheduler behavior

- **Default:** OFF after worker startup/restart, consistent with the existing automatic-order pattern if its lifecycle semantics are suitable.
- **Clock:** real elapsed time, independent of simulation speed or tick count.
- **Interval:** schedule the next attempt after a randomized 3–5 minutes (uniform distribution is an acceptable MVP assumption).
- **Types:** choose among LPR helicopter, recipient unavailable and drone failure. Use configurable weights only if a simple configuration mechanism already exists; otherwise use a documented default.
- **Cooldown:** enforce 2–3 minutes between attempts of the same incident type. Define whether this starts at attempt or successful trigger and test it; recommended: successful trigger to avoid needlessly suppressing skipped types.
- **No eligible target:** record a skipped attempt and schedule the next regular interval; do not busy-loop or immediately retry.
- **OFF:** no new automatic incident attempts; disabling does not retroactively undo an active incident.
- **Failure isolation:** exceptions in the scheduler must not terminate the main worker loop or interrupt flight updates. Record an error outcome without leaking sensitive details to the UI.
- **Worker restart:** reset mode to OFF, cancel in-memory deadlines, and ensure no stale enabled state is displayed.

## 6. Mission eligibility and overlap protection

Before triggering an automatic incident, confirm the target is eligible using existing service validations and a scheduler-specific overlap guard:

- Target must be an active mission in the appropriate phase for that incident type.
- A mission with an already active incident must not receive another automatic incident.
- Recheck eligibility inside the same protected transaction/trigger path to avoid races with manual actions or flight progression.
- Do not alter manual incident validation or behavior solely to satisfy the automatic scheduler.
- Prefer a shared authoritative incident-state query; if current data cannot reliably represent active incidents, flag this as an architectural decision before coding.
- A manual incident occurring concurrently with an automatic attempt must not cause a partial or duplicate incident.

**Open decision:** Confirm the exact definition of an *active incident* for each existing scenario and whether automatic-only exclusion can be enforced without changing the manual paths.

## 7. Drone-failure fleet guard

An automatic drone failure must be skipped if it would leave **fewer than 50% of the total fleet operational**.

Proposed MVP definition, subject to verifying model/status semantics:

- **Fleet total:** all non-retired drones represented in the current simulation fleet.
- **Operational:** drones that are not in maintenance, permanently failed or otherwise unavailable due to a fault; normal flying, idle and charging states count as operational if they can return to service without manual repair.
- Evaluate the projected operational count *after* failing the selected drone.
- Enforce the guard at trigger time, not only when selecting candidates.
- For a fleet of 12, do not allow automatic failures to reduce the operational count below 6.

**Open decision:** Verify exact status values, whether retired drones exist, and how the guard can be made race-safe with manual failures. Do not assume `status != MAINTENANCE` is sufficient without inspection.

## 8. Persistence and API

Use a durable, independent state record for Random Incidents, following established application patterns. **Do not assume** that `dispatch_auto_state` can safely store a second feature merely because it has `enabled` fields.

Before implementation, compare:

1. Reusing a genuinely generic keyed control-state table, if its schema, constraints and readers support multiple independent controls.
2. A dedicated random-incident state table with a reviewed migration, only if needed.
3. Existing supported configuration storage, if it provides correct restart and concurrent-write semantics.

**Approval gate:** Present the chosen persistence strategy and whether a migration is required. No migration without explicit approval.

Suggested API shape, to align with existing conventions after inspection:

- `GET /api/incidents/random` — enabled state, worker availability if known, last attempt outcome and timestamps if stored.
- `POST /api/incidents/random/enable` — enable.
- `POST /api/incidents/random/disable` — disable.

Requirements: idempotent transitions, explicit errors when the worker is unavailable, consistent authorization/error handling with other simulation controls, and no independent duplicate frontend polling where existing shared state can be reused.

## 9. Incident execution and observability

- Call existing trigger services with their established `AUTOMATIC` origin (if confirmed by repository inspection).
- Preserve all existing domain validations, alerts, mission timelines and audit/history semantics.
- Do not fabricate success when the trigger rejects an ineligible target.
- Distinguish successful trigger, skipped attempt and internal error in logs/status.
- Expose automatic origin in existing events when supported by the data model; do not change historical records.
- Avoid unbounded event/log growth introduced solely by frequent skipped attempts; use existing operational status fields or logs where appropriate.

## 10. Configuration

- Production/demo default attempt interval: 180–300 seconds.
- Per-type cooldown: 120–180 seconds, with a clearly documented choice of fixed versus randomized duration.
- Use small, injectable/test configuration values for deterministic tests; do not make the real-time demo interval globally short merely to speed up testing.
- Incident-type weights and fleet threshold must be documented. Default proposal: equal weighting for eligible types, with the 50% fleet guard; final weights require approval after code review.

## 11. Failure and edge cases

Cover: no active missions; no eligible target of the chosen type; concurrent manual incident; cooldown active; worker offline; worker restart; duplicate enable/disable requests; API failure; fleet at exactly the 50% threshold; odd fleet size and rounding; missing or stale state row; transaction rollback; scheduler exception; incident completion and subsequent eligibility; rapid ON/OFF toggles.

## 12. Automated testing

### Backend and worker

- OFF by default and after restart; ON/OFF transitions are idempotent.
- Real-time scheduling uses a controllable clock/random source; no multi-minute sleeps in tests.
- Correct interval boundaries and cooldown behavior.
- Exactly one eligible automatic incident attempt per scheduled cycle.
- No active-incident overlap, including concurrent/manual races.
- Fleet guard boundary and status classification.
- Existing trigger validations and `AUTOMATIC` attribution.
- No-target skip, exception isolation and continued worker ticks.
- API response codes, worker-offline behavior and persistence across relevant processes.
- PostgreSQL integration tests where concurrency or row locking matters; SQLite tests alone are insufficient for those claims.

### Frontend

- Backend-confirmed switch state, pending and failure states.
- OFF after worker restart, including stale UI refresh behavior.
- Compact menu behavior, keyboard accessibility and mobile overflow.
- Manual scenarios and existing alerts remain functional.
- No duplicate polling caused by mounting the menu.

### Regression

Run relevant backend lint/type checks and full pytest suites, plus frontend `tsc -b`, lint, formatting check, vitest and production build. Do not silently dismiss unrelated pre-existing failures; report them separately.

## 13. Manual browser QA

1. Start local API, worker and frontend using the normal project workflow, with explicit authorization for restarts.
2. Confirm Random Incidents starts OFF and can be enabled/disabled.
3. Observe the status/last-attempt feedback. For a time-limited demo, use an explicitly documented temporary development configuration rather than changing production defaults.
4. Confirm LPR, recipient-unavailable and drone-failure incidents appear when eligible, with expected alerts and event attribution.
5. Verify no incident overlaps an already affected mission and that fleet safety is preserved.
6. Disable the mode and verify no further attempts occur.
7. Restart the worker and confirm mode returns to OFF.
8. Check manual scenarios, Auto Dispatch, Automatic Orders, Rain Warning, relocation and return-to-hub regressions.
9. Check desktop and phone-width menu layout.

## 14. Expected change areas (verify exact paths)

- New or adapted worker scheduler module, tentatively `backend/app/simulation/incident_scheduler.py`.
- Worker startup/tick integration and existing scheduler/configuration support.
- Incident state persistence model/repository/service as needed.
- Incident API routes and schemas following existing patterns.
- Frontend `SimulationEventsPanel`, Scenario menu and associated API/hook or shared resource.
- Focused unit/integration tests and documentation (ADR 0004, progress tracker, feature status).

Do not treat these tentative paths as verified file locations.

## 15. Implementation sequence and approval gates

**Gate A — repository inspection and decisions (no code):**
- Verify actual persistence schema, incident-state semantics, status values, worker lifecycle and trigger transaction boundaries.
- Recommend the least risky storage approach, exact eligibility/overlap rule, weights and cooldown semantics.
- Identify whether any migration is unavoidable.
- Obtain explicit approval for unresolved choices.

**Gate B — backend implementation:** independent state, scheduler, API and tests; no frontend redesign.

**Gate C — frontend integration:** enable existing switch, status/error handling, accessible menu and tests.

**Gate D — verification:** complete automated suite, authorized service restart, manual browser QA, then separate commit after explicit approval.

At every gate: no unapproved migrations, dependency installation, DB resets/reseeding, service restarts, commits or pushes.

## 16. Acceptance criteria

- [x] Operator can enable/disable Random Incidents and sees authoritative state.
- [x] Worker attempts incidents on randomized 3–5 minute real-time intervals while enabled.
- [x] Only LPR, recipient-unavailable and drone-failure scenarios are generated automatically.
- [x] Existing trigger services and validations are reused.
- [x] No overlapping automatic incidents on the same mission.
- [x] Per-type cooldowns and fleet guard are enforced.
- [x] Mode resets to OFF after worker startup/restart.
- [x] Skips and errors are visible without falsely claiming incidents occurred.
- [x] Existing alerts, histories and manual incident controls continue to work.
- [x] Backend and frontend automated checks pass; browser QA is completed (see §18 for the one pre-existing mypy error).
- [x] No changes to flight physics, routing, dispatch or battery calculations.
- [ ] Feature is committed separately only after approval (not committed yet).

## 17. Decisions requiring approval before coding

1. **Persistence:** generic existing state table versus dedicated table/migration; validate schema first.
2. **Overlap:** exact active-incident criteria and concurrency-safe enforcement.
3. **Fleet guard:** operational status classification and treatment of odd fleet sizes.
4. **Type selection:** equal weights versus a safer weighted mix, and whether an ineligible chosen type is skipped or another type is tried.
5. **Cooldown:** fixed versus randomized 2–3 minutes and whether measured from trigger or attempt.
6. **UI observability:** which last-attempt fields can be exposed without adding a new event log.

**This document authorizes planning and review only. It does not authorize implementation, migration, restart or commit.**

## 18. Implementation record (verified against the code)

Decisions made during implementation (the §17 questions) and the resulting behavior:

- **Persistence:** a dedicated table `incident_scheduler_state` (migration `0017`, one row keyed by `name`; `enabled`, `last_check_at`, `last_outcome`, `updated_at`), independent of `dispatch_auto_state` and `order_simulation_state`. A missing row means OFF; the worker resets the mode to OFF on startup (`random_incidents.py`).
- **API** (`api/routes/incidents.py`): `GET /api/incidents/random`, `POST /api/incidents/random/enable`, `POST /api/incidents/random/disable`. Response: `enabled`, `worker_running`, `last_check_at`, `last_outcome`. `enabled` is reported only while the worker heartbeat is fresh. Enable is refused while no worker is alive (the shared worker-unavailable error); enable and disable are idempotent.
- **Scheduler** (`simulation/incident_scheduler.py`, called from `worker.py` in its own try/except): timing is in worker memory on the monotonic clock. The first look at the ON mode only starts the first random pause (180–300 s), so enabling never triggers immediately; turning OFF clears the schedule and cooldowns. One attempt triggers at most one incident.
- **Type selection:** default weights LPR 0.4, recipient unavailable 0.4, drone failure 0.2 (`INCIDENT_SIM_WEIGHT_*`). Types not in cooldown are tried in a weight-biased random order within the same attempt until one triggers; a type with no eligible target, an LPR pass already running or a refused fleet guard is skipped. Nothing is retried before the next scheduled attempt.
- **Cooldown:** random 120–180 s per type, started only by a successful trigger.
- **Overlap:** an automatic drone failure skips flights that are recalled or have a pending or failed handover, rechecked under the locks (`failure.has_other_incident`, `automatic_safety=True`); the manual failure path is unchanged. Recipient-unavailable and LPR keep their existing validations.
- **Fleet guard** (automatic drone failure only): refused if fewer than `ceil(total / 2)` drones would remain operational. Unavailable = status `MAINTENANCE` or a drone in `EMERGENCY_APPROACH`; a failed drone and one an operator took out of service cannot be told apart by status, so both count. On PostgreSQL automatic failures are serialised by a transaction-scoped advisory lock. Limit: a manual failure never takes the lock and is never refused, so one racing an automatic failure can leave one drone fewer than the guard alone would allow.
- **Observability:** the attempt time and a short outcome (`Triggered: …`, `Skipped: <type>: <reason>; …`, or a generic error text) are stored in the state row and shown in the Scenarios menu control; skipped attempts create no mission event; error details go to the worker log only. Triggered incidents use the existing events with the `AUTOMATIC` origin.
- **Configuration** (`config.py`, validated at startup): `INCIDENT_SIM_MIN/MAX_INTERVAL_SECONDS` (180/300), `INCIDENT_SIM_COOLDOWN_MIN/MAX_SECONDS` (120/180), `INCIDENT_SIM_WEIGHT_LPR/RECIPIENT/FAILURE`.
- **Frontend:** `RandomIncidentsControl` in the Scenarios menu, one shared poll (`useRandomIncidents`, owned by `App`), state taken from the server response, with loading, unavailable/retry and worker-not-running states.

Verification (run on 2026-11-15):

- Backend: `ruff check` clean, `ruff format --check` clean (182 files), `pytest` 828 passed (61 `postgres` tests deselected by default), `pytest -m postgres` 61 passed.
- Backend `mypy .`: 1 error, `tests/weather/test_rain_warning.py:208` (`app.dispatch.service` does not export `weather`, `attr-defined`). The file is not changed by this feature; it was not investigated further and is reported as pre-existing.
- Frontend: `tsc -b`, `oxlint`, `prettier --check` clean; `vitest` 847 passed (62 files); production build succeeded (chunk-size warning only).
- Manual browser QA (§13): confirmed passed by the owner on 2026-11-15; the individual steps were not recorded.

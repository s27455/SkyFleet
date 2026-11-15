# Feature 022 — Incident Acknowledgement & Automatic Drone Recovery

> Formerly documented as Feature 021F; renamed to 022 (file `022-incident-acknowledgement-drone-recovery.md`).

**Project:** SkyFleet MVP  
**Status:** Implemented and verified (2026-11-15): automated checks, a live activation of the recovery worker and the owner's live QA of the acknowledgement UI. The phone-width layout of the overlay and the visual recovery line in the Activity list are not explicitly confirmed by the owner. Not committed. See §12 to §17.
**Scope:** Incident notification acknowledgement and recovery of drones after simulated failures  
**Dependencies:** Existing incident/event UI (021B/021C), automatic incidents (021D-2), hub capacity and worker lifecycle  
**Priority:** High — prevents long-running simulation fleet depletion

## 1. Problem and goal

During long-running simulations, incident alerts remain visible over the map after the operator has read them. In addition, drones that emergency-land following simulated failures remain in `MAINTENANCE` indefinitely, gradually reducing the fleet available for orders.

Deliver two independently testable improvements:

1. **Acknowledge incident notifications** without deleting incidents or losing their history.
2. **Automatically recover eligible failed drones** after a simulated ground-service delay of **120 seconds of real elapsed time**, returning them to a suitable hub without simulating a flight.

Preserve the existing emergency-landing, mission, dispatch, charging, and hub-capacity semantics unless a specific change is separately approved.

## 2. Existing behavior to verify before implementation

Claude Code must inspect the repository rather than assume the following details:

- `LiveDataNotices`, Events tab, incident notification sources, event IDs and polling behavior. (Follow-up 2026-11-15: the Events tab's current alerts now also drop an acknowledged emergency; see §Implementation "Unchanged on purpose".)
- Manual and automatic drone-failure triggers, `origin=AUTOMATIC`, and the emergency-landing transition to `MAINTENANCE`.
- Any existing recovery, repair, maintenance release, relocation, or return-to-hub logic.
- `Drone`, `MissionFlight`, event records, hub docking/capacity and battery/charging rules.
- Worker scheduling, real-time clocks, startup recovery and database transaction patterns.
- Feature 021D-2's 50% operational-fleet guard and its distinction between `MAINTENANCE` and `EMERGENCY_APPROACH`.
- Whether manual failures should be eligible for automatic recovery: **yes (approved after live QA, see §16):** every completed `DRONE_FAILURE` landing is recovered, whatever the origin of the failure.

If a compatible recovery mechanism already exists, reuse or repair it instead of introducing a competing scheduler.

## 3. Part A — Incident notification acknowledgement

### 3.1 Operator experience

- Every applicable incident notification in the map overlay provides a compact, accessible **Acknowledge** action (icon plus accessible label or text).
- Acknowledging immediately removes that specific notification from the **active map overlay and from the active Events list** once confirmed by the chosen persistence mechanism (the Events part was added on 2026-11-15).
- Acknowledgement does **not** dismiss unrelated notifications or change incident, flight, drone or mission state.
- Unacknowledged critical alerts remain available; do not auto-dismiss them based on age.
- Incident history remains accessible in Events and relevant mission/drone timelines.
- Acknowledgement survives page refresh and routine polling, and an already acknowledged event does not reappear merely because the same API record is fetched again.
- Newly generated incidents, including later incidents involving the same drone, remain visible until separately acknowledged.
- Preserve the existing compact responsive notification layout and overflow access from 021B.

### 3.2 Identity and persistence

- Use a **stable, unique incident/notification identity**, not array position, message text, drone ID alone, or a volatile timestamp.
- Inspect existing notification/event IDs and determine whether an acknowledgement store already exists.
- Prefer the smallest persistence solution consistent with current architecture. If backend persistence is needed, propose the schema/API and migration **before implementing it**.
- A browser-local solution is acceptable only if the documented product requirement is **per-browser persistence** and it can reliably distinguish events; otherwise use backend persistence. Do not silently assume cross-device synchronization.
- Handle repeated acknowledgement requests idempotently and avoid stale polling reintroducing an acknowledged alert.
- Display a recoverable error if acknowledgement persistence fails; do not claim success when it has not persisted.
- Acknowledge is **not** incident resolution or cancellation; keep these concepts separate in UI and code.

### 3.3 Accessibility

- Keyboard-operable controls, visible focus, appropriate ARIA label, and no accidental click-through to map controls.
- Accessible on narrow/mobile layouts without covering the map.

## 4. Part B — Automatic drone repair and ground recovery

### 4.1 Lifecycle

1. Existing simulated drone failure occurs; existing emergency approach and landing remain unchanged.
2. After the drone **actually completes emergency landing** and enters the appropriate failure-related `MAINTENANCE` state, begin a **120-second real-time recovery delay**. Do not start the delay at initial failure trigger if the drone is still flying.
3. Once due, simulate ground crew recovery (no new flight and no teleportation during an active mission).
4. Choose an eligible hub using the existing hub-capacity and docking rules. Prefer the nearest **suitable** hub to the emergency-landing position; if current code defines a different authoritative recovery destination, document and obtain approval before changing it.
5. Atomically relocate the recovered drone to that hub and update hub occupancy/assignment consistently.
6. Return the drone to the appropriate operational state using **existing charging/battery rules**. Do not arbitrarily set battery to 100%. If charging is required, use `CHARGING`; use `IDLE` only when genuinely dispatch-ready.
7. Record a durable recovery event while retaining the original failure and emergency-landing history.

**Time basis:** 120 seconds of real elapsed time, independent of simulation tick rate. The timestamp must be durable enough to survive worker restarts; a purely in-memory timer is insufficient.

### 4.2 Eligibility and isolation

- Automatically recover only drones whose maintenance state can be **unambiguously linked to a completed simulated drone-failure incident** (an `AUTOMATIC` or a `MANUAL` `DRONE_FAILURE`, see §16).
- Never auto-release drones manually placed into maintenance, drones undergoing unrelated maintenance, or emergency-landed drones without confirmed eligible failure provenance.
- Do not change manual incident behavior without explicit approval.
- A failed/closed mission remains failed/closed; recovery must not reopen, resume, or silently complete its order.
- Recovery must not interfere with an active flight, a new mission, or a later operator maintenance action.
- Ensure that recovery is performed at most once per failure, including across restarts and concurrent worker steps.

### 4.3 Hub capacity and retry

- Check capacity using existing authoritative hub occupancy semantics and database locks.
- If the nearest hub is full, consider other suitable hubs according to existing capacity rules.
- If **all** hubs are full, keep the drone in a recoverable pending state and retry later, without deleting it or overfilling a hub.
- If the worker restarts, pending recoveries remain discoverable and resume safely when the worker runs again.
- Recovery failures must be logged and retried without repeatedly duplicating events or corrupting occupancy.

### 4.4 Fleet safety

- Recovery should increase operational availability only when the drone is actually available or charging under existing definitions.
- Preserve Feature 021D-2's minimum-50%-operational automatic failure guard; do not weaken it to compensate for recovery.
- Confirm the guard counts `MAINTENANCE` and `EMERGENCY_APPROACH` correctly throughout the lifecycle.
- Avoid an endless loop of the same drone failing and instantly recovering: recovery must respect the 120-second delay, and existing per-type incident cooldowns remain in effect.

## 5. Scheduling and persistence design gate

**Do not choose schema or implementation mechanism blindly.** First inspect current models and worker patterns and propose the smallest robust solution.

A satisfactory design must persist or derive:

- Which specific failure makes the drone eligible for recovery.
- When emergency landing completed (or when recovery becomes due).
- Whether recovery is pending, completed or blocked by hub capacity.
- The identity of the recovery event, so processing is idempotent.

Prefer deriving state from existing durable fields where safe. If new fields or a recovery table are needed, present a narrowly scoped Alembic migration and rationale. **Creating and applying a migration require separate approvals.** Never reuse the random-incident scheduler state as a per-drone recovery ledger.

Worker processing must be bounded, guarded against exceptions, safe under concurrent attempts, and compatible with the existing heartbeat and startup behavior. The recovery feature must not require Random Incidents to remain ON after a failure has occurred.

## 6. API and frontend integration

- Reuse existing endpoints and polling where possible; avoid duplicate high-frequency polling.
- Add acknowledgement endpoints only if needed for durable semantics, with idempotent requests and clear error handling.
- The UI should reflect recovered drones at their new hub and remove their old emergency-location marker through the existing state refresh.
- Show recovery in event history using existing event conventions; do not fabricate a new flight or delivery.
- Do not automatically remove the original incident notification merely because the drone has recovered; acknowledgement is an operator action.
- If recovery is blocked, keep a truthful status (e.g. awaiting ground recovery/hub capacity) without implying the drone is already available.

## 7. Acceptance criteria

### Notifications

- [x] Each applicable incident alert has an accessible acknowledgement action.
- [x] Acknowledging one alert removes only that alert from the map overlay and the active Events list.
- [x] Acknowledgement survives refresh/polling according to the approved persistence scope.
- [x] Original incidents, event history and mission timelines remain intact.
- [x] A later incident on the same drone appears as a new alert.
- [x] Unacknowledged critical alerts remain visible or reachable through overflow.

### Recovery

- [x] Automatic failure follows the existing emergency-landing trajectory.
- [x] Recovery countdown starts after landing, not at failure trigger.
- [x] After approximately 120 real seconds, an eligible drone is recovered to a suitable hub.
- [x] The drone disappears from the emergency site and appears at the hub without an artificial flight.
- [x] Battery and post-recovery status follow existing charging rules.
- [x] Operator-set and unrelated maintenance is never automatically cleared (revised in §16: a completed `DRONE_FAILURE` landing is recovered whatever the origin of the failure).
- [x] A full hub cannot be overfilled; another hub is chosen or recovery retries.
- [x] Recovery survives worker restart and cannot execute twice.
- [x] Failure and recovery remain visible in event history; failed orders are not resurrected.
- [x] The 50% automatic-failure guard still passes all boundary and concurrency tests.
- [x] Long-running simulation does not permanently deplete the fleet solely through recoverable failures (observed over the live run: nine failures recovered, no drone left in `MAINTENANCE`; no separate long-running soak test was done).

## 8. Test plan

**Backend unit tests:** eligibility by failure origin, real-time delay, no early recovery, battery/status semantics, pending/full-hub retry, idempotency, event history, disabled Random Incidents after failure, worker restart.

**PostgreSQL integration tests:** atomic hub occupancy, concurrent recovery attempts, capacity race with normal docking, failure/retry rollback, durable recovery state and migrations if required.

**Frontend tests:** individual acknowledgement, persistence across refresh/polling, new incident on same drone, error handling, compact mobile layout, no event-history deletion, recovered drone location refresh.

**Manual QA:** run one controlled automatic failure in an approved test environment, observe emergency landing, wait 120 real seconds from landing, verify transfer to a suitable hub, confirm event history and notifications, and verify the fleet can dispatch again. Check a capacity-blocked case and worker restart using isolated test fixtures where feasible.

Run the project's existing formatting, lint, type-check, backend/frontend test and build checks. Report pre-existing failures separately from regressions.

## 9. Risks and non-goals

**Risks:** confusion between maintenance reasons; insufficient provenance on old failure records; capacity races; non-durable timers; old alert IDs; shared uncommitted files from 021D-2 and 021E; changes to existing order/mission state.

**Non-goals:** real repair logistics or road routes; new drone models; changing flight physics or routing; modifying historical orders; automatic recovery of all maintenance drones; changing automatic incident probability, 3–5-minute cadence or cooldowns; resetting the development database.

Existing historical maintenance drones should **not** be mass-recovered automatically unless their eligibility can be proven and the operator explicitly approves a one-time remediation plan.

## 10. Implementation gates

**Gate A — Repository investigation and design (documentation/read-only):** inspect existing mechanisms; identify exact files, data provenance, schema requirements and notification persistence scope. Report unresolved decisions. **Stop for approval.**

**Gate B — Backend recovery and acknowledgement persistence (if required):** implement narrowly scoped changes and automated tests. Migration files may be prepared only after explicit design approval; do not apply them without separate authorization. **Stop for approval.**

**Gate C — Frontend acknowledgement and integration:** implement accessible controls and state synchronization; test and build. **Stop for approval.**

**Gate D — Local migration (if needed), controlled restart and manual QA:** back up local development database before approved migration; verify target and revision; preserve all data; test recovery and notification behavior. **Stop for approval.**

**Gate E — Final review and commits:** inspect full diff and distinguish 021D-2, 021E and 022 changes, especially shared files. Commit only with explicit approval; do not push without explicit approval.

## 11. Instructions for Claude Code — first pass

Read this specification, relevant existing feature docs and ADRs, and the actual implementation. **Perform Gate A only.** Do not edit application code, tests or database; do not install dependencies, restart services, trigger incidents, commit or push. Report current behavior, reusable mechanisms, exact proposed files, whether a migration is required, edge cases, test plan and any decisions requiring approval. Preserve all uncommitted work from Features 021D-2 and 021E.

## 12. Approved decisions and Gate B record (2026-11-15)

### Approved at Gate A

1. **Acknowledgements:** backend-persisted, in a dedicated `incident_acknowledgements` table keyed by `mission_id`; idempotent, survive refresh, hide only the matching emergency alert (in the map overlay and, since 2026-11-15, in the Events tab's current alerts); events, missions and history are never changed.
2. **Recovery event:** a new `DRONE_RECOVERED` event type with the unique key `DRONE_RECOVERED:<mission id>`. `DRONE_RELOCATION` is not reused.
3. **Migration:** `0018` (acknowledgement table and the event-type CHECK). It is **created but not applied** to the development database; applying it needs a separate approval (Gate D).
4. **Existing automatic failures:** the four current AUTOMATIC failures may be recovered once the recovery worker runs, after eligibility and event provenance are revalidated under locks, in bounded batches. Unrelated `MAINTENANCE` drones are never recovered.
5. **Manual failures:** *superseded by §16.* At Gate A they were to stay grounded; after live QA every completed `DRONE_FAILURE` landing is recovered automatically, whatever its origin. `recover_grounded_drone` still lets a future operator action reuse it (`wait_for_delay=False`, `origin=MANUAL`).

### Gate B implementation (backend only)

- **Recovery** (`app/simulation/recovery.py`): nothing new is stored per drone. A drone is eligible when it is in `MAINTENANCE` where its failed flight stopped; the flight ended as `EMERGENCY` with reason `DRONE_FAILURE` and the mission is `EMERGENCY`; the mission has a `DRONE_FAILURE` event (*Gate B: origin `AUTOMATIC` only; changed to any origin in §16*); at least `DRONE_RECOVERY_DELAY_SECONDS` (default 120) real seconds have passed since `mission_flights.emergency_at` (the committed landing time); and no `DRONE_RECOVERED` event exists for the mission. Pending is simply "eligible, due, still `MAINTENANCE`" (for example every Hub full), so a worker restart loses nothing.
- **Action:** the drone moves straight to the nearest Hub with a free place (the landing occupancy rule), keeping its battery; status `CHARGING` below 100 %, otherwise `IDLE`; `hub_id` and position follow the Hub. The mission stays `EMERGENCY`, the flight an emergency, the order unchanged. One `DRONE_RECOVERED` event (with the order, mission, flight and drone ids) is written in the same transaction. If every Hub is full nothing changes and the next look retries.
- **Concurrency:** locks in the established order (flight, mission, drone, then all Hubs by id); eligibility and capacity are rechecked under the locks; the unique event key is a second guard against a double recovery.
- **Worker** (`app/worker.py`): a guarded step every `DRONE_RECOVERY_CHECK_SECONDS` (default 5) recovers at most `DRONE_RECOVERY_BATCH_SIZE` (default 3) drones, oldest landing first; one failing drone is logged once and does not block the others. It does not depend on Random Incidents.
- **Acknowledgements** (`app/simulation/acknowledgements.py`): `POST /api/incidents/emergencies/{mission_id}/acknowledge` stores the acknowledgement once (`INSERT ... ON CONFLICT DO NOTHING`) and returns its original time on repeats; 404 `EMERGENCY_NOT_FOUND` when the mission has no emergency alert. `FlightEmergency` gained an optional `acknowledged_at`.
- **Migration** `0018_incident_acknowledgement_and_recovery.py`: creates the table and widens the CHECK; the downgrade drops the table and restores the CHECK, and refuses while a `DRONE_RECOVERED` event exists.

### Deployment constraints (important)

- **Apply order:** migration `0018` first, then restart the API and the worker. The running dev API uses `--reload`, so it already loads this code; the acknowledge endpoint and the new table are only touched when called.
- **`GET /api/flights` is intentionally not wired to the acknowledgements yet.** Joining the new table before the migration is applied would make the live endpoint fail. After `0018` is applied (Gate D) `list_flights` must read `acknowledgements.acknowledged_at_by_mission(...)` for the emergency flights and fill `FlightEmergency.acknowledged_at`.
- **Frontend first:** the current frontend rejects an unknown `event_type`, so a `DRONE_RECOVERED` event would break the order and drone activity lists. `types/event.ts` and `EventTimeline.tsx` must learn `DRONE_RECOVERED` (Gate C) before the worker is allowed to recover anything.
- The four existing AUTOMATIC failures are recovered on the first worker steps after the restart (3 per step, 5 s apart).

### Verification (Gate B, 2026-11-15)

- Backend: ruff and format clean; `pytest` 1107 passed; `pytest -m postgres` 69 passed; `mypy .` reports one error in the unmodified `tests/weather/test_rain_warning.py:208` (pre-existing).
- New tests: `test_drone_recovery.py`, `test_incident_acknowledgements.py`, `test_migration_0018.py`, `test_drone_recovery_postgres.py`. One existing assertion in `test_random_incidents_postgres.py` was adjusted because the migration head moved.
- Mutation check: removing the row locks makes the PostgreSQL capacity-race test fail.

## 13. Gate C record: frontend and flights integration (2026-11-15)

### What was added

- **Alert acknowledgement** (`LiveDataNotices.tsx`, `useEmergencyAcknowledgements.ts`, `api/acknowledgements.ts`): every emergency row has its own **Acknowledge** button (a check icon on a phone, icon and text from the small breakpoint; 40 px minimum target; accessible name "Acknowledge emergency for <drone>"). It calls `POST /api/incidents/emergencies/{mission_id}/acknowledge` and hides the alert only after the backend confirms. While the request runs the button is disabled and `aria-busy`, and repeated clicks send no second request. A failure keeps the alert, shows "Could not acknowledge this alert: <reason> Try again." and the button can be pressed again.
- **No reappearance:** an alert is hidden when `emergency.acknowledgedAt` from the flights answer is set, or when this page received the confirmation. The confirmed set lives as long as the page, so an older flights answer that arrives after the confirmation cannot bring the alert back. After a reload the server's `acknowledgedAt` is the source of truth. The summary count ("N more simulated emergencies") counts only open alerts, and a hidden alert makes room for the next one.
- **Unchanged on purpose:** rain, LPR, worker and data-staleness notices; `buildNotices` itself (it lists the emergencies it is given). Follow-up 2026-11-15: the app now passes it only unacknowledged emergencies, so a confirmed acknowledgement removes the alert from the Events tab's current alerts as well as from the overlay (one shared rule, `isUnacknowledgedEmergency`); a failed acknowledgement hides nothing, an unacknowledged alert is never hidden by age, and the acknowledged emergency stays stored and in the drone and order Activity; the emergency map marker (it still disappears when the drone leaves `MAINTENANCE`); incident history and drone and order activity.
- **`DRONE_RECOVERED`** (`types/event.ts`, `EventTimeline.tsx`): added to the known event types, shown as "Drone recovered and returned to a Hub" with the backend's reason ("Drone recovered by ground crew and moved to <Hub>"), origin, mission and drone, in the drone activity (3 newest, newest first) and the order activity, in the API's order. An unknown type is still rejected.
- **Flights parsing** (`api/flights.ts`, `types/flight.ts`): `FlightEmergency.acknowledgedAt` (null when absent, so an older backend still works); a zone-less timestamp is rejected.

### GET /api/flights integration (backend)

- `list_flights` now fills `FlightEmergency.acknowledged_at` from `incident_acknowledgements` for the emergency flights (`acknowledgements.acknowledged_at_if_migrated`).
- **Migration-safe compatibility (temporary):** the helper first asks the database whether the table exists (`inspect(...).has_table`) and returns "nothing acknowledged" when it does not, so the running development API (database still at 0017, `--reload`) keeps answering `GET /api/flights`. It is a catalog lookup, not an exception handler: a database error other than a missing table is raised, acknowledging while the table is missing fails with the database error (and the UI shows it as recoverable), and the strict `acknowledged_at_by_mission` is unchanged. Verified on the live API after reload: HTTP 200, `acknowledged_at: null` on all emergencies.
- **Removal:** done in Gate D1 (§14): the helper is deleted and `list_flights` calls `acknowledged_at_by_mission` directly.
- **Before 0018 is applied** an Acknowledge click in the running UI fails with a recoverable error (the table does not exist) and nothing is hidden; after a reload the alert is shown again. That is the intended safe behavior.

### Activation order (still pending, needs approval)

1. Apply migration 0018 to the development database (back it up first).
2. Restart the API and the worker. The frontend already knows `DRONE_RECOVERED`.
3. The four existing AUTOMATIC failures recover on the first worker steps (3 per step, 5 s apart). *(At that time manual failures stayed grounded; §16 changes this.)*
4. Optionally remove the temporary compatibility helper.

### Verification (Gate C, 2026-11-15)

- Frontend: `tsc -b`, oxlint, prettier clean; vitest 870 passed (66 files); production build succeeded.
- Backend: ruff and format clean; `pytest` 1112 passed; `pytest -m postgres` 69 passed; `mypy .` reports one error in the unmodified `tests/weather/test_rain_warning.py:208` (pre-existing).
- New tests: `LiveDataNotices.acknowledge.test.tsx` (button, pending, duplicate clicks, failure and retry, stale polling, server-persisted state, counts, multiple alerts), `acknowledgements.test.ts`, `EventTimeline.recovered.test.tsx`, `notices.test.ts`, flights parsing cases in `flights.test.ts`, and backend tests for the populated field, the missing-table behavior and non-swallowed errors (SQLite and PostgreSQL).
- Layout (a phone-width overlay, wrapping of the three controls) is not verified automatically (jsdom has no layout engine): manual browser QA is pending with the owner.

## 14. Gate D1 record: migration and API integration (2026-11-15)

- **Pre-flight:** 32 uncommitted Feature 022 files preserved on `main`; the database was at Alembic 0017 (confirmed by `alembic current` and in `alembic_version`); 0018 is the only head and follows 0017; API healthy; the worker (started 09:45, before any recovery code existed) was left running untouched.
- **Backup:** custom-format `pg_dump` of database `skyfleet` from the Docker container `skyfleet-db-1`, kept outside the repository: `C:\Users\Tomek\AppData\Local\SkyFleet\backups\skyfleet-pre-0018-20261115-113659.dump`, 577,146 bytes. Verified: the SHA-256 is identical inside the container and on the host, and `pg_restore -l` lists 74 entries including 14 data tables and `alembic_version`. A table-of-contents listing (`.toc.txt`) and the data fingerprints sit next to it. To restore, use `pg_restore` into an empty database; never downgrade 0018 while a `DRONE_RECOVERED` event exists.
- **Migration:** `alembic upgrade 0018` applied; `alembic current` reports 0018 (head). Verified in PostgreSQL: `incident_acknowledgements(mission_id varchar NOT NULL primary key, acknowledged_at timestamptz NOT NULL)` with a foreign key to `missions(id)` ON DELETE RESTRICT; `ck_operational_events_type_valid` now includes `DRONE_RECOVERED`; the `dedupe_key` unique constraint is intact; the table is empty.
- **Data untouched:** nothing was reset, reseeded, truncated or rewritten. The existing events (ids up to 2222) have an identical MD5 before and after; row counts only grew through the live simulation (one new mission, flight, order and event during the work). No `DRONE_RECOVERED` event exists and no acknowledgement row exists.
- **API integration:** the temporary `acknowledged_at_if_migrated` helper was removed and `GET /api/flights` reads `acknowledged_at_by_mission` directly. Live API after the reload: HTTP 200, every emergency carries `acknowledged_at` (all `null`, nothing acknowledged). The populated read path was checked against the real development schema inside a transaction that was rolled back (nothing was stored). A missing table is now an error, covered by tests.
- **Not changed:** the simulation worker (same process, not restarted, so recovery is not active), Random Incidents (still ON, untouched), all drone statuses, positions, missions and orders (the same 7 drones remain in `MAINTENANCE`), no incident was triggered and no drone recovered.
- **Verification:** backend ruff and format clean; `pytest` 1111 passed; `pytest -m postgres` 69 passed; `mypy .` reports one error in the unmodified `tests/weather/test_rain_warning.py:208` (pre-existing); frontend `tsc -b` clean and vitest 870 passed (unchanged by D1).
- **Next (Gate D2, needs approval):** restart the worker to load the recovery step, then watch the first recoveries.

## 15. Gate D2 record: controlled activation (2026-11-15)

- **Prediction:** before the restart, a read-only run of `due_mission_ids` on the development database listed exactly the four approved AUTOMATIC failures: DRN-001 (MIS-F2FC8056), DRN-004 (MIS-09F534C0), DRN-013 (MIS-655D0FF9), DRN-014 (MIS-B75C1051).
- **Restart:** the old worker's process tree (started 09:45, without the recovery step) was stopped, its heartbeat went stale, and the standard start helper launched the new worker (database at 0018, API and frontend reused). The new worker's heartbeat was fresh immediately and its log has no errors.
- **Recoveries (worker log, real time):** at 11:44:03 DRN-013 and DRN-004 to Centrum Riviera and DRN-014 to Centrum Handlowe Osowa (a batch of three), and at 11:44:08 DRN-001 to Forum Gdańsk (the next look, 5 s later). Each drone went to the nearest Hub, kept its battery (85, 77, 94 and 98 %), became `CHARGING` below 100 %, and the existing charging rules then took over (DRN-001 and DRN-014 were back at 100 % and `IDLE` within minutes).
- **Verified in PostgreSQL:** exactly four `DRONE_RECOVERED` events (ids 2250 to 2253, origin AUTOMATIC, keys `DRONE_RECOVERED:<mission>`), none duplicated; the drones sit exactly at their Hub's coordinates with `hub_id` updated; the four missions are still `EMERGENCY`, their flights still `EMERGENCY` with reason `DRONE_FAILURE`, their four `DRONE_FAILURE` events remain, and their orders keep their status (two are still `OUT_FOR_DELIVERY`, as the 018C rule leaves an interrupted order); every Hub is far below its capacity of 50; the events up to id 2222 have the same MD5 as before the migration.
- **Manual failures:** DRN-005, DRN-006 and DRN-009 are still `MAINTENANCE`, untouched, as decided. They need a separate manual recovery workflow.
- **Alerts:** all seven emergency alerts are still in `GET /api/flights` and none is acknowledged: recovery never removes an alert, only an operator acknowledgement does. The map's grounded-drone markers of the four recovered drones clear by themselves because the drones left `MAINTENANCE`.
- **Side effect of any worker start (existing behavior):** the modes reset to OFF. Random Incidents (was ON), Automatic Dispatch (was ON) and Automatic Orders (OFF now, 6 orders outstanding) are all OFF; the operator can switch them back on in the UI. The fleet is now 4 `CHARGING`, 7 `IDLE`, 3 `MAINTENANCE`.
- **Not done:** no incident was triggered, no real acknowledgement was stored, no drone was changed by hand, no commit.
- **Still pending:** the owner's browser QA (the Acknowledge button, the phone-width overlay, the "Drone recovered and returned to a Hub" line in a drone's Activity), ADR 0006 correction, the progress tracker, and the commit.

## 16. Revised recovery policy and activation (2026-11-15)

### Why it changed

Live QA showed drones accumulating in `MAINTENANCE` after the first activation. The worker was healthy; the cause was the Gate A rule that recovered only AUTOMATIC failures. Random Incidents was OFF after the restart, and every new failure had been triggered manually from the Scenarios menu (DRN-001 and DRN-010), so the eligibility rule left them grounded together with the three older manual failures (DRN-005, 006, 009).

### The approved rule

**Every completed `DRONE_FAILURE` emergency landing is recovered automatically 120 seconds of real time after `emergency_at`, whether the failure event is AUTOMATIC or MANUAL.** This replaces the earlier decision that manual failures stay grounded. It still does **not** apply to a drone an operator put into `MAINTENANCE` (it has no failed flight), to unrelated emergency reasons, or to a drone that has not finished landing (`EMERGENCY_APPROACH`).

### What changed in the code

- `recovery.due_mission_ids`: the `AUTOMATIC` origin condition is gone; the mission needs a `DRONE_FAILURE` event of any origin.
- `recovery.recover_grounded_drone`: the `automatic_only` parameter and its check were removed. The remaining parameters are `wait_for_delay` and `origin` (default `AUTOMATIC`, because the worker performs the recovery), so a future operator-initiated "Recover Drone" can pass `wait_for_delay=False, origin=MANUAL`.
- Unchanged safety conditions: `MAINTENANCE` status; completed `EMERGENCY` landing; `emergency_reason = DRONE_FAILURE`; a valid `DRONE_FAILURE` event; 120 s since `emergency_at`; unchanged landing position; no earlier `DRONE_RECOVERED` event; a Hub with a free place; locks in the order flight, mission, drone, Hubs; exactly one event per mission (unique key `DRONE_RECOVERED:<mission>`).
- No change to emergency landing, charging, dispatch, order status handling, incident probabilities, the migration or the frontend.

### Tests

Updated: the SQLite and PostgreSQL tests that expected manual failures to stay grounded now assert recovery after the delay (and not before). New: automatic and manual failures recovered together, oldest first, in bounded batches; an incomplete emergency approach stays excluded; a PostgreSQL race between an automatic and a manual failure for the last free place; worker-loop tests that run the real `run_forever` and check that the recovery step is called and recovers both origins, that a drone not yet due stays grounded, and that a recovery failure never stops the loop (disabling the call in the worker makes two of them fail). The already existing exclusions (operator-set `MAINTENANCE`, other emergency reasons, moved drones, already recovered missions, full Hubs) are still covered.

Verification: backend ruff and format clean; `pytest` 1116 passed; `pytest -m postgres` 70 passed; `mypy .` reports one error in the unmodified `tests/weather/test_rain_warning.py:208` (pre-existing). No frontend change.

### Activation (worker restart only)

- **Pre-flight:** revision 0018; API 200; the verified backup of Gate D1 present (577,146 bytes, same SHA-256); a read-only eligibility run with the new code listed exactly DRN-001, DRN-005, DRN-006, DRN-009 and DRN-010 (all `MANUAL`, none recovered before); every Hub was nearly empty (capacity 50).
- **Restart:** only the simulation worker (the old process, from 11:44, was stopped; the helper started the new one at 12:00:56 local time; the API and frontend were not touched). Its heartbeat was fresh at once and its log has no warnings or errors.
- **Recoveries (bounded batches):** at 12:00:57 DRN-009 and DRN-005 to Centrum Riviera and DRN-006 to Forum Gdańsk (a batch of three), and 5 s later at 12:01:03 DRN-001 to Galeria Bałtycka and DRN-010 to Centrum Riviera.
- **Verified in PostgreSQL:** five new `DRONE_RECOVERED` events (ids 2304 to 2308, origin AUTOMATIC, failure origin MANUAL, keys `DRONE_RECOVERED:<mission>`); nine in total over nine distinct missions, none duplicated (DRN-001 has two because it failed on two different missions). Each drone sits exactly at its Hub's coordinates with `hub_id` updated, kept its battery (96, 84, 92, 89 and 71 %) and became `CHARGING` (DRN-009 reached 100 % and `IDLE` within seconds); the five missions are still `EMERGENCY`, their flights still `EMERGENCY` with reason `DRONE_FAILURE`, their five failure events remain, and their orders keep their status (two are still `OUT_FOR_DELIVERY`). No drone is left in `MAINTENANCE`; the other nine drones changed only through normal charging and flying; Hub occupancy is far below capacity; events up to id 2222 still have the same MD5.
- **Modes:** the restart reset Automatic Dispatch (which had been switched back ON) to OFF; Random Incidents stays OFF; Automatic Orders is OFF. The operator can switch them on again in the UI. All nine emergency alerts remain listed and acknowledged (the acknowledgements survived the restart).
- **Not done:** no incident was triggered, no database reset, no dependency installed, no commit.

## 17. Final verification and known limits (2026-11-15)

### Verification

- Backend: `ruff check` and `ruff format --check` clean (190 files); `pytest` 1116 passed; `pytest -m postgres` 70 passed; `mypy .` reports one error in the unmodified `tests/weather/test_rain_warning.py:208` (pre-existing, not investigated).
- Frontend: `tsc -b`, oxlint and prettier clean; vitest 870 passed (66 files); production build succeeded.
- Database: migration 0018 applied to the development database (backup `%LOCALAPPDATA%\SkyFleet\backups\skyfleet-pre-0018-20261115-113659.dump`, 577,146 bytes, verified with `pg_restore -l`). `GET /api/flights` reads `incident_acknowledgements` directly; the temporary compatibility helper is removed.
- Live activation: the recovery worker recovered the four AUTOMATIC failures at 11:44 and, after the policy correction (§16), the five MANUAL failures at 12:00:57 to 12:01:03 in bounded batches. There are 9 `DRONE_RECOVERED` events on 9 distinct missions, none duplicated; no drone is left in `MAINTENANCE`; missions, flights, orders and the failure history are unchanged; the events up to id 2222 have the same MD5 as before the migration.
- Owner QA: the owner confirmed in live QA that the acknowledgement UI works correctly, and found the AUTOMATIC-only recovery bug that §16 fixed. **Not explicitly confirmed by the owner:** the phone-width layout of the overlay (jsdom cannot check it) and the visual "Drone recovered and returned to a Hub" line in a drone's Activity.

### Known limits

- An order interrupted before the handover stays `OUT_FOR_DELIVERY` (the 018C rule). Recovery moves the drone only and never resurrects, completes or changes an order; two such orders exist (the drones DRN-009 and DRN-001).
- The recovery step locks all Hubs briefly in each recovery transaction. That is fine with four Hubs and would need a narrower lock for many Hubs.
- Starting the worker resets Random Incidents, Automatic Dispatch and Automatic Orders to OFF (existing behavior); the operator switches them on again in the UI.
- Emergency flights are never dropped from `GET /api/flights`, so emergency alerts (acknowledged or not) accumulate in the response over time.
- There is no operator-initiated "Recover Drone" action; `recover_grounded_drone(wait_for_delay=False, origin=MANUAL)` supports one.
- Recovery places a drone at the nearest Hub with a free place; there is no repair duration beyond the fixed 120 s and no spare-parts or ground-crew limit (MVP simulation).

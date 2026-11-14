# Feature 020 — Rain Warning & Flight Grounding

**Project:** SkyFleet  
**Status:** Implemented and verified; not committed. Migration `0016` applied to the development database. Live QA run by the owner, who then requested finalization (decisions in `docs/decisions/0011-rain-warning-flight-grounding.md`)  
**Scope:** MVP, manually triggered global weather alert  
**Baseline:** commit `84966be` (after Feature 019B); Feature 020 Simulation Speed Control was discarded.

## 1. Goal

Demonstrate operational weather safety: when rain is forecast or detected, SkyFleet grounds **new drone takeoffs** until the weather alert is cleared. The operator can activate and deactivate the scenario live from the existing random-events/incident UI. The architecture should allow a future weather API and rooftop hub weather stations, but **no real integrations** are included now.

## 2. Scenario

1. All systems are operating normally; drones may be delivering orders or docked at hubs.
2. The operator clicks **Activate Rain Warning** in the existing event controls.
3. SkyFleet records a persistent, global rain warning and displays a prominent weather restriction state.
4. Any drone already airborne continues its active flight, including its normal return/landing behavior. No mid-flight pause, teleportation, or forced landing is introduced.
5. No new takeoff may start while the warning is active, regardless of whether it is initiated manually, by Auto Dispatch, or by automatic/manual relocation.
6. Orders remain available/queued, and existing non-airborne missions retain a consistent state. The warning must not silently cancel orders or missions.
7. The operator clicks **Clear Rain Warning**. New takeoffs become possible again under normal validation rules; queued work resumes through existing scheduling logic.

## 3. Business rules

### 3.1 Warning state

- Exactly one **global** rain warning state for the MVP: `ACTIVE` or `INACTIVE`.
- The state is backend-authoritative, persisted in PostgreSQL, and visible to all clients. It must survive API and worker restarts. Do not automatically clear it on startup.
- Activation and clearing are idempotent; repeated clicks must not generate duplicate incidents or activity noise.
- Store the activation and clearing timestamps in UTC and record operator/manual origin. Preserve history via the existing activity/event mechanism where practical.
- UI labels should clearly distinguish **forecast/precautionary grounding** from actual rain: e.g., “Rain warning — new takeoffs suspended.” Do not claim live meteorological data exists.

### 3.2 Flight safety gate

- The restriction applies at the **authoritative backend takeoff/start boundary**, not only in the UI. Every route to starting a flight must be covered.
- Block new outbound delivery launches, manual launches/confirmations that actually start a flight, automatic dispatch launches, and manual/automatic relocation launches.
- An already-airborne drone must be allowed to continue through subsequent route legs and phases, including return to a hub, diversions and safe landing. Do not block necessary in-flight transitions.
- An already-created but not-yet-airborne mission may remain pending; starting its flight must be rejected while the warning is active. Do not leave partial flight/mission/order mutations on rejection.
- Cancellation, recall of active missions, drone-failure handling, landing, and other safety actions remain usable.
- Manual API attempts return a clear, stable domain error (e.g. HTTP 409 `RAIN_WARNING_ACTIVE`), following existing error conventions. Automatic flows skip weather-blocked launches without repeated error events or tight retry loops.
- Avoid race conditions: activating the warning and authorizing takeoff must be serialized/transactionally checked so no takeoff is committed *after* the warning becomes active. Respect existing locking/transaction conventions.
- Do not use the removed simulation clock or Feature 020 endpoints.

### 3.3 UI and operator control

- Add **Rain Warning** to the existing random-event/incident controls, using the same interaction and visual conventions as earlier events.
- When inactive: **Activate Rain Warning** action. When active: **Clear Rain Warning** action, with an explicit active indicator.
- Show a concise global warning in the operations UI; do not obscure the map or existing controls.
- Disable or explain takeoff/relocation actions when blocked, while keeping backend enforcement authoritative. Existing queued orders and in-flight drones remain visible.
- Refresh warning state through the existing polling approach; no WebSockets.

### 3.4 Activity and observability

- Emit one durable activity event on activation and one on clearing (e.g., `RAIN_WARNING_ACTIVATED`, `RAIN_WARNING_CLEARED`), with human-readable descriptions and manual origin.
- Do not emit an activity entry on every worker tick or every skipped dispatch attempt.
- Provide a small API to read warning status and to activate/clear it; follow existing route naming, schemas and authorization patterns.

## 4. Implementation constraints

- First inspect the current codebase and its incident/event, dispatch, relocation, mission and worker flows. Reuse existing abstractions where possible.
- Prefer a small migration for persisted state if no suitable existing table/configuration exists. Do not invent a separate weather simulation engine.
- Keep existing 1-second worker tick and frontend polling.
- No external weather API, real rooftop sensors, rainfall intensity, forecast timeline, wind, geographic weather zones, rain particle effects, or autonomous diversion of airborne drones.
- No simulation speed controls, new simulation clock, or reintroduction of discarded Feature 020 code.
- No unrelated refactors.

## 5. Acceptance criteria

1. Operator can activate and clear the warning live from the existing incident/event UI.
2. Active warning is visible on dashboard and survives API/worker restart.
3. While active, **all** new delivery and relocation takeoffs are blocked through both manual and automatic entry points.
4. In-flight drones continue and complete their missions/returns without weather-induced interruption.
5. Pending orders and missions are not lost or incorrectly marked failed.
6. Once cleared, launches resume using normal dispatch/manual workflows without requiring a service restart.
7. Repeated activation/clearing is safe and does not duplicate activity events.
8. Error messages explain that takeoff is prohibited due to a rain warning.
9. Existing LPR, failure, cancellation, manual relocation and automatic rebalancing behavior does not regress.
10. Backend/frontend tests and Live QA demonstrate the above.

## 6. Suggested test coverage

- Activation, deactivation, idempotency and persistence across process restart.
- Manual delivery start and automatic dispatch blocked.
- Manual relocation and automatic rebalancing blocked.
- Pending mission confirmation/takeoff edge cases blocked without partial writes.
- In-flight OUTBOUND, RETURNING and RELOCATING continue normally.
- Landing/diversion/failure/recall/cancellation remain allowed.
- Race between warning activation and launch authorization.
- Queued work resumes after clearing; Auto Dispatch ON/OFF semantics remain unchanged.
- UI button state, status refresh, banner and API error handling.
- PostgreSQL migration upgrade/downgrade and focused integration tests.

## 7. Demo / Live QA script

1. Start worker and API; ensure a drone is already airborne and another is docked and eligible.
2. Open random events and activate **Rain Warning**.
3. Confirm visible active warning and a single Activity entry.
4. Attempt a new manual delivery and relocation; confirm they are blocked with an understandable reason.
5. Turn on Auto Dispatch or leave it on; confirm no new takeoffs occur while orders remain queued.
6. Observe the previously airborne drone completing its flight and landing normally.
7. Clear the warning; confirm one clearing Activity entry.
8. Verify a new takeoff can start and Auto Dispatch resumes under normal rules.
9. Reload the page and check the state remains consistent.

## 8. Explicitly deferred

- Strong wind event (separate future feature).
- Real weather forecast provider and rooftop station telemetry.
- Per-hub or geographic weather restrictions.
- Predictive mission feasibility based on forecast windows.
- Forced landing, rerouting or recall solely due to a rain warning.

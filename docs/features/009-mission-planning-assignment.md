# Feature 009 — Mission Planning & Assignment (Backend)

**Status:** Implemented and approved by the operator (verified; see section 10)  
**Scope:** Backend only. This feature plans, confirms and cancels missions. Takeoff, flight, landing and the landing-time capacity recheck are Feature 010; automatic dispatch is Feature 011; fleet rebalancing is Feature 012.

> Where this original specification and section 10 differ, section 10 (the approved, implemented behavior) is authoritative.

## Goal
Allow a SkyFleet operator to evaluate whether a delivery order can be served by a particular drone, and explicitly confirm an assignment that creates a persisted mission. This feature **does not start flights, move drones, consume battery, or deliver parcels**.

## Context
- Feature 003: persisted Hubs.
- Feature 005: DroneModel and Drone; MVP model SF-1 Courier (3 kg payload, nominal 20 km total range, ~12–14 km operational planning budget, 20% battery reserve).
- Feature 007: persisted orders and read-only API. Existing order status for seeded orders: `READY_FOR_PICKUP`.
- Feature 008: frontend order list and map markers.
- Business flow: partner hands parcel to a Hub; drone delivers from that Hub to the customer, then returns to a suitable Hub. A Hub is both a parcel handover point and drone base.

## Scope
1. Add a `Mission` domain model and Alembic migration, with relationships to one order, one drone, origin Hub and planned return Hub. Store lifecycle status and creation/update timestamps. Follow established repository naming, Pydantic, SQLAlchemy and migration conventions.
2. Add a **read-only planning/feasibility operation** for a selected order and drone. Return a clear eligible/ineligible decision, reason codes and estimated route distances. Planning must not mutate orders, drones, or missions.
3. Add an **explicit operator-confirmed assignment operation**. Recheck eligibility at confirmation time in a transaction, create a mission, and record the order-to-mission relationship. Prevent two active missions from claiming the same order or drone, including concurrent requests.
4. Add mission read endpoints for inspection, including lookup by ID and list. Document request/response contracts in the plan before implementation; use repository's `/api/...` conventions.
5. Add automated tests for successful planning/assignment, rejections, state consistency, transaction rollback and concurrency/uniqueness. Verify migration and endpoint behavior against the development PostgreSQL instance if available, without touching protected environment files.

## Planning rules (MVP)
- An order must be in `READY_FOR_PICKUP` to be assignable. Do not invent or silently rename existing backend enum values; inspect the actual code first.
- A drone must be in an available, non-flying state suitable for dispatch. Confirm the actual drone status enum and whether it has a current Hub before implementing. A drone already committed to an active mission is not eligible.
- Order weight must not exceed the selected DroneModel payload (3 kg for SF-1), using model data rather than a second hard-coded constant.
- The drone must be at the order's origin Hub for the MVP. If actual persisted drone location / Hub association differs, surface this as a planning decision, not a silent approximation.
- Compute route as origin Hub -> customer -> return Hub, using geodesic (great-circle / Haversine) distance. Choose the nearest suitable return Hub by distance to the customer, with deterministic tie-breaking (suitable: reachable with the parcel still on board and with a free *physical* place; see section 10). This is a **simplified estimate**, not an airspace-aware or road route.
- Apply a conservative configurable operating distance budget consistent with the existing business rules (~12–14 km total, subject to the codebase's canonical rule) and a minimum 20% battery reserve. Do not claim precise energy prediction: specify and test a transparent, conservative battery-feasibility approximation, or flag the rule for approval if repository context is insufficient.
- Invalid order/drone, missing location, overweight parcel, insufficient battery, excessive route distance, unavailable drone, or duplicate active assignment must produce clear, consistent failures.
- Planning and assignment must not change the drone's physical position, battery percentage, or flight status. Any order status change should use the **existing** order state machine and be explicitly justified in the implementation plan; do not introduce a fake delivery-in-progress state.

## Data integrity and concurrency
- Preserve foreign keys and check constraints consistent with existing conventions.
- Prevent duplicate active assignments for both orders and drones at the database/transaction layer (not merely a pre-check); define what 'active' means in the proposed mission status model.
- Assignment must be atomic. If anything fails, neither the mission nor the order is left partially assigned.
- Avoid overengineering future fleet scheduling, optimization, charging and flight telemetry.

## Out of scope
- Automatic assignment, AI suggestions, dispatch scheduler or batch optimization.
- Frontend assignment controls (future feature).
- Landing-slot or capacity reservations of any kind (decided: none), Hub locks, reservation counters or tables.
- Flight movement, ETA simulation, battery drain, delivery completion and drone return (Feature 010 or later).
- Real-world aviation routing, weather, airspace restrictions, legal flight permissions or precise battery physics.
- Order creation UI and partner portal.

## Acceptance criteria
1. A valid ready order and eligible drone produce a deterministic plan with route legs, total estimated kilometers, planned return Hub and feasibility information, with **no database changes**.
2. An operator can confirm a feasible plan; exactly one persisted active mission links the order and drone and can be retrieved through the API.
3. Invalid or infeasible combinations return actionable reasons and do not change data.
4. Concurrent confirmations cannot assign the same order or drone to multiple active missions.
5. Assignment does not initiate a flight, move a drone or drain its battery.
6. Alembic migration upgrades successfully; all lint, formatting, type-check and test checks pass.
7. Existing Hubs, Drones and Orders APIs and frontend behavior remain unchanged unless an explicitly approved contract update is required.

## Decisions Claude Code must surface before implementation

_All five were decided with the operator before implementation; see section 10._
1. Exact mission statuses, and whether an order changes from `READY_FOR_PICKUP` to an existing assigned state upon confirmation.
2. API shapes for plan preview, assignment confirmation, and mission reads.
3. How the current schema represents a drone's Hub and how availability is determined.
4. Exact operational distance and battery estimate formula, aligned with `context/business-rules.md` and DroneModel data.
5. How PostgreSQL enforces uniqueness of active missions, including concurrent assignment attempts.

## Workflow
- Start a new Claude Code session and run `/feature-start 009`.
- Inspect `CLAUDE.md`, relevant `context/` documents, current models/migrations and Feature 007/008 implementations.
- Produce a focused plan and **stop for user approval**. Do not implement yet.
- After approval: `/task-implementation`, QA subagent, code-review subagent, user verification, `/feature-finalization`.
- Finalization must not commit or push without explicit user approval.
- Do not read or modify protected `.env` / `.env.local` files.

## 10. Implementation and verification (recorded at finalization)

### Decisions applied (approved before implementation)

1. **Order readiness:** the order lifecycle starts with a customer depositing the parcel in a partner parcel locker, after which it is transported to the selected Hub, so an order can exist before the parcel reaches the Hub. The existing statuses (`CREATED`, `AWAITING_HANDOVER`, `READY_FOR_PICKUP`) are kept; only `READY_FOR_PICKUP` (physically confirmed at the origin Hub) is assignable. Assignment is derived from the mission; there is no order `ASSIGNED` status and the order status never changes. No parcel-locker integration.
2. **Mission statuses:** `ASSIGNED`, `IN_FLIGHT` (reserved for Feature 010, never set here) and `CANCELLED`. Active means `ASSIGNED` or `IN_FLIGHT`.
3. **Hub occupancy is physical presence only; no reservations.** A drone counts at a Hub only while docked there (status not `IN_FLIGHT`, stored position within 50 m of the Hub, nearest Hub wins, ties to the lower Hub id). An in-flight drone counts nowhere. Assignment and cancellation never change occupancy; active missions reserve nothing; there are no reservation tables, counters, release mechanisms or Hub locks. The 50 m rule is a documented simulation approximation: docking and charging hardware will be authoritative later, and `Drone.hub_id` is only the administrative assignment.
4. **Energy model** (simulation assumptions, not certified performance): empty rate `100 / max_range_km` % per km (5% for the SF-1); loaded rate = empty rate × (1 + `MISSION_PAYLOAD_ENERGY_FACTOR` × weight / max payload), default factor 0.5. Expected energy = outbound km × loaded rate + return km × empty rate. Worst case = total km × loaded rate (the parcel never leaves the drone). Required battery = worst case + the model's minimum reserve (20%); exactly the required level passes. The total distance must stay within the model's `recommended_mission_range_km` (14 km). Example (5 km out, 5 km back): a 0.3 kg parcel needs 72.5%, a 3 kg parcel needs 95%.
5. **Return Hub:** the nearest Hub to the destination (great-circle, ties to the lower id) that is within the distance budget and battery requirement for the worst case and has a free physical place; it may be the origin Hub. A drone docked at a Hub vacates its own place on takeoff, so it can plan to return there. The planned return Hub is a planning-time choice, not guaranteed or reserved.
6. **Cancellation:** `POST /api/missions/{id}/cancel` returns 200, 404 (unknown) or 409 `MISSION_NOT_CANCELLABLE` (already cancelled, or not `ASSIGNED` such as `IN_FLIGHT`). It frees the order and the drone and changes no occupancy.
7. **Preview and ids:** read-only `GET /api/missions/plan`; mission ids are `MIS-` plus 8 hexadecimal characters (the primary key guarantees uniqueness; a repeated id is retried).
8. **Configuration:** `mission_payload_energy_factor` (`MISSION_PAYLOAD_ENERGY_FACTOR`, default 0.5) and `hub_dock_proximity_m` (`HUB_DOCK_PROXIMITY_M`, default 50) in `app/config.py`, documented in the README. Protected `.env` files were not read or modified.

### Feature boundaries

| Feature | Responsibility |
|---|---|
| 009 (this) | Mission preview, validation, confirmation, cancellation; energy validation; return-Hub selection at planning time |
| 010 | Flight simulation: takeoff (mission `IN_FLIGHT`), landing, battery updates, **recheck of Hub capacity before landing and re-picking a reachable Hub if the planned one is full; occupancy never above 50** |
| 011 | Autonomous drone assignment and dispatch |
| 012 | Automatic fleet rebalancing: target about 40 physically present drones per Hub (80%), about 10 free places; 40 is not a hard landing limit (temporary occupancy above 40 allowed, never above 50); must consider battery, destination capacity, drone availability and operational demand |

### Delivered (backend only; no frontend, no Hubs/Drones/Orders API change, no new dependency)

- `app/missions/{models,schemas,repository,presence,routing,energy,capacity,planning,service}.py` (routing, presence, energy and capacity are pure functions; the planner is one pure function shared by the preview and the confirmation), `app/api/routes/missions.py`, migration `0004_create_missions.py`.
- Endpoints: `GET /api/missions/plan?order_id=&drone_id=` (always 200 with `eligible`, `reasons`, route, energy block, `distance_budget_km`, Hub occupancy, skipped return Hubs and notes; 404 unknown id; 422 missing or empty parameters), `POST /api/missions` (201; 404; 409 `MISSION_NOT_ELIGIBLE` with the full plan; 422), `POST /api/missions/{id}/cancel`, `GET /api/missions`, `GET /api/missions/{id}`.
- **Reason codes (final):** `ORDER_NOT_READY`, `ORDER_ALREADY_ASSIGNED`, `DRONE_ALREADY_ASSIGNED`, `DRONE_NOT_AVAILABLE`, `DRONE_NOT_AT_ORIGIN_HUB`, `OVERWEIGHT`, `ROUTE_TOO_LONG`, `INSUFFICIENT_BATTERY`, `RETURN_HUBS_FULL`. All that apply are reported together. `NO_SUITABLE_RETURN_HUB`, proposed in the plan, was **removed**: once the nearest Hub passes the range checks, having no return Hub can only mean every reachable Hub is full, so it was unreachable.
- **Mission row:** order, drone, origin Hub, planned return Hub, status, a snapshot of the route legs and both energy figures, timestamps. The order, drone and Hub rows are never written.
- **Transactions:** confirmation locks the order row, then the drone row (`SELECT ... FOR UPDATE`, refreshing already-loaded rows), recomputes the plan, inserts and commits; a unique-index conflict rolls back and returns 409; only a genuine id collision is retried. Cancellation locks the mission row. No Hub locks.
- **Database guarantees:** foreign keys with `RESTRICT`; CHECKs on status and non-negative distances and energy; two partial unique indexes (`uq_missions_active_order`, `uq_missions_active_drone`) where `status IN ('ASSIGNED', 'IN_FLIGHT')`.
- Two comment-only edits (`drones/models.py`, `drones/seed.py`) so the capacity wording matches the physical-presence rule; the seed's assigned-drone capacity check is unchanged (every seeded drone starts docked at its Hub).
- `pyproject.toml`: an opt-in `postgres` test marker (deselected by default).

### Occupancy-rule consistency check (before finalization)

Confirmed in code and tests: only docked drones count; in-flight drones count nowhere; the planner receives drones only, never missions, so assignments cannot reserve capacity; no reservation table, counter or release exists (the only new table is `missions`, and the only locks are on order, drone and mission rows); the landing-time recheck is deferred (documented in `capacity.py`, the plan notes and the README); no 40/50 threshold or rebalancing code exists. One gap found and fixed: a unit test named "an active mission reserves no capacity" did not create a mission, so it was replaced by an API test that confirms a mission returning to a Hub with one free place and shows the next plan can still use it.

### Migration and verification

| Check | Result |
|---|---|
| `ruff check`, `ruff format --check`, strict `mypy app tests` | Passed (re-run at finalization) |
| `pytest` (SQLite, default suite) | Passed: 202 tests (91 before this feature) |
| Migration 0004 on SQLite: upgrade keeps Hubs, drones and orders; downgrade to 0003 drops only `missions`; model/migration parity; constraints and partial unique indexes enforced by the migrated DDL | Passed |
| `pytest -m postgres` (real PostgreSQL 17, uniquely named temporary database, dropped afterwards) | Passed: 7 tests (same-order race and same-drone race: exactly one mission; 8 identical confirmations: exactly one; independent confirmations all succeed; two concurrent cancels: one 200, one 409; assign racing cancel; partial unique indexes present). The tests refuse any host other than local port 55432 |
| Development database | `alembic upgrade head` applied migration 0004 (revision `0004`); only the `missions` table and its two partial unique indexes were added; 4 Hubs, 12 drones and 10 orders intact; no mission was created; read-only preview checked against real data. Temporary test databases were verified dropped |
| `qa-tester` | Pass with gaps; no critical, high or medium findings |
| `code-reviewer` | Two Medium findings, fixed: missing host/port guard in the PostgreSQL test (now local port 55432 only) and the unreachable `NO_SUITABLE_RETURN_HUB` (removed). Low findings fixed: stale-row refresh on the retry path (`populate_existing`), retry only a real id collision, empty ids on `POST /api/missions` now 422, enum comparison |

Acceptance criteria 1 to 7 are covered by the tests above (criterion 4, concurrency, additionally on real PostgreSQL). There is no mission UI, so nothing was checked in a browser.

### Known limitations and follow-ups

- Return-Hub capacity is checked at planning time only and nothing is reserved, so the Hub may fill before landing. Feature 010 must recheck capacity before landing, re-pick a reachable Hub if needed, and never let occupancy exceed 50.
- Physical presence is approximated from status and stored position (50 m); the backend rule duplicates the frontend docking rule (`fleetPlacement.ts`) in a second language, kept aligned by matching boundary tests.
- The occupancy read at confirmation is not locked (by design). Feature 010 must take the same mission and drone row locks when it starts a flight.
- No Hub operational status exists, so every Hub counts as available; "suitable" beyond distance, reachability and free capacity is open (`business-rules.md` §8, Q2).
- After assignment an order still reads `READY_FOR_PICKUP` and the drone `IDLE` in the existing UIs; there is no mission UI yet.
- The energy figures and the 0.5 payload factor are simulation assumptions, not certified performance.
- The PostgreSQL concurrency tests are opt-in (`uv run pytest -m postgres`), so a default run does not exercise them. If every attempt to allocate a unique mission id failed (astronomically unlikely) the client would get a generic 500.
- Airspace and weather checks (Q7), parcel-locker integration, automatic dispatch and fleet rebalancing are out of scope.

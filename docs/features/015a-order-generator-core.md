# Feature 015A — Order Generator Core

## Status
Implemented and verified by automated tests; not committed. Acceptance criterion 9 (live verification on the development database) has not been run. No QA or code-review agent run.

### Implementation summary
- **Refinement approved at Initialize:** orders are assumed to have passed customer checkout validation, so the generator uses a curated catalog of **prevalidated routes** (origin Hub, delivery address and coordinates, safe weight range). It does not search candidates, retry, or duplicate the dispatch planner. Drone availability and battery are the dispatcher's concern.
- `backend/app/orders/generator_catalog.py`: `ROUTE_CATALOG`, 16 illustrative routes covering all four Hubs, including one cross-Hub route (Galeria Bałtycka to Podwale Grodzkie 2, returning to Forum Gdańsk). Coordinates are approximate simulation data.
- `backend/app/orders/generator.py`: `generate_one_order(session, *, rng=None, catalog=...)` picks a route and a weight (rounded to 0.1 kg, within the route's range) and calls the existing `create_order`. An injectable `random.Random` makes it deterministic in tests.
- `POST /api/orders/generate` (`backend/app/api/routes/orders.py`): no body, 201 with the standard `OrderResponse`; errors map through the existing order error handling.
- No migration, and no change to dispatch, planning, charging or flight simulation.

### Verification
- Backend: ruff and mypy pass; full suite 432 passed; PostgreSQL suite (`-m postgres`) 24 passed, including 24 parallel generations from 12 threads that produced distinct IDs and left existing orders unchanged.
- `tests/orders/test_order_generator.py` re-checks every catalog route at both weight bounds with `distance_km`, `hubs_by_distance`, `estimate_energy` and `has_enough_battery` (mission budget to the nearest return Hub and a full battery).
- Not run: live check on the development database (generate with Automatic Dispatch OFF and observe the order in Management).

## Goal
Provide a small, reusable backend service that creates **one realistic, valid simulated delivery order on demand**. This is the foundation for 015B (periodic generation) and 015C (operator controls), not a background generator yet.

## Context
- SkyFleet uses FastAPI, SQLAlchemy, PostgreSQL, a separate Simulation Worker, and an existing order creation flow.
- Four configured Hubs serve Gdańsk/Gdynia. Drone payload limit is 3 kg; the mission planner enforces route distance, battery, drone availability, and return-Hub capacity.
- Automatic Dispatch (014A–014C) consumes `READY_FOR_PICKUP` orders; 014D charges docked drones.
- Existing order schemas, creation service, validation, statuses, and persistence are the source of truth. Audit them before deciding the implementation details.

## Required behavior
1. Expose a small backend entry point that generates and persists **exactly one** simulated order per successful invocation. Prefer an explicit operator/developer-triggered API action if consistent with existing API conventions; propose the endpoint and response during Initialize.
2. Use the existing order creation service/validation and database model; do not bypass normal invariants or duplicate the order persistence path.
3. Select an existing Hub and a delivery destination from a **small, curated set of plausible real-world locations** in the Gdańsk/Gdynia area. Do not generate arbitrary map coordinates (e.g. in the sea). Keep the location data simple and auditable.
4. Choose an order payload within the existing allowed range (at most 3 kg), using the actual schema units and validation rules. Generate a unique order identifier through the project's existing mechanism, or introduce a concurrency-safe minimal mechanism only if necessary.
5. Ensure generated orders are structurally valid and geographically feasible under the **relevant static route/payload constraints**. Reuse the existing planning/geometry helpers where practical. Do **not** require an available 100%-charged drone, free capacity at the instant of generation, or an immediately dispatchable mission: orders may legitimately wait in the queue.
6. Persist the generated order in the existing `READY_FOR_PICKUP` workflow so Automatic Dispatch can discover it without changes to 014A–014D.
7. A failed attempt must not leave a partially created order. Use bounded candidate retries or a prevalidated location catalog; fail clearly if no valid candidate exists.
8. Preserve existing manually created and seeded orders. Never delete, reset, or overwrite historical orders as part of generation.
9. Keep generation independent of Automatic Dispatch ON/OFF. Generating an order does not itself start a mission or toggle automation.
10. Make the behavior testable and deterministic under a supplied random seed/injected RNG in tests, without requiring deterministic production output.

## Design constraints
- Minimal backend-first change. No new worker loop, periodic scheduler, ON/OFF state, rate controls, event simulation, or UI in 015A.
- No new external geocoding/maps API, dependency, or microservice.
- Avoid a migration unless the existing schema makes one essential; justify it during Initialize.
- Respect existing DB transaction patterns and concurrent order-ID creation.
- Do not silently alter dispatch, mission planning, drone charging, or flight simulation.
- Avoid assuming a destination is serviceable merely because it is near a Hub; use the current route budget and geometry assumptions. If full static feasibility cannot be checked without a live drone, explain and propose the smallest safe approximation.

## Suggested implementation approach (subject to audit)
- A curated destination catalog, with explicit Hub associations if appropriate.
- A reusable `generate_one_order(...)` service that uses existing order creation code.
- One small API route for manually triggering a single generation, with an ordinary JSON response that identifies the created order.
- Lightweight configuration/constants rather than a new database table for destination locations.

## Acceptance criteria
1. One API request creates exactly one valid, persisted `READY_FOR_PICKUP` order with a unique ID, selected Hub, plausible destination, and allowed payload.
2. The order appears in the existing orders API/UI and in 014A dispatch recommendations when eligible; if no drone is available, it remains queued rather than failing generation.
3. Repeated requests create distinct orders without overwriting earlier data; concurrent requests do not collide on IDs.
4. The generator never creates an obviously invalid destination or a payload outside existing limits.
5. Invalid/unavailable candidates produce a clear error with no partial database writes.
6. Generation works with Automatic Dispatch OFF and ON; it never toggles the mode or directly starts a mission.
7. Focused unit/integration tests cover valid generation, static feasibility, no available drone, concurrency/unique IDs where relevant, failure atomicity, and existing order regression.
8. Backend quality checks and applicable PostgreSQL tests pass. No frontend changes are required for this feature.
9. Live verification: with Automatic Dispatch OFF, generate one order and observe it in Management; optionally turn dispatch ON to verify normal consumption, only after operator approval.

## Explicitly out of scope
- 015B: automatic periodic order creation, independent simulation ON/OFF, worker integration, restart behavior.
- 015C: simulation controls, generation-rate settings, one-click UI.
- 015D: backlog caps, sustained-load protections, end-to-end long-running simulation.
- 016: cancellation, failed handoff, return-with-package, emergency or other delivery events.
- UI/UX polishing, dashboard analytics, fleet rebalancing, changing mission eligibility.

## Workflow
1. **Initialize:** inspect repository conventions, order schemas/services, ID generation, existing destination data, static route feasibility, and test setup. Propose the smallest implementation, endpoint, catalog format, and any risks. **Stop for approval. No code, database changes, or commit.**
2. **Start Implementation:** only after approval; implement, test, and report. Do not commit or Finish yet.
3. **Review and live test:** verify a generated order and dispatch interoperability.
4. **Finish:** update documentation, run final checks, commit only approved changes.

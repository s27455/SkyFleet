# SkyFleet — Progress Tracker

## Project Goal

Build **SkyFleet**, an autonomous urban drone delivery and AI operations platform simulating a drone logistics network across the Tricity area (Gdańsk, Sopot, and Gdynia).

**Delivery deadline: 14 November 2026.**

The project is a recruitment assignment for job. The priority is to deliver a polished, understandable, working application with a clear architecture, a useful interface, and a convincing operational simulation.

The simulation uses mock data and simulated events. It should behave consistently and look believable, without attempting to model real-world drone physics, actual flight control, or regulatory systems.

---

## Current Development Priorities

The implementation order is intentionally adjusted to prioritize visible progress and establish the application's foundation early.

1. Set up the repository and project structure.
2. Establish the frontend and backend foundations.
3. Build the dark Mapbox map focused on the Tricity area.
4. Implement Mall Pickup Hubs and display them on the map.
5. Connect the frontend map to the backend API.
6. Expand the operational domain: drones, orders, missions, and dispatch.
7. Implement the independent simulation runtime.
8. Add AI-powered operational assistance.
9. Test, polish, deploy, and prepare the recruitment demonstration.

**Important:** Do not implement later phases prematurely. Keep the scope focused on the current milestone and maintain working software throughout development.

---

## Phase 1 — Project Foundation & Repository Structure

**Priority:** Critical  
**Status:** Complete — skeleton implemented and verified (2026-11-11); GitHub remote `origin` configured and `main` tracks `origin/main`

### Objectives

- [x] Create the GitHub repository (`origin` is configured; `main` tracks `origin/main`).
- [x] Create separate frontend and backend application directories.
- [x] Add the project documentation and context files.
- [x] Create the root `CLAUDE.md` and configure project-level instructions for Claude Code.
- [x] Initialize the frontend application with the selected technology stack (Vite, React, TS, Tailwind v4).
- [x] Initialize the backend application with FastAPI (plus Simulation Worker heartbeat entrypoint).
- [x] Configure environment variables and example environment files.
- [x] Establish basic development commands and startup instructions.
- [x] Add a root README with an initial project description.
- [x] Verify that frontend and backend can run independently.

### Expected Result

A clean, understandable repository with a working frontend and backend skeleton, ready for feature development.

---

## Phase 2 — Mapbox Integration & Dark Operations Map

**Priority:** Critical  
**Status:** Core map working (task 001, verified in browser 2026-11-11) — remaining: pan limits, overlay/panel visual language

Task spec: `docs/features/001-mapbox-initial-setup.md`

### Objectives

- [x] Integrate Mapbox GL JS into the frontend.
- [x] Configure the Mapbox access token through environment variables (`VITE_MAPBOX_TOKEN`).
- [x] Display a map centered on the Tricity area.
- [ ] Configure the initial zoom, camera position, and map bounds. (Initial view fits the Tricity bounds; panning is not restricted yet — no `maxBounds`.)
- [x] Select and configure a dark map style appropriate for an operations dashboard (`dark-v11`).
- [x] Create a reusable map component with a clear separation from surrounding UI (`src/features/map/MapView.tsx`).
- [ ] Establish a consistent visual language for map overlays, markers, and operational panels.
- [x] Ensure the map resizes correctly with the application layout.

### Expected Result

A working, dark, Mapbox-powered map of the Tricity area that serves as the main visual workspace of SkyFleet.

### Scope Notes

- Use Mapbox rather than introducing multiple map providers.
- Do not build route visualization, live drone movement, or advanced geospatial features yet.
- Focus on a reliable map foundation and a polished initial presentation.

---

## Phase 3 — Mall Pickup Hubs

**Priority:** Critical  
**Status:** Complete — frontend slice with mock data (`docs/features/002-drone-hubs-map.md`, approved; manual map check passed on the earlier Hub set) and backend Hub model, seed and read-only REST API (`docs/features/003-hubs-backend-api.md`, approved; verified against PostgreSQL 17). Phase 4 (feature 004) later switched the frontend to this API.

### Objectives

- [x] Define the initial Hub data model (feature 003: `id` slug, `name`, `address`, `longitude`, `latitude`, `drone_capacity` = 50; no `status`/`city` field yet, added only when real data backs it).
- [x] Prepare a small set of realistic demo hubs located in malls across the Tricity area (task 002: Galeria Bałtycka, Forum Gdańsk, Centrum Riviera, Centrum Handlowe Osowa; local mock data in `frontend/src/features/hubs/mockHubs.ts`).
- [x] Implement the backend representation of Hubs (`backend/app/hubs/`, Alembic migration `0001`, idempotent insert-only seed).
- [x] Expose a REST endpoint for retrieving hubs (`GET /api/hubs`, `GET /api/hubs/{id}`).
- [x] Add visually distinct Hub markers to the Mapbox map (task 002, frontend mock data).
- [x] Implement marker interaction (mouse/touch/keyboard).
- [x] Display a hub information panel when a marker is selected.
- [x] Show basic information such as hub name, mall/location, illustrative operational status, and maximum drone capacity (50). Status is labelled as mock data.
- [x] Keep map rendering and hub data retrieval separate (`MapView` receives `hubs` as a prop; `getHubs()` is the future API swap point).

### Expected Result

Mall Pickup Hubs are represented as backend-managed entities and displayed as interactive markers on the map.

Selecting a hub should reveal its basic information.

### Scope Notes

- A Hub is both a parcel handover/pickup point and a drone base; there is no separate DroneBase or PickupStation entity (see `business-rules.md` §2).
- `drone_capacity` is the number of drones a Hub can accommodate (50 initially), not parcel capacity. Occupancy semantics are an open rule (`business-rules.md` §8, Q8); Phase 3 only exposes the capacity value.
- Use realistic but fictional demo data.
- Avoid implementing the complete hub management system at this stage.

---

## Phase 4 — First Frontend–Backend Integration

**Priority:** Critical  
**Status:** Complete — feature 004 (`docs/features/004-hubs-api-frontend-integration.md`, approved). Automated checks and an API/CORS smoke test against Docker PostgreSQL pass; rendering in a real browser was not verified by Claude.

### Objectives

- [x] Establish frontend-to-backend API communication (`src/api/client.ts`, `src/api/hubs.ts`).
- [x] Configure CORS correctly (Phase 1 allow-list; verified for `GET /api/hubs` with origin `http://localhost:5173`, rejected for `http://127.0.0.1:5173`).
- [x] Consume the hub retrieval endpoint implemented in Phase 3.
- [x] Fetch hub data from the backend (`useHubs`).
- [x] Display API-provided hubs on the map (component tests with a stubbed map; real-map rendering NOT VERIFIED in a browser).
- [x] Add loading and error states (with Retry).
- [x] Handle an empty hub collection gracefully.
- [x] Verify that frontend components do not depend on hardcoded hub data (mock source removed; no fallback).

### Expected Result

The map displays Mall Pickup Hubs retrieved from the backend API.

This is the first complete vertical slice of the application: backend data, API communication, and frontend visualization working together.

---

## Phase 5 — Core Operations Domain

**Priority:** High  
**Status:** In progress — Drone entity and read-only drone API done (feature 005, `docs/features/005-drone-fleet-backend.md`, approved). Order entity and read-only orders API done (feature 007, `docs/features/007-delivery-orders-backend.md`, approved). Mission entity with operator-confirmed assignment and cancellation done (feature 009, `docs/features/009-mission-planning-assignment.md`). Partner and Incident are not started; the System Event foundation exists (Feature 018A, below).

### Objectives

Develop the foundational operational entities and their relationships.

- [ ] Define the Partner entity.
- [x] Define the Drone entity (feature 005: `drone_models` with the single SF-1 Courier model, `drones` with Hub assignment, status, battery and position; read-only `GET /api/drones`, `GET /api/drones/{id}`).
- [x] Show the drone fleet on the map (feature 006, `docs/features/006-drone-fleet-frontend-integration.md`): Hub drone-count badges, Hub-panel drone list, small markers for `IN_FLIGHT` drones only. Implemented and tested; manual browser acceptance not yet verified.
- [x] Define the Order entity (feature 007: `orders` table with explicit origin Hub, destination address and coordinates, package weight 0 to 3.0 kg, confirmed initial states only, timestamps; read-only `GET /api/orders`, `GET /api/orders/{id}`; 10 seeded `READY_FOR_PICKUP` orders). No Partner entity, drone assignment or status transitions yet.
- [x] Show delivery orders on the map (feature 008, `docs/features/008-delivery-orders-frontend.md`): collapsible orders list, order detail panel, small destination markers. Implemented and tested; manual browser acceptance not yet verified.
- [x] Define the Mission entity (feature 009: `missions` table, migration 0004, statuses `ASSIGNED` / `IN_FLIGHT` (reserved) / `CANCELLED`, partial unique indexes for one active mission per order and per drone).
- [x] Mission planning, confirmation and cancellation (feature 009: read-only `GET /api/missions/plan`, `POST /api/missions`, `POST /api/missions/{id}/cancel`, `GET /api/missions`, `GET /api/missions/{id}`; weight-aware energy estimate; return Hub chosen by physical capacity; no reservations; no flight, movement or battery change). Planning only: takeoff and landing are Feature 010, automatic dispatch Feature 011, fleet rebalancing Feature 012.
- [x] Drone management API (feature 011, `docs/features/011-drone-management-api.md`): `POST`, `PATCH` and `DELETE /api/drones`, backend only. Verified on SQLite (307 tests, ruff, mypy, QA and code review); PostgreSQL locking not verified (the PostgreSQL tests were skipped). Feature numbers 011 and 012 are now taken by the drone and order management APIs, so the "automatic dispatch = 011" and "rebalancing = 012" references in this file and in the 009 and 010 specs and `architecture-context.md` are stale; those features are unnumbered until scheduled.
- [x] Order management API (feature 012, `docs/features/012-order-management-api.md`): `POST`, `PATCH` and `DELETE /api/orders`, backend only; edits and deletes only for a mission-free `READY_FOR_PICKUP` order. Verified on SQLite (325 tests, ruff, mypy); independent QA and code review not run; PostgreSQL locking not verified.
- [ ] Define the Incident entity.
- [x] Define the System Event entity (Feature 018A: table `operational_events`, see Phase 7; only `ORDER_CREATED` is emitted so far).
- [ ] Establish relationships between the entities.
- [ ] Implement the essential CRUD endpoints.
- [ ] Add appropriate validation and error handling.
- [ ] Prepare initial demo data.

### Expected Result

The backend provides a coherent operational domain that can support dispatching, simulation, and frontend visualization.

### Scope Notes

- Keep the domain model practical and focused on the MVP.
- Do not introduce unnecessary abstractions or premature complexity.
- Prefer a small number of meaningful entities over an oversized model.

---

## Phase 6 — Deterministic Dispatch & Mission Management

**Priority:** High  
**Status:** In progress — Features 014A (read-only recommender), 014B (explicit dispatch execution), 014C (automatic dispatch mode) and 014D (automatic charging) done; fleet rebalancing not started

### Objectives

- [x] Dispatch decision, read-only (feature 014A, `docs/features/014a-dispatch-decision.md`): `GET /api/dispatch/recommendations` proposes order–drone pairs per Hub FIFO queue using the existing planner unchanged; creates, reserves and writes nothing. Verified by backend tests, ruff and mypy; no QA or code-review agent run. Only drones at exactly 100% battery are eligible and nothing recharges drones yet, so recommendations dry up after flights until charging exists. Planned follow-ups: 014B assignment and execution, 014C automatic scheduling (default off), 014D charging, 014E rebalancing.
- [x] Dispatch execution (feature 014B, `docs/features/014b-dispatch-execution.md`): `POST /api/dispatch/execute` creates and starts a mission for one chosen order–drone pair through the existing mission services, revalidated under locks with an extra 100% battery rule; a failed start leaves the mission `ASSIGNED` and reported. Verified by backend tests including concurrency tests on PostgreSQL, ruff and mypy; no QA or code-review agent run; not exercised on the development database. Still open: 014C automatic scheduling (default off), 014D charging, 014E rebalancing.
- [x] Automatic dispatch mode (feature 014C, `docs/features/014c-automatic-dispatch-mode.md`): an operator-controlled loop owned by the simulation worker, OFF by default and reset to OFF when the worker starts; mode stored in the database (migration 0006, table `dispatch_auto_state`); `GET /api/dispatch/auto/status`, `POST /api/dispatch/auto/enable` and `/disable`; header switch in the frontend. Verified by backend tests (including PostgreSQL concurrency tests), frontend tests and quality checks; no QA or code-review agent run; the full loop was not run end to end by the implementer. Still open: 014D charging, 014E rebalancing.
- [x] Automatic drone charging (feature 014D, `docs/features/014d-automatic-charging.md`): the simulation worker moves docked, mission-free drones below 100% to `CHARGING`, raises their battery at `SIM_CHARGE_RATE_PCT_PER_MINUTE` (default 20, demo-accelerated) and returns them to `IDLE` at exactly 100%, whatever the Automatic Dispatch mode is; no migration. Verified by backend tests (including PostgreSQL), ruff and mypy; no QA or code-review agent run; not run live on the development database. Operators cannot edit a charging drone through Feature 011 (follow-up). Still open: 014E rebalancing.
- [ ] Implement a deterministic Dispatch Engine.
- [ ] Identify eligible drones for an order.
- [ ] Filter candidates using basic operational constraints.
- [ ] Rank eligible drones using factors such as battery level, distance, estimated delivery time, and workload.
- [ ] Assign a suitable drone to an order.
- [ ] Create and manage missions. (Partly done: operator-confirmed assignment and pre-takeoff cancellation exist, feature 009; state transitions after takeoff are Feature 010, automatic assignment Feature 011.)
- [ ] Implement mission state transitions.
- [ ] Handle cases where no suitable drone is available.
- [ ] Record important dispatch decisions as system events.
- [ ] Planned: check simulated operating conditions (weather, airspace) before assigning a mission (`business-rules.md` §4; retry/status semantics open, Q7).
- [ ] Planned (Feature 012): fleet repositioning of idle, sufficiently charged drones between Hubs, respecting Hub `drone_capacity` and never interrupting an active mission. Target about 40 of 50 places occupied per Hub, about 10 free; temporary occupancy above 40 allowed, never above 50 (demand-based prioritization open, Q4).

### Expected Result

The system can assign orders to suitable drones using predictable, testable business rules.

### Scope Notes

- Dispatch decisions must remain deterministic and backend-controlled.
- AI may later explain or recommend improvements to dispatch decisions, but must not bypass operational constraints.

---

## Phase 7 — Simulation Runtime

**Priority:** High  
**Status:** Not started

### Objectives

- [ ] Implement a simulation process independent of the frontend.
- [ ] Establish the simulation lifecycle and configurable execution interval.
- [ ] Implement drone operational states.
- [ ] Simulate drone movement between pickup hubs and delivery addresses.
- [ ] Generate mock telemetry.
- [ ] Simulate Partner delivery request arrivals. (Partly done: Feature 015A, `docs/features/015a-order-generator-core.md`, creates one simulated `READY_FOR_PICKUP` order on demand via `POST /api/orders/generate`, picking a random route from a curated, prevalidated catalog (`app/orders/generator_catalog.py`) and creating it through the existing order service; no migration. The test suite re-checks every catalog route at both weight bounds with the planner's routing and energy helpers. Verified by backend tests (including a PostgreSQL parallel-generation test), ruff and mypy; no QA or code-review agent run; not run live on the development database. Feature 015B, `docs/features/015b-automatic-order-generation.md`, adds automatic generation: an Order Simulation mode of its own (migration 0007, table `order_simulation_state`; OFF by default, reset to OFF when the worker starts, independent of Automatic Dispatch), owned by the simulation worker, which creates one order through the 015A generator after each random pause of `ORDER_SIM_MIN_INTERVAL_SECONDS`–`ORDER_SIM_MAX_INTERVAL_SECONDS` (default 15–30 s); no order on enabling and no catch-up burst after a stall or restart. Generation pauses while `ORDER_SIM_MAX_OUTSTANDING_ORDERS` (default 20) orders are outstanding; every `READY_FOR_PICKUP` order counts, however it was created, and nothing is deleted. Endpoints: `GET /api/orders/simulation/status`, `POST /api/orders/simulation/enable` (503 while the worker heartbeat is stale) and `POST /api/orders/simulation/disable`. Verified by backend tests (including PostgreSQL), ruff and mypy; no QA or code-review agent run; the live demo of orders arriving was not observed by the implementer (the first live attempt returned 500 only because the development database was still at revision 0006; after `alembic upgrade head` the status endpoint returned 200). Known: while the table is missing the worker logs a traceback every tick. Feature 015C, `docs/features/015c-simulation-controls-ui.md`, adds the operator controls in the frontend (no backend change): an Order simulation section at the top of the Management Orders tab, separate from the Automatic Dispatch switch, with an ON/OFF switch, worker availability, `Waiting orders: N / M`, the last automatic outcome, and a Generate One Order button (`POST /api/orders/generate`, available whatever the mode is; the backlog cap applies to automatic generation only). It shows what the server reports, re-reads after every action, and handles loading, error with Retry, stale data and the 503 worker-unavailable message. The interval is still set in the backend configuration. Verified by frontend typecheck, lint, format check, 400 unit tests and a production build; no QA or code-review agent run; the live smoke test was not observed by the implementer. Still open: 015D backlog protections.)
- [x] Delivered orders lifecycle (Feature 017A, `docs/features/017a-delivered-orders-lifecycle.md`): a `DELIVERED` order stays in the active operational views for 120 s from its persisted delivery time (new nullable `orders.delivered_at`, migration `0009` with backfill from the flights, set by the flight engine), then drops out of them; the row is never deleted. `GET /api/orders` still returns full history; `GET /api/orders?active=true` applies the rule on the server (`app/orders/visibility.py`, setting `ORDER_DELIVERED_VISIBILITY_SECONDS`), and the map, orders list, counters and drone inspector use it. Management → Orders defaults to Active with an Active / All toggle; a selected order that leaves the active list is deselected. Verified by backend pytest (478 passed; 28 PostgreSQL-marked tests deselected, so `0009` was tested on SQLite only), ruff, mypy, frontend lint, typecheck, format check, 588 unit tests and a production build; `0009` applied to the development database with the owner's approval (84 delivered orders backfilled); no QA or code-review agent run; the live delivery-to-disappearance flow over about 120 s was not observed by the implementer. Still open: 017B delivery marker states (reuses the active list), 017C delivery coordinates and nearest-Hub return routing.
- [x] Delivery marker states (Feature 017B, `docs/features/017b-delivery-marker-states.md`): frontend only. Delivery-address diamonds show the order state from its backend status: gray *Waiting* (`CREATED`, `AWAITING_HANDOVER`, `READY_FOR_PICKUP`), blue *In delivery* (`OUT_FOR_DELIVERY`), green *Delivered*; unknown statuses are neutral; the state is also in the marker's accessible name and in a compact map legend. `MapView` updates markers in place by order id, so a status change keeps the same marker and a delivered order disappears only when the 017A active list stops returning it (no client timer). Related 017A fix found in live testing: the worker now stamps `orders.delivered_at` with the real UTC time of the delivery transition (the flight's `delivered_at` stays the scheduled timeline instant); the vanishing diamonds were caused by a worker still running pre-017A code, and development data was repaired twice by a one-off backfill (no migration). Verified by backend pytest (484 passed; 28 PostgreSQL-marked tests deselected), ruff, mypy, frontend lint, typecheck, format check, 609 unit tests and a production build; live data shows new deliveries carrying `delivered_at`; the full blue → green → expiry sequence, legend placement and contrast were not observed in a browser by the implementer; no QA or code-review agent run; workers have no auto-reload and must be restarted after backend changes. Still open: 017C delivery coordinates and nearest-Hub return routing.
- [x] Natural delivery locations and return-Hub bookkeeping (Feature 017C, `docs/features/017c-natural-delivery-locations-nearest-hub-return.md`): new generated orders get organic, non-repeating delivery points sampled around the Hubs (about 60% local, 30% medium, 10% cross-hub, as targets) inside an approximate operating polygon (`app/orders/operating_area.py`, explicitly not a land or sea mask), labelled `Delivery Point TC-0001` and checked with the mission planner's own routing and energy helpers; the old 16-route catalog is only a fallback. The nearest feasible return Hub was already implemented by the planner and the flight and is unchanged; `drone.hub_id` now means the Hub where the drone last docked successfully and is set only on a successful landing (a diversion that lands included), never in flight or after an emergency (no migration); the frontend label is "Current Hub". Verified by backend pytest (516 passed; 28 PostgreSQL-marked tests deselected), ruff, mypy, frontend lint, typecheck, format check, 609 unit tests and a production build; organic points on the real map and a real cross-hub return were not observed by the implementer; no QA or code-review agent run. Drones that landed elsewhere before this change keep their old `hub_id` until they next land. The development database orders, missions and flights were cleared at the owner's request before the live check.
- [x] Incident foundation and simulation controls (Feature 018A, `docs/features/018a-incident-foundation-simulation-controls.md`, decisions in `docs/decisions/0004-incident-event-foundation.md`): migration `0010` adds the append-only table `operational_events` (stable id, event type, real UTC `occurred_at`, origin `SYSTEM` / `AUTOMATIC` / `MANUAL`, optional order, mission, flight and drone references, all `ON DELETE RESTRICT`, short reason, bounded JSON details, unique `dedupe_key`). `append_event` writes inside the caller's transaction with `INSERT ... ON CONFLICT DO NOTHING ... RETURNING`, so a duplicate key neither raises nor aborts a PostgreSQL transaction (at-most-once per key, not exactly-once). `GET /api/events` is read-only and requires `order_id`, `mission_id` or `drone_id` (default limit 50, maximum 200, newest events returned oldest first). The only emitted event is `ORDER_CREATED`, written in the same transaction as the order (`MANUAL` for `POST /api/orders`, `AUTOMATIC` for generated orders, the Generate One Order button included); older orders have no events and show an empty timeline, nothing is backfilled. The technical `DELETE /api/orders/{id}` keeps its rules and now deletes the order's events in the same transaction; it is a maintenance tool, not cancellation (Feature 018B added the `CANCELLED` status, which keeps history). `DELETE /api/drones/{id}` is unchanged: a drone with events is refused with `DRONE_HAS_HISTORY`. Frontend: an Activity timeline in the order detail panel and a "Simulation events (demo only)" cluster in Management → Orders with four disabled controls (Cancel order, Drone failure, Recipient unavailable, LPR transit; inline SVGs, labelled "Coming in 018B/C/D/E") and a disabled Random incidents switch; no backend call, no trigger endpoint, no scheduler. Verified by backend pytest (533 passed; 30 PostgreSQL-marked tests deselected), the events tests including the PostgreSQL-marked ones on a temporary database (19 passed), ruff, ruff format, mypy, frontend lint, typecheck, format check, 617 unit tests and a production build; migration `0010` applied to the development database with the owner's approval (row counts unchanged) and a live API smoke test on it (new order produced exactly one `ORDER_CREATED`, eligible delete removed its events only, an order with a mission still returned 409); the owner reported the manual browser QA as passed. No QA or code-review agent run; the full PostgreSQL suite was not run. Known: the worker has no single-instance guard (two workers were observed running at once; a PostgreSQL advisory lock is a possible follow-up); a WebODM container publishing port 8000 made `localhost` resolve to the wrong listener, so keep `VITE_API_BASE_URL=http://127.0.0.1:8000`. Still open: 018B cancellation and recall, 018C drone failure, 018D failed delivery and parcel return, 018E LPR helicopter; active-incident state, trigger endpoints and random incidents are not implemented.
- [x] Order cancellation and drone recall (Feature 018B, `docs/features/018b-order-cancellation-drone-recall.md`, decisions in `docs/decisions/0005-order-cancellation-and-recall.md`): `POST /api/orders/{id}/cancel` is a business transition, not deletion. Migration `0011` adds the `CANCELLED` order status, `orders.cancelled_at` and `mission_flights.recalled_at`. Without an active mission the order is cancelled; with an `ASSIGNED` mission the mission is cancelled too and the drone is untouched; in flight, before the parcel is handed over, the flight's remaining legs are replaced by one loaded RECALL leg to the nearest reachable Hub (loaded consumption rate, existing landing and diversion logic), the mission stays `IN_FLIGHT` until the drone lands and `drone.hub_id` changes only then. A delivered order (or one past its delivery time) is refused with 409 `ORDER_ALREADY_DELIVERED`; a drone not flying normally is not recalled (409 `DRONE_NOT_RECALLABLE`); an already cancelled order returns 200 with no second event or recall; a defensive 409 `RECALL_NOT_POSSIBLE` changes nothing. An `ORDER_CANCELLED` event (origin `MANUAL`, dedupe key per order, recall Hub in `details`) is written in the same transaction, with locks taken in the engine's order (flight, mission, order, drone). A cancelled order stays in the active views for the same 120 s window as a delivered one (from `cancelled_at`), then only in the history. The technical `DELETE` is unchanged (a cancelled order is refused with `ORDER_NOT_EDITABLE`). Frontend: a Cancel order action with confirmation in Order Details, a shortcut for the selected order in Simulation events (order ids in the Management table are selectable), a red Cancelled marker with a legend entry, the recall shown as "Recalled: returning with the parcel" with the target Hub (also in Order Details), and an Activity timeline that refreshes at once; the other three incident controls and Random incidents stay disabled; no route polyline. Verified by backend pytest (561 passed; 32 PostgreSQL-marked tests deselected), the full PostgreSQL suite on a temporary database (32 passed, including concurrent cancellation and cancellation-versus-worker race tests), ruff, ruff format, mypy, frontend lint, typecheck, format check, 649 unit tests and a production build; migration `0011` applied to the development database with the owner's approval (rows unchanged); the owner reported the Live QA as passing after a frontend-only fix (the first UI hid the shortcut behind the Management overlay with no way to select an order). No QA or code-review agent run. Known: the MVP assumption that a recalled parcel stays on the drone and counts as returned when it lands, with no further handling, is a simplification, not an approved rule; the recall window is short (about 10 to 45 s after takeoff with default timings; `SIM_FLIGHT_MIN_SECONDS` and `SIM_FLIGHT_MAX_SECONDS` can slow flights); the migration downgrade with a cancelled order was not tested on SQLite (non-transactional DDL); one App test (Escape and focus) can fail under parallel load. Still open: 018C drone failure, 018D failed delivery and parcel return, 018E LPR helicopter.
- [x] Drone failure and emergency landing (Feature 018C, `docs/features/018c-drone-failure-emergency-landing.md`, decisions in `docs/decisions/0006-drone-failure-and-emergency-landing.md`): `POST /api/incidents/drone-failure` (no body) calls one backend service, `trigger_drone_failure`, that a future automatic trigger can reuse. It picks one eligible flying drone (flight in `OUTBOUND`, `DELIVERING`, `RETURNING` or `DIVERTING`, a 018B recall included; not already failed; next milestone not already due), locks flight, mission, order and drone in the engine's order, revalidates, and answers 200 or 409 `NO_ELIGIBLE_TARGET` (no event). Migration `0012` adds the nullable `mission_flights.failed_at`, the phase `EMERGENCY_APPROACH` (so `phase` is widened to 24 characters) and the emergency reason `DRONE_FAILURE`. The remaining legs are replaced by the leg flown so far plus one emergency leg to a deterministic simulated landing point 250 m ahead along the current heading (`SIM_EMERGENCY_LANDING_DISTANCE_M`; no GIS or terrain check); position and battery continue without a jump. The worker flies the approach and then grounds the drone: flight `EMERGENCY` with reason `DRONE_FAILURE`, mission `EMERGENCY`, drone `MAINTENANCE` at the landing point (never docked, dispatched or charged; no repair workflow). No new order status: an undelivered order stays `OUT_FOR_DELIVERY` and shows "Delivery interrupted by drone failure"; delivered and cancelled orders keep their status. An interrupted order stays in the full history and leaves the active views and the map 120 s after the emergency landing completes (real UTC `ended_at`). A `DRONE_FAILURE` event (origin `MANUAL`, `stage` and `landing_position` in `details`, dedupe key per mission) is written in the same transaction. Cancelling an order whose drone failed is refused with 409 `DRONE_FAILED` and an explanation (it never repairs or resets the drone). Frontend: the Drone failure control in Simulation events is live (pending, success, information for no target, error), a red emergency landing marker (pulsing on the approach, steady once grounded), a red-outlined failed drone, an Interrupted order marker and legend entry, and failure-aware Flight and Order Details sections. Random incidents stay disabled. Verified by backend pytest (589 passed; 34 PostgreSQL-marked tests deselected), the full PostgreSQL suite on a temporary database (34 passed, including concurrent triggers and failure-versus-cancellation-versus-worker races; it caught `phase` being too short for `EMERGENCY_APPROACH`), ruff, ruff format, mypy, frontend lint, typecheck, format check, 673 unit tests and a production build; migration `0012` applied to the development database with the owner's approval (`failed_at` present and empty, row counts unchanged, fingerprint of the finished flights identical); the owner reported the Live QA as passed. No QA or code-review agent run. Known: the approach window is short (about 5 to 20 s); a flight whose next milestone is already due is skipped, so a spurious `NO_ELIGIBLE_TARGET` is possible for about a second; the interruption of an order is derived from its flight, not stored on the order; the existing Management toggle can still return a `MAINTENANCE` drone to `IDLE` (operator override, out of scope); the SQLite downgrade with new values was not tested. Still open: 018D failed delivery and parcel return, 018E LPR helicopter.
- [x] Failed delivery and parcel return (Feature 018D, `docs/features/018d-failed-delivery-parcel-return.md`, decisions in `docs/decisions/0007-failed-delivery-and-parcel-return.md`): `POST /api/incidents/recipient-unavailable` (no body) calls one backend service, `trigger_recipient_unavailable`, that a future automatic trigger can reuse (`origin` parameter, default `MANUAL`). It picks an eligible delivery (flight `OUTBOUND` or `DELIVERING` of an `OUT_FOR_DELIVERY` order, not recalled, failed, delivered or already marked, handover not yet due, a Hub reachable from the destination with the parcel), locks flight, mission, order and drone in the engine's order, revalidates, and answers 200 or 409 `NO_ELIGIBLE_TARGET` (no event). The trigger only stores a pending outcome (`mission_flights.recipient_unavailable_at` and `recipient_unavailable_origin`); the drone still flies to the destination. At the delivery milestone the worker makes it real: the order becomes the new terminal status `DELIVERY_FAILED` (`orders.delivery_failed_at` = real UTC commit time; `delivered_at` is never set), the empty return is replaced by one loaded return leg to the nearest Hub reachable with the parcel (shared helper `nearest_reachable_hub`, also used by the 018B recall), `mission_flights.handover_failed_at` is set, and one `RECIPIENT_UNAVAILABLE` event is written in the same transaction with the trigger's stored origin (`MANUAL` today, `AUTOMATIC` for a future trigger; dedupe key per mission). The event is recorded at the failed handover, not at the trigger. Position and battery continue without a jump at the loaded rate; the existing landing and diversion logic docks the drone (`IDLE`, `drone.hub_id` only on landing), and the mission completes. A failed delivery stays in the full history and leaves the active views and the map 120 s after `delivery_failed_at`. Interplay: cancelling while the outcome is pending recalls the drone and the order stays `CANCELLED`; cancelling a `DELIVERY_FAILED` order is refused (409 `ORDER_NOT_CANCELLABLE`, with an explanation); a drone failure (018C) while pending wins and leaves the order interrupted; a drone failure on the way back keeps `DELIVERY_FAILED` (stage `HANDOVER_FAILED`). Migration `0013` adds the `DELIVERY_FAILED` status and four nullable columns (`orders.delivery_failed_at`, the three flight columns). Frontend: the Recipient unavailable control is live (pending message that does not claim a failure yet, information for no target, error), a violet Delivery failed marker and legend entry (`--color-status-failed`), the status in Order Details, the Orders list and history, a pending notice and a loaded-return phase label with the target Hub in the flight panel; Cancel is hidden for a failed delivery. Verified by backend pytest (619 passed; 38 PostgreSQL-marked tests deselected), the PostgreSQL suite on a temporary database (38 passed, including concurrent triggers and trigger-versus-worker, trigger-versus-cancellation and trigger-versus-drone-failure races), ruff, ruff format, mypy, frontend lint, typecheck, format check, 691 unit tests and a production build; migration `0013` applied to the development database with the owner's approval (target and revision `0012` confirmed, row counts unchanged, fingerprints of the finished orders and flights identical, new columns empty); the owner reported the Live QA as passed. No QA or code-review agent run. Known: the trigger window is short (roughly 10 to 60 s per flight; `SIM_FLIGHT_MIN_SECONDS` and `SIM_FLIGHT_MAX_SECONDS` can slow flights); a flight whose handover is already due is left to the worker, so a spurious `NO_ELIGIBLE_TARGET` is possible for about a second; the returned parcel counts as returned at landing and nothing more happens to it (MVP simplification, not an approved rule; no redelivery); the defensive fallback when no Hub is reachable at the attempt and the SQLite downgrade with a `DELIVERY_FAILED` order are not tested; `alembic check` still reports the unrelated `dispatch_auto_state` item. Still open: 018E LPR helicopter.
- [x] LPR helicopter and dynamic safety zone (Feature 018E, `docs/features/018e-lpr-helicopter-dynamic-safety-zone.md`, decisions in `docs/decisions/0008-lpr-helicopter-and-safety-zone.md`): a fictional, manually triggered scenario, not an aviation safety system. `POST /api/incidents/lpr-helicopter` starts one helicopter pass or answers 409 `LPR_ALREADY_ACTIVE`; `GET /api/incidents/lpr` returns the running scenario with the helicopter's position now (or `null`); the flights API adds `yielding_to_lpr`. Migration `0014` adds the table `lpr_scenarios` (the values the scenario started with, and a partial unique index that allows one `ACTIVE` scenario, so concurrent triggers cannot both succeed). The helicopter flies a fixed west-to-east corridor (latitude 54.3925, about 1.1 km north of Galeria Bałtycka and clear of the other Hubs) at 80 m/s with a 500 m zone (`SIM_LPR_SPEED_MS`, `SIM_LPR_ZONE_RADIUS_M`, `SIM_LPR_HOLD_MARGIN_M`, `SIM_LPR_CLEAR_EXTRA_M`; a pass takes about 3 minutes); its position is a pure function of the stored row and the clock, so nothing is written per tick and a restart loses nothing; the worker completes the scenario once its end time has passed and the zone ends by the clock even if the worker is down. Drones yield with a `HOLD` leg in the stored schedule: the leg flown is split where the drone stops, the hold is inserted and every later leg shifts later, so nothing teleports and the route, delivery stop and landing are unchanged, only later; the hold keeps the phase it interrupts and costs battery like cruising at the flight's original pace (loaded while the parcel is on board). Detection runs on each worker tick inside the flight's own transaction and is predictive: it solves the drone's scheduled path against the helicopter's route over a look-ahead of at least two ticks (longer if the worker is late), so a fast drone cannot cross the zone between ticks unnoticed and the result does not depend on tick timing. The drone stops at the edge of the helicopter's corridor (the hold distance either side of its route), so the zone passes beside it, flies on to that edge first if it is inside the corridor and can leave in time, and is released only when its own continued path is conflict-free. If the hold would take the battery below the critical floor, the drone neither flies on nor waits: it ends in the existing `BATTERY_CRITICAL` emergency where it stands, outside the zone (no new recovery workflow); its order stays `OUT_FOR_DELIVERY` and leaves the active views 120 s later like a drone-failure interruption. A failing drone (018C) is never held and a grounded drone never resumes; a recall (018B) cuts the hold and the recalled drone yields again if needed; the handover (018D) waits until the drone has really arrived and a loaded failed-delivery return keeps `DELIVERY_FAILED`. `LPR_TRANSIT` events record the scenario started and completed once each (no references) and the first yield of each mission once in its Activity, with the scenario's origin. A refactor made first: the delivery stop is found by kind (`delivery_leg`), not as `legs[1]`, in five places. Frontend: the LPR helicopter control (pending, started, information for "already active", error; disabled while one crosses), a helicopter marker and a translucent zone (GeoJSON layer, real size in metres at any zoom) that glides between polls, a legend entry, an amber outline and the label "Yielding to LPR helicopter" for a waiting drone (distinct from emergency and maintenance), and a truthful Order Details notice for a battery emergency before the handover. Verified by backend pytest (683 passed; 41 PostgreSQL-marked tests deselected), the PostgreSQL suite on a temporary database (41 passed, including duplicate triggers, completion racing a new trigger, and yielding racing cancellation, drone failure and marking), ruff, ruff format, mypy, frontend lint, typecheck, format check, 721 unit tests and a production build; migration `0014` applied to the development database with the owner's approval (target and revision `0013` confirmed, the table created empty, row counts and fingerprints of the finished orders and flights identical); the owner reported the Live QA as passed. No QA or code-review agent run. Known simulation limits (not guaranteed safety behavior): a drone already inside the corridor that cannot leave it in time stands still where it is and the zone then passes over it; holds are decided on worker ticks, so a stopped worker holds nothing; the scenario's started and completed events are not shown in an order's Activity (the events API needs an order, mission or drone filter); an order stopped by a battery emergency before the handover keeps the blue "In delivery" marker until it leaves the active views; the SQLite downgrade of `0014` was tested with no active scenario only; `alembic check` still reports the unrelated `dispatch_auto_state` item. Random or automatic incidents are not implemented and the Random incidents switch stays disabled.
- [x] Manual drone relocation (Feature 019A, `docs/features/019a-manual-drone-relocation.md`, decisions in `docs/decisions/0009-manual-drone-relocation.md`): in the drone details panel an operator picks a different Hub for an IDLE, docked drone; `GET /api/drones/{id}/relocation-plan?destination_hub_id=` previews feasibility and `POST /api/drones/{id}/relocate` starts an empty, timed Hub-to-Hub flight through the existing worker and flight engine (one reusable service, `simulation/relocation.py`, that the future 019B can call). Migration `0015` adds `missions.purpose` (`DELIVERY` / `RELOCATION`), makes `missions.order_id` nullable (a relocation has no order or parcel) and widens the flight-phase (`RELOCATING`) and event-type (`DRONE_RELOCATION`) checks. `drone.hub_id` changes only on landing; a full destination is handled by the existing landing diversion. Drone failure and the LPR hold work on a relocating drone; Activity shows the relocation for the drone. Verified by backend tests (719 passed), ruff, ruff format, mypy, a migration-versus-model drift check, frontend lint, typecheck, format check, 746 unit tests and a production build; migration `0015` was applied to the development database with the owner's approval (row counts unchanged). The four PostgreSQL concurrency tests (`tests/simulation/test_relocation_postgres.py`) were written but not run, and no QA or code-review agent was run. 019B (automatic rebalancing) is not implemented.
- [ ] Simulate mission progression.
- [ ] Implement post-delivery return to the nearest suitable Hub (with or without the parcel).
- [ ] Simulate charging and waiting at Hubs.
- [ ] Implement basic maintenance states at Hubs.
- [ ] Generate operational events. (Partly done: Feature 018A persists `ORDER_CREATED` only; no flight, dispatch or charging events yet.)
- [ ] Implement deterministic incident detection.
- [ ] Support pausing and resuming the simulation.
- [ ] Expose real-time updates through WebSocket.
- [ ] Planned: repeat the weather/airspace check immediately before takeoff; a simulated restriction may prevent or delay takeoff.
- [ ] Planned: simulate fleet repositioning between Hubs (rules from Phase 6).
- [ ] Planned: Hub occupancy monitoring — drones present at each Hub vs. `drone_capacity`, shown to the operator (counting semantics open, Q8).
- [ ] Planned: operator interventions (cancel/abort, request return, request landing) as backend-validated commands (exact semantics open, Q5).
- [ ] Planned, subject to MVP prioritization: contextual drone detail view with live telemetry and a 3D drone representation, driven by backend telemetry.
  - [x] Feature 016A (`docs/features/016a-drone-3d-model.md`): reusable procedural 3D quadcopter viewer (`Drone3DViewer`, React Three Fiber) with a dev-only preview at `/?preview=drone3d`; frontend only; used by the drone inspector from Feature 016B. Verified by frontend lint, typecheck, format check, 416 unit tests and a production build, plus headless-Chrome screenshots; no QA or code-review agent run. Still open: 016C simulated telemetry, 016D component selection and polish.
  - [x] Feature 016B (`docs/features/016b-inspector-navigation-layout.md`): an **Inspect Drone** button in the drone details panel opens a drone inspector overlay with the lazily loaded 3D model and the drone's real backend data (operational, flight, mission, payload, model specification; unreadable data shown as unavailable, never invented), with an empty reserved Diagnostics area. Escape closes only the inspector and the selected drone is kept; frontend only (the drone model gained five API fields already sent by `GET /api/drones`). Verified by frontend lint, typecheck, format check, 451 unit tests, a production build and a scripted headless-Chrome smoke test on desktop and narrow widths (flying-drone data injected in the browser only); no QA or code-review agent run; not observed on a real GPU or with touch input. Open at the time: the backend seeded SF-1 as a hexacopter while the 3D model has four motors (since resolved by the quadcopter-only MVP correction). Still open: 016C simulated telemetry, 016D component selection and polish.
  - [x] Feature 016C (`docs/features/016c-simulated-drone-telemetry.md`): a frontend-only, deterministic **Simulated telemetry** panel in the drone inspector (`frontend/src/features/telemetry/`): motors M1–M4 (temperature, RPM), battery (voltage, current, power, temperature) and connectivity, estimated from the drone's real status, battery, flight phase and parcel weight; labelled Simulated, with all reference ranges marked as estimates; no randomness, timers or persistence. Health (Nominal / Attention / Critical) follows explicit thresholds applied to the displayed readings; most drones stay Nominal and some have one warmer motor. MVP scope correction: the fleet is quadcopters only — SF-1 is seeded as `quadcopter` and migration `0008` (data only, guarded, reversible; applied to the local database) updated the existing row; any other airframe gets no motor telemetry. Verified by backend pytest (461 passed; 28 Postgres-marked tests deselected, so `0008` was tested on SQLite only), ruff and mypy, frontend lint, typecheck, format check, 511 unit tests and a production build, plus a scripted headless-Chrome smoke test (idle, in flight, charging, maintenance, low battery; desktop and narrow) run before the quadcopter-only correction and not repeated after it; no QA or code-review agent run; not observed on a real GPU or with touch input.
  - [x] Feature 016D (`docs/features/016d-interactive-diagnostics-polish.md`): the 3D model is the primary diagnostic interface of the drone inspector. Motors M1–M4 and the battery show telemetry-driven amber/red highlights and labels (the level also in words), and are selectable from the model, its labels and the telemetry list, with a synchronized details panel (readings, level, each check and threshold, all marked as estimates); the dev preview can force every level. The simulated telemetry now varies smoothly and deterministically over the flight progress (per-motor RPM waves of 2–5%, warm-up and cool-down), with display-only easing of the shown temperatures; health and highlights are computed from the shown readings, thresholds unchanged. Frontend only. Verified by frontend lint, typecheck, format check, 583 unit tests and a production build, plus scripted headless-Chrome smoke tests on desktop and narrow widths (selection from 3D, labels and list; forced states; a flying drone over about 20 polls; frozen identical polls); backend untouched; no QA or code-review agent run; not observed on a real GPU or with touch input. Open: narrow label chips are smaller than the 40 px touch target (the list is the touch route); one App test (Escape and focus restore) failed once under parallel load and passed on rerun. Feature 016 is complete.

### Expected Result

SkyFleet operates as a continuously running logistics simulation.

The frontend displays the state produced by the backend, but does not control the simulation lifecycle.

### Scope Notes

- The simulation must continue independently of whether the frontend is open.
- Use mock data and coherent state transitions.
- Do not attempt to implement realistic flight physics or real drone control.

---

## Phase 8 — AI Operations Intelligence

**Priority:** Medium  
**Status:** Not started

### Objectives

- [ ] Define the Fleet Operations Agent.
- [ ] Integrate an LLM through a controlled backend interface.
- [ ] Provide the agent with narrowly scoped operational tools.
- [ ] Support natural-language questions about fleet status, orders, missions, and hubs.
- [ ] Implement incident investigation using relevant telemetry and system events.
- [ ] Generate operational explanations and recommendations.
- [ ] Add human approval for any AI-proposed action that changes system state.
- [ ] Record approved AI-assisted actions as system events.

### Expected Result

An AI assistant that can inspect operational information, explain incidents, and help an operator make decisions.

### Scope Notes

- AI should provide interpretation and reasoning, not replace deterministic business logic.
- Do not give the model unrestricted database access.
- Do not allow unapproved AI actions to modify operational state.
- Prioritize useful functionality over the number of AI features.

---

## Phase 9 — Integration, Testing & UX Polish

**Priority:** High  
**Status:** Not started

### Objectives

- [ ] Verify the complete order-to-delivery workflow.
- [ ] Verify drone state transitions.
- [ ] Verify simulation behavior over time.
- [ ] Verify real-time frontend updates.
- [ ] Test API endpoints and important business rules.
- [ ] Test dispatch behavior and edge cases.
- [ ] Add appropriate frontend loading, empty, and error states.
- [ ] Improve visual consistency and responsive behavior.
- [ ] Review accessibility and usability.
- [ ] Remove unnecessary debug code and unused components.
- [ ] Verify that the application can be demonstrated reliably.

### Expected Result

A coherent, stable application that demonstrates the main SkyFleet workflow without requiring manual intervention.

---

## Phase 10 — Deployment & Recruitment Submission

**Priority:** Critical  
**Status:** Not started

### Objectives

- [ ] Choose and configure the deployment environment.
- [ ] Deploy the frontend.
- [ ] Deploy the backend API.
- [ ] Configure the database and persistence.
- [ ] Configure environment variables and secrets.
- [ ] Ensure the simulation worker runs independently in the deployed environment.
- [ ] Verify the public application URL.
- [ ] Prepare a Docker-based local setup if appropriate.
- [ ] Complete the README.
- [ ] Document the architecture and technology choices.
- [ ] Document how AI was used during development.
- [ ] Include `CLAUDE.md` and other required project instructions.
- [ ] Record a short GIF or MP4 demonstrating the application.
- [ ] Verify the public GitHub repository and submission requirements.

### Expected Result

A publicly accessible application and a complete GitHub repository ready for the job recruitment review.

---

## Development Rules

- Work on one clearly defined milestone at a time.
- Before implementation, inspect the existing code and relevant project documentation.
- Plan significant changes before writing code.
- Keep implementation tasks small and independently verifiable.
- Update this tracker when milestones or meaningful decisions change.
- Do not mark a task complete until its expected behavior has been verified.
- Keep frontend and backend responsibilities clearly separated.
- Avoid introducing infrastructure or abstractions without a concrete need.
- Prioritize a working end-to-end application over unnecessary architectural sophistication.

---

## Current Focus

**Active milestone: Phase 5 — Core Operations Domain** (Phases 1, 3 and 4 complete; Phase 2 core map done — pan limits and overlay visual language remain)

**Next milestones:**
1. Continue the operational domain (Phase 5): the Mission entity and operator-confirmed assignment exist (feature 009); partners are next, then flight simulation (Feature 010), automatic dispatch (Feature 011) and fleet rebalancing (Feature 012) (the Order entity and read-only orders API exist, feature 007; the orders are shown on the map and in a list, feature 008; the spec names assignment and flight execution as later features). Drones are seeded `IDLE` snapshots with no movement or status changes yet; the fleet is shown on the map (feature 006: docked drones as Hub badges, `IN_FLIGHT` drones as small markers). Verify the Hub, drone and order map once in a real browser (see the feature 006 and 008 specs). Hubs have no `status`/`city` fields in the API; the UI shows `address` only. Verify the Hub map once in a real browser (see feature 004 spec).

**Current confirmed decisions:**
- Mission planning (feature 009): Hub occupancy counts only drones physically docked (status not `IN_FLIGHT`, within 50 m of the Hub; a simulation approximation until docking hardware confirms presence). In-flight drones occupy no Hub; assignment and cancellation never change occupancy; there are no reservations, counters or reservation tables. Return-Hub capacity is checked at planning time only; Feature 010 must recheck before landing (never above 50 drones). Q8 is answered; Q2, Q4 and Q5 are partly answered (`business-rules.md` §8).
- Mission planning (feature 009): order readiness requires `READY_FOR_PICKUP` and assignment is derived from the mission (no order `ASSIGNED` status); the drone must be `IDLE` and docked at the origin Hub; weight-aware energy model with `MISSION_PAYLOAD_ENERGY_FACTOR` default 0.5 (simulation assumption), 14 km budget, 20% reserve, worst case assumes the parcel stays on board; a mission can be cancelled only while `ASSIGNED`; mission ids are `MIS-` plus 8 hex characters. The order flow starts with a customer deposit in a partner parcel locker, transported to the Hub (no locker integration).
- Drone map display (feature 006): a drone is "docked" when its status is not `IN_FLIGHT` and it is within 50 m of a Hub (MVP simplification; the same rule defines physical Hub occupancy, `business-rules.md` §2).
- Orders on the map (feature 008): unknown order statuses are rejected strictly (the frontend is updated when the backend adds one); timestamps shown in UTC; the orders list is closed by default and hidden on narrow screens while a panel is open.
- Orders (feature 007): status limited to the confirmed `CREATED`, `AWAITING_HANDOVER`, `READY_FOR_PICKUP`; later states are added when a feature needs them (business-rules Q1 stays open). Origin Hub is explicit. Drone assignment will belong to a future Mission entity (no `assigned_drone_id` on orders). Maximum package weight 3.0 kg (SF-1 payload) is an MVP order-acceptance rule; distance feasibility is a later planning concern.
- Drones (feature 005): one seeded model, SkyFleet SF-1 Courier (3.0 kg payload; specifications are simulation assumptions), 12 seeded drones (3 per Hub). The seed checks each Hub's assigned drones against its capacity (every seeded drone starts docked at its assigned Hub, so this bounds initial physical occupancy); at runtime, occupancy is physical presence (feature 009, `business-rules.md` §2).
- Initial demo Hubs (task 002): Galeria Bałtycka, Forum Gdańsk, Centrum Riviera (Gdynia), Centrum Handlowe Osowa, with owner-supplied coordinates; illustrative, not real partnerships.
- Map provider: Mapbox GL JS.
- Map appearance: Dark.
- Backend framework: FastAPI.
- Architecture direction: Modular monolith with a separate simulation worker.
- Simulation: Mock-based, backend-owned, and independent of the frontend.
- Dispatch: Deterministic business logic.
- AI: Controlled operational assistant with human approval for state-changing actions.
- Frontend tooling: Vite + React + TypeScript, Tailwind CSS v4, npm, oxlint, Prettier, Vitest + React Testing Library.
- Backend tooling: Python 3.13, uv, Ruff, mypy (strict), pytest.
- Database: PostgreSQL 17 in dev and prod; local instance via Docker Compose on host port 55432 (container 5432) with the named volume `skyfleet-db`; backend runs natively on Windows and connects via `localhost:55432`; the Windows PostgreSQL on port 5432 is never used or modified (see `docs/decisions/0001-postgresql-database.md`).
- Real-time bridge: worker persists events, API polls the DB and pushes over WebSocket (see `docs/decisions/0002-realtime-bridge-db-polling.md`).
- Git: default branch `main`; no pre-commit hooks for now.
- Business model and operational rules (B2B, Hubs as handover points and drone bases, return to nearest suitable Hub, etc.): see `business-rules.md`. Not duplicated here.

**Open decisions:**
- Frontend supporting libraries (e.g. server-state handling): feature 004 used plain `fetch` and a small hook; revisit only if polling/WebSocket state needs it.
- LLM provider — decide in Phase 8.
- Hosting provider and deployment configuration.
- Open business questions (order lifecycle after `READY_FOR_PICKUP`, suitable return Hub, returned-parcel handling, fleet balancing, operator interventions, emergency outcomes, weather/airspace retry, Hub occupancy semantics): tracked in `business-rules.md` §8. Resolve each only when the relevant feature needs it.

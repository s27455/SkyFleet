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
**Status:** In progress — Drone entity and read-only drone API done (feature 005, `docs/features/005-drone-fleet-backend.md`, approved). Order entity and read-only orders API done (feature 007, `docs/features/007-delivery-orders-backend.md`, approved). Mission entity with operator-confirmed assignment and cancellation done (feature 009, `docs/features/009-mission-planning-assignment.md`). Partner, Incident and System Event are not started.

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
- [ ] Define the System Event entity.
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
- [ ] Simulate Partner delivery request arrivals.
- [ ] Simulate mission progression.
- [ ] Implement post-delivery return to the nearest suitable Hub (with or without the parcel).
- [ ] Simulate charging and waiting at Hubs.
- [ ] Implement basic maintenance states at Hubs.
- [ ] Generate operational events.
- [ ] Implement deterministic incident detection.
- [ ] Support pausing and resuming the simulation.
- [ ] Expose real-time updates through WebSocket.
- [ ] Planned: repeat the weather/airspace check immediately before takeoff; a simulated restriction may prevent or delay takeoff.
- [ ] Planned: simulate fleet repositioning between Hubs (rules from Phase 6).
- [ ] Planned: Hub occupancy monitoring — drones present at each Hub vs. `drone_capacity`, shown to the operator (counting semantics open, Q8).
- [ ] Planned: operator interventions (cancel/abort, request return, request landing) as backend-validated commands (exact semantics open, Q5).
- [ ] Planned, subject to MVP prioritization: contextual drone detail view with live telemetry and a 3D drone representation, driven by backend telemetry.

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

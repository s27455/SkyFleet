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
4. Implement Drone Hubs and display them on the map.
5. Connect the frontend map to the backend API.
6. Expand the operational domain: drones, orders, missions, and dispatch.
7. Implement the independent simulation runtime.
8. Add AI-powered operational assistance.
9. Test, polish, deploy, and prepare the recruitment demonstration.

**Important:** Do not implement later phases prematurely. Keep the scope focused on the current milestone and maintain working software throughout development.

---

## Phase 1 — Project Foundation & Repository Structure

**Priority:** Critical  
**Status:** Skeleton implemented and verified (2026-11-11) — remaining: GitHub remote + first commit

### Objectives

- [ ] Create the GitHub repository (local repo + project structure done; remote not created yet).
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

Task spec: `docs/tasks/001-mapbox-initial-setup.md`

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

## Phase 3 — Drone Hubs

**Priority:** Critical  
**Status:** Planned

### Objectives

- [ ] Define the initial Drone Hub data model.
- [ ] Prepare a small set of realistic demo hubs located across the Tricity area.
- [ ] Define hub coordinates and basic operational properties.
- [ ] Implement the backend representation of Drone Hubs.
- [ ] Expose a REST endpoint for retrieving hubs.
- [ ] Add visually distinct Drone Hub markers to the Mapbox map.
- [ ] Implement marker interaction.
- [ ] Display a hub information panel when a marker is selected.
- [ ] Show basic information such as hub name, location, operational status, and available capacity.
- [ ] Keep map rendering and hub data retrieval separate.

### Expected Result

Drone Hubs are represented as backend-managed entities and displayed as interactive markers on the map.

Selecting a hub should reveal its basic operational information.

### Scope Notes

- Drone Hubs are distinct from Pickup Stations.
- A hub may serve multiple Pickup Stations.
- Use realistic but fictional demo data.
- Avoid implementing the complete hub management system at this stage.

---

## Phase 4 — First Frontend–Backend Integration

**Priority:** Critical  
**Status:** Planned

### Objectives

- [ ] Establish frontend-to-backend API communication.
- [ ] Configure CORS correctly (base allow-list configured in Phase 1; verify for hub requests).
- [ ] Consume the hub retrieval endpoint implemented in Phase 3.
- [ ] Fetch hub data from the backend.
- [ ] Display API-provided hubs on the map.
- [ ] Add loading and error states.
- [ ] Handle an empty hub collection gracefully.
- [ ] Verify that frontend components do not depend on hardcoded hub data.

### Expected Result

The map displays Drone Hubs retrieved from the backend API.

This is the first complete vertical slice of the application: backend data, API communication, and frontend visualization working together.

---

## Phase 5 — Core Operations Domain

**Priority:** High  
**Status:** Not started

### Objectives

Develop the foundational operational entities and their relationships.

- [ ] Define the Drone entity.
- [ ] Define the Pickup Station entity.
- [ ] Define the Delivery Point entity.
- [ ] Define the Order entity.
- [ ] Define the Mission entity.
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
**Status:** Not started

### Objectives

- [ ] Implement a deterministic Dispatch Engine.
- [ ] Identify eligible drones for an order.
- [ ] Filter candidates using basic operational constraints.
- [ ] Rank eligible drones using factors such as battery level, distance, estimated delivery time, and workload.
- [ ] Assign a suitable drone to an order.
- [ ] Create and manage missions.
- [ ] Implement mission state transitions.
- [ ] Handle cases where no suitable drone is available.
- [ ] Record important dispatch decisions as system events.

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
- [ ] Simulate drone movement between hubs, pickup stations, and delivery points.
- [ ] Generate mock telemetry.
- [ ] Simulate order arrivals.
- [ ] Simulate mission progression.
- [ ] Implement drone return-to-hub behavior.
- [ ] Simulate charging and waiting.
- [ ] Implement basic maintenance states.
- [ ] Generate operational events.
- [ ] Implement deterministic incident detection.
- [ ] Support pausing and resuming the simulation.
- [ ] Expose real-time updates through WebSocket.

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

**Active milestone: Phase 1 — Project Foundation & Repository Structure**

**Next milestones:**
1. Establish the repository and application structure.
2. Integrate Mapbox and configure the dark Tricity map.
3. Implement Drone Hubs and their map markers.
4. Connect hub data to the backend API.

**Current confirmed decisions:**
- Map provider: Mapbox GL JS.
- Map appearance: Dark.
- Backend framework: FastAPI.
- Architecture direction: Modular monolith with a separate simulation worker.
- Simulation: Mock-based, backend-owned, and independent of the frontend.
- Dispatch: Deterministic business logic.
- AI: Controlled operational assistant with human approval for state-changing actions.
- Frontend tooling: Vite + React + TypeScript, Tailwind CSS v4, npm, oxlint, Prettier, Vitest + React Testing Library.
- Backend tooling: Python 3.13, uv, Ruff, mypy (strict), pytest.
- Database: PostgreSQL in dev and prod; local instance via Docker Compose (see `docs/decisions/0001-postgresql-database.md`).
- Real-time bridge: worker persists events, API polls the DB and pushes over WebSocket (see `docs/decisions/0002-realtime-bridge-db-polling.md`).
- Git: default branch `main`; no pre-commit hooks for now.

**Open decisions:**
- Frontend supporting libraries (e.g. server-state handling) — decide in Phase 4.
- LLM provider — decide in Phase 8.
- Hosting provider and deployment configuration.
- Final initial set of demo Drone Hubs and their coordinates.

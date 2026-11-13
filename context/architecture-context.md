# SkyFleet — Architecture Context

## 1. Architecture Overview

SkyFleet is an autonomous urban drone delivery and AI operations platform built around a continuously running logistics simulation.

The system is designed as a **modular monolith with a separate Simulation Worker process**.

The architecture should provide clear domain boundaries, maintainable code, predictable operational behavior, and straightforward deployment.

The initial implementation should avoid unnecessary distributed infrastructure. Components should be separated according to their responsibilities without introducing microservices or infrastructure complexity prematurely.

Confirmed business rules and open business questions are maintained in `business-rules.md`. This document describes the architecture that implements them and must not restate or override them.

### Core Architectural Principles

- Clear separation between frontend and backend.
- Modular backend organized around business domains.
- Backend owns all operational state and simulation logic.
- Frontend focuses on presentation and user interaction.
- Deterministic business logic for operational decisions.
- Real-time communication for simulation updates.
- Controlled integration of AI through backend tools.
- Explicit and consistent domain state transitions.
- Testability and maintainability over unnecessary abstraction.

## 2. Technology Stack

The following technologies define the intended implementation direction.

### Frontend

- React.
- TypeScript.
- Tailwind CSS for styling.
- Mapbox GL JS for interactive maps.
- A suitable React state management solution, selected according to actual application complexity.
- REST API communication with the backend.
- WebSocket communication for real-time operational updates.

### Backend

- Python.
- FastAPI.
- Pydantic for data validation and API schemas.
- SQLAlchemy for database access and persistence.
- Pytest for automated testing.

### Simulation

- A separate Python Simulation Worker process.
- Shared domain logic and persistence with the main backend.
- Configurable simulation execution interval.
- Backend-controlled state transitions and event generation.

### AI Integration

- An LLM accessed through a controlled backend integration.
- Tool calling for retrieving operational information.
- Explicit approval for state-changing AI-assisted operations.

### Infrastructure

- Database: PostgreSQL 17 (see `docs/decisions/0001-postgresql-database.md`).
- Environment-based configuration and secret management.
- Docker and Docker Compose may be used to simplify local development and deployment.
- Frontend and backend may be deployed independently.
- The Simulation Worker must run independently of frontend sessions.

Do not introduce additional technologies without a concrete technical reason.

## 3. High-Level System Structure

The system consists of three primary logical areas.

### 3.1 Core Operations

Responsible for managing the business domain and operational workflows.

Modules:

- Partners
- Orders
- Drones
- Hubs (Mall Pickup Hubs)
- Dispatch
- Missions
- Charging (at Hubs)
- Maintenance (at Hubs)
- Incidents
- System Events

Responsibilities:

- Manage operational entities.
- Enforce business rules.
- Validate state transitions.
- Expose REST API endpoints.
- Coordinate dispatch and mission execution.
- Persist operational data.

### 3.2 Simulation Runtime

Responsible for continuously generating and processing simulated operational activity.

Components:

- Simulation Worker
- Flight State Engine
- Telemetry Generator
- Event Processing
- Incident Detection
- Simulation Lifecycle Management

Responsibilities:

- Generate incoming orders.
- Advance mission states.
- Simulate drone movement.
- Generate telemetry.
- Simulate battery consumption and charging.
- Detect simulated incidents.
- Update operational state.
- Produce events for frontend consumption.

The Simulation Worker must operate independently of the frontend and should not require an active browser session.

The main backend and Simulation Worker may run as separate processes while sharing application modules and persistence.

### 3.3 AI Operations Intelligence

Responsible for assisting operators in understanding and managing the simulated network.

Primary component:

- Fleet Operations Agent.

Responsibilities:

- Answer natural-language questions about the operational system.
- Retrieve relevant information through controlled backend tools.
- Investigate incidents.
- Explain operational decisions.
- Generate reports and recommendations.
- Propose selected operational actions subject to human approval.

AI must not bypass domain rules or directly manipulate persistence.

## 4. Backend Architecture

Use a modular backend structure with clear separation of responsibilities.

A logical organization may look like:

- `api/` — REST endpoints, request handling, and WebSocket interfaces.
- `domains/` — business entities, rules, and domain operations.
- `simulation/` — simulation lifecycle and runtime components.
- `ai/` — LLM integration, agent orchestration, and tool definitions.
- `infrastructure/` — persistence, configuration, and external integrations.
- `shared/` — common utilities and cross-domain primitives.

The exact directory structure may evolve as the project grows.

### Architectural Rules

- Keep API route handlers thin.
- Keep business logic outside HTTP route handlers.
- Keep domain logic independent of frontend implementation.
- Avoid unnecessary circular dependencies between domains.
- Use explicit interfaces between modules where appropriate.
- Validate incoming data at application boundaries.
- Keep persistence concerns separate from domain behavior where practical.
- Avoid creating abstractions without a concrete need.

## 5. Domain Model

The initial domain includes the following entities.

### Drone

Represents an autonomous delivery drone.

Potential attributes:
- Identifier.
- Name or model.
- Operational status.
- Battery level.
- Current location.
- Assigned mission.
- Operational capabilities.
- Simulated telemetry.

### Partner

Represents a SkyFleet business customer (restaurant, fast-food outlet, retail store in a mall) that submits delivery requests.

Potential attributes:
- Identifier.
- Name.
- Business type.

The end customer who ordered from the Partner is not a platform entity.

### Hub

Represents a Mall Pickup Hub: both a parcel handover/pickup point (typically inside a shopping mall) and the operational base of the drone fleet. Drone storage, charging, inspection, maintenance, and mission preparation take place at Hubs. There is no separate DroneBase or PickupStation entity.

Potential attributes:
- Identifier.
- Name.
- Mall / location description (e.g. floor or logistics area).
- Coordinates.
- Operational status.
- `drone_capacity` — maximum number of drones the Hub can accommodate (50 for the initial Hubs). This is drone capacity, not parcel or order capacity.

Occupancy counts only drones physically docked at the Hub (a drone in flight counts toward no Hub; missions reserve nothing; actual occupancy never exceeds 50). The MVP derives presence from drone status and stored position (within 50 m of the Hub), a simulation approximation until docking hardware confirms it. See `business-rules.md` §2.

Partners may use any available Hub; each Order names its pickup Hub.

### Delivery Address (not an entity)

There is no separate DeliveryAddress entity or table for the MVP. The delivery address (text, coordinates when available, optional delivery instructions) is stored directly on the Order.

### Order

Represents a B2B delivery request submitted by a Partner.

An order must reference:
- The originating Partner.
- The pickup Hub.
- The customer-provided delivery address (stored on the Order).

It also maintains a clear fulfillment status. Creating an Order does not mean the parcel has been handed over. The confirmed initial states are `CREATED`, `AWAITING_HANDOVER`, and `READY_FOR_PICKUP`. The states after `READY_FOR_PICKUP` are not yet finalized; define only the minimum transitions each feature needs (see `business-rules.md` §3 and §8).

There is no Partner-facing or end-customer-facing UI in the MVP. Orders are created manually by an operator or generated by the Simulation Worker.

### Mission

Represents an operational task assigned to a drone.

A mission may involve:
- Traveling to the pickup Hub.
- Collecting the parcel at the Hub.
- Traveling to the delivery address.
- Completing delivery.
- Returning to the nearest suitable Hub (see Section 6.2).

Feature 009 persists a mission as a planned assignment of one drone to one order. It stores the order, drone, origin Hub and planned return Hub, a status (`ASSIGNED`, `IN_FLIGHT` reserved for the flight simulation, `CANCELLED`), a snapshot of the route estimate and energy figures, and timestamps. A mission is active while `ASSIGNED` or `IN_FLIGHT`; database partial unique indexes allow at most one active mission per order and per drone. Whether an order is assigned is derived from its active mission (the order status does not change), and missions never write drones, orders or Hubs. Planning, confirmation and cancellation belong to Feature 009; takeoff, flight, landing and capacity rechecks belong to the flight simulation (Feature 010); automatic dispatch to Feature 011; fleet rebalancing to Feature 012.

### Incident

Represents a simulated operational problem requiring attention.

Incidents should reference relevant entities and preserve their status and history.

### Telemetry Record

Represents simulated technical measurements generated during drone operation.

Examples include:
- Battery level.
- Motor temperature.
- Battery temperature.
- Position.
- Speed.
- Other relevant simulated measurements.

### System Event

Represents an important event in the operational lifecycle.

Events provide an auditable history of state changes and operational decisions.

The final entity attributes, relationships, and state definitions should be specified when implementing each domain.

Implemented foundation (Feature 018A): the append-only `operational_events` table with a read-only `GET /api/events`; only `ORDER_CREATED` is emitted so far. See `docs/decisions/0004-incident-event-foundation.md`.

Do not over-engineer the initial domain model.

## 6. Operational Workflows

### 6.1 Order Fulfillment

A typical order workflow:

1. A Partner submits a delivery request; an order enters the system.
2. The order references the Partner, the pickup Hub, and the Delivery Address.
3. The customer deposits the parcel in a partner parcel locker and it is transported to the selected Hub (order states: `AWAITING_HANDOVER`, then `READY_FOR_PICKUP` once it is physically confirmed at the Hub). An order can exist before the parcel reaches the Hub.
4. The system evaluates available drones and simulated operating conditions (weather, airspace).
5. An eligible drone is selected: in the MVP an operator previews the plan, confirms it, and may cancel it before takeoff (Feature 009). Automatic selection and dispatch come later (Feature 011).
6. A mission is created.
7. Operating conditions are checked again immediately before takeoff.
8. The drone travels to the pickup Hub and collects the parcel.
9. The drone travels to the delivery address and waits for the recipient to collect the parcel.
10. Delivery is successful (recipient collected the parcel) or unsuccessful (the drone keeps the parcel). Either outcome must be recorded so that "returning with the parcel" is preserved.
11. The drone returns to the nearest suitable Hub.

The system must preserve consistent relationships between orders, missions, and drones. The detailed order lifecycle after `READY_FOR_PICKUP` is defined per feature; see `business-rules.md`.

### 6.2 Post-Delivery Return

After every delivery attempt the drone returns to the nearest suitable Hub, which may differ from the pickup Hub. After a successful delivery it returns without the parcel; after an unsuccessful one it returns with the parcel. Returned parcels are unloaded at the Hub.

For mission planning, "suitable" means reachable with the parcel still on board within the distance budget and battery reserve, and having a free physical place; a full Hub is skipped at planning time. The planned return Hub is not reserved, so the flight simulation (Feature 010) must recheck capacity before landing and pick another reachable Hub if needed. Suitability beyond that and handling of returned parcels remain open; see `business-rules.md` §8.

### 6.3 Charging, Maintenance & Fleet Balancing

At the Hub, a returning drone receives a quick post-flight inspection and then charges, enters maintenance if needed, or waits for another task.

Drone states must affect availability and eligibility for future missions. The simulation should represent these transitions consistently.

Idle, sufficiently charged drones may be repositioned between Hubs to balance fleet availability (a later feature, not part of mission planning). Repositioning must respect Hub `drone_capacity` and must not interrupt an active mission. The operational target is about 40 of 50 places occupied per Hub; demand-based prioritization remains open (`business-rules.md` §8).

## 7. Dispatch Engine

Dispatch is deterministic business logic implemented in Python.

Its responsibility is to select an eligible drone for an incoming order.

Potential evaluation factors:

- Payload capacity.
- Battery level.
- Distance to the pickup location.
- Estimated mission duration.
- Current operational status.
- Current workload.
- Relevant operational constraints.

The dispatch process should:

1. Identify eligible drones.
2. Filter candidates using operational constraints.
3. Rank remaining candidates.
4. Select the best candidate according to defined rules.
5. Record the decision and its reasoning.

The engine must be predictable, testable, and reproducible.

AI may later provide recommendations or explain dispatch decisions, but must not replace or bypass deterministic eligibility rules.

## 8. Simulation Architecture

The simulation is a backend-owned process that operates independently of the frontend.

### Simulation Responsibilities

- Generate mock orders.
- Advance drone movement.
- Progress missions.
- Generate telemetry.
- Simulate battery consumption.
- Manage charging and waiting.
- Generate operational events.
- Detect simulated incidents.
- Apply consistent state transitions.

### Simulation Design Principles

- Use a configurable simulation interval.
- Keep simulation logic independent of HTTP request handling.
- Avoid tying simulation execution to WebSocket connections.
- Ensure frontend disconnection does not stop simulation.
- Persist important operational state and events.
- Make simulation behavior testable.
- Prevent invalid or contradictory state transitions.

The simulation should be believable rather than physically accurate.

Do not implement real flight physics, hardware control, or unnecessary external integrations.

## 9. Event-Driven Internal Communication

Use domain events where they provide meaningful separation between operational processes.

Examples:

- `OrderCreated`
- `DroneAssigned`
- `MissionStarted`
- `ParcelCollected`
- `DeliveryCompleted`
- `ParcelHandedOverAtHub`
- `ChargingStarted`
- `IncidentDetected`

Events should help coordinate state changes and maintain an understandable operational history.

Do not introduce a message broker or distributed event infrastructure unless future requirements justify it.

For the MVP, an appropriately structured in-process event mechanism and persisted system event history are sufficient.

## 10. API & Real-Time Communication

### REST API

Use REST endpoints for:

- Retrieving operational entities.
- Creating and updating orders.
- Managing hubs and other resources.
- Inspecting drones and missions.
- Retrieving incidents and system events.
- Performing explicitly authorized operational actions.

Follow consistent resource naming, HTTP methods, response structures, validation, and error handling.

### WebSocket

Use WebSocket for real-time operational updates.

Potential updates include:

- Drone position changes.
- Telemetry updates.
- Mission state transitions.
- New orders.
- Incident notifications.
- Hub status changes.
- Simulation status.

The backend remains the source of truth. WebSocket messages communicate changes; they do not transfer ownership of operational logic to the frontend.

## 11. AI Operations Architecture

SkyFleet includes one primary Fleet Operations Agent.

The agent interacts with the application through explicitly defined backend tools.

Potential read-only tools:

- `get_fleet_status`
- `get_active_missions`
- `get_incident_details`
- `get_drone_telemetry`
- `get_dispatch_candidates`
- `get_hub_status`
- `get_order_history`

Potential controlled actions:

- `pause_simulation`
- `resume_simulation`
- `request_drone_return` (exact intervention semantics are open; see `business-rules.md` §8)
- `retry_dispatch`
- `create_maintenance_request`

### AI Design Rules

- Do not expose unrestricted database access to the model.
- Do not allow arbitrary SQL execution.
- Use typed, narrowly scoped tool interfaces.
- Validate all tool arguments.
- Keep operational rules in deterministic backend services.
- Require explicit operator approval for state-changing actions.
- Validate approved operations again on the backend.
- Record approved AI-assisted actions as system events.
- Provide understandable explanations for recommendations.

### Incident Investigation

Incident detection should be deterministic.

The system detects a simulated threshold violation or operational exception and creates an incident.

The AI agent may then retrieve relevant telemetry, mission information, and event history to explain what happened and recommend next steps.

AI is an investigation and decision-support layer, not a safety controller.

## 12. Frontend Architecture

The frontend is a presentation and interaction layer.

It communicates with the backend through REST and WebSocket interfaces.

### Frontend Responsibilities

- Render the operational dashboard.
- Display the Mapbox map.
- Display Mall Pickup Hubs, drones, and other relevant locations.
- Present orders, missions, and incidents.
- Visualize backend-provided telemetry.
- Provide contextual detail views.
- Display AI-generated explanations and recommendations.
- Send authorized operator actions to the backend.

### Frontend Rules

- Do not implement business-critical dispatch logic in React.
- Do not make the frontend the owner of simulation state.
- Keep API communication separate from presentation components.
- Use TypeScript types for API contracts.
- Handle loading, empty, and error states.
- Keep components focused and reusable.
- Avoid unnecessary global state management.
- Use Tailwind CSS consistently according to `ui-context.md`.

### Map & Geospatial Data

Mapbox GL JS is the selected map technology.

The initial map should focus on the Tricity area and use a dark visual style.

Map-related functionality should be separated from general dashboard presentation.

Geographic data should be provided by the backend where it represents operational entities.

The frontend may handle map rendering, visual marker placement, camera interactions, and presentation-specific transformations.

Do not hardcode operational entities in map components.

## 13. Persistence & Database

The database is **PostgreSQL 17** in development and production (ADR 0001).

Standard development setup:
- PostgreSQL runs in Docker Compose (`docker-compose.yml`, service `db`).
- Host port **55432** maps to container port 5432.
- Data is stored in the persistent named volume `skyfleet-db`.
- The FastAPI backend and worker run locally on Windows and connect through `localhost:55432`
  (`DATABASE_URL`, default in `backend/app/config.py`).
- The Windows PostgreSQL instance on port 5432 is unrelated to SkyFleet: never modify, stop, or use it.
- Schema changes go through Alembic migrations (`backend/migrations`). Backend unit and API tests use
  SQLite and do not need Docker.

Use SQLAlchemy to keep database access structured and maintainable.

## 14. Deployment & Runtime

The application should be accessible through a public URL for the recruitment demonstration.

The intended deployment model may include:

- Frontend hosted separately.
- FastAPI backend hosted as an API service.
- Simulation Worker running as an independent background process.
- Shared persistent database accessible to the required backend processes.

The exact hosting provider and infrastructure remain open.

Docker Compose may be used to provide a reproducible local environment.

### Deployment Principles

- The simulation must continue without an open browser.
- Store secrets in environment variables or the hosting provider's secret management.
- Never commit real API keys or credentials.
- Provide example environment configuration.
- Include clear startup instructions.
- Ensure the deployed frontend can communicate with the backend.
- Configure CORS explicitly.

## 15. Testing Strategy

Testing should focus on important business behavior and system boundaries.

Priorities:

- Domain logic and state transitions.
- Dispatch eligibility and ranking.
- Order and mission workflows.
- Simulation behavior.
- Incident detection.
- API validation and responses.
- Persistence behavior.
- AI tool validation and approval workflows.

Prefer focused unit tests for deterministic logic and integration tests for important workflows.

Do not pursue test coverage numbers at the expense of meaningful verification.

## 16. Architecture Decision Rules

When making architectural decisions:

1. Prefer the simplest solution that satisfies the actual requirement.
2. Preserve clear domain boundaries.
3. Keep operational logic in the backend.
4. Avoid premature microservices and distributed infrastructure.
5. Do not introduce dependencies without a clear benefit.
6. Prefer explicit and testable state transitions.
7. Consider deployment requirements early.
8. Document significant architectural decisions.
9. Keep the implementation aligned with the MVP and `progress-tracker.md`.

---

## 17. Architectural North Star

**SkyFleet should be a maintainable, modular operational platform in which deterministic backend services own the business processes, an independent simulation runtime drives the network, and the frontend provides a clear real-time view of the entire operation.**

AI should enhance operator understanding and decision-making without replacing predictable business logic.
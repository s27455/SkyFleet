# Feature 009 — Mission Planning & Assignment (Backend)

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
- Compute route as origin Hub -> customer -> return Hub, using geodesic (great-circle / Haversine) distance. Choose the nearest suitable return Hub by distance to the customer, with deterministic tie-breaking. This is a **simplified estimate**, not an airspace-aware or road route.
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

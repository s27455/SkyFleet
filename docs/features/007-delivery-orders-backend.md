# Feature 007 — Delivery Orders Backend

**Project:** SkyFleet  
**Status:** Implemented and approved by the operator (verified; see section 10)  
**Scope:** Backend only — FastAPI, PostgreSQL 17, SQLAlchemy, Alembic, tests  
**Depends on:** Feature 003 (Hubs API), Feature 005 (Drone Fleet Backend)

## 1. Goal

Introduce persistent delivery orders so the operator can see which packages await drone delivery. An order represents a package handed over at a SkyFleet Hub by a business partner, destined for a customer location. This feature stores and exposes orders; it does **not** dispatch drones, plan routes, execute flights, or provide a new UI.

## 2. MVP business context

- Partners hand packages over at one of the four existing Hubs. There is no Partner portal or separate DroneBase.
- One order represents one package and one delivery destination.
- The only drone model currently available is SF-1 Courier, with a **3.0 kg maximum payload**.
- A drone's future mission will be Hub → delivery point → suitable Hub. This feature does not select the return Hub.
- Order destination coordinates are simulation inputs, not proof of a real deliverable address or legal flight corridor.

## 3. Proposed data model

Add a `DeliveryOrder` model and an Alembic migration (the next available revision; do not assume a revision ID without checking the repo).

| Field | Suggested type | Meaning / constraint |
|---|---|---|
| `id` | String primary key | Stable human-readable ID such as `ORD-001` |
| `origin_hub_id` | Foreign key → `hubs.id` | Hub where the package was handed over; required |
| `destination_address` | Nonempty string | Display address, required |
| `destination_longitude` | Float | Valid longitude, −180 to 180 |
| `destination_latitude` | Float | Valid latitude, −90 to 90 |
| `package_weight_kg` | Numeric / decimal | Greater than 0 and at most 3.0 kg for MVP |
| `status` | Constrained string | Initial value `PENDING` |
| `assigned_drone_id` | Nullable foreign key → `drones.id` | Null until a later mission-assignment feature |
| `created_at` | Timezone-aware timestamp | Set on creation |
| `updated_at` | Timezone-aware timestamp | Set on updates; prepare for later lifecycle |

Follow existing repository conventions for naming, SQLAlchemy types, Pydantic schemas, timestamps, and database constraints. Use DB constraints where practical, and ensure API schemas reject malformed values. Do not add unnecessary tables or dependencies.

### Order status proposal (requires plan approval)

Use a small lifecycle that future features can build upon:

- `PENDING` — package is at the origin Hub, awaiting assignment.
- `ASSIGNED` — a drone has been allocated (Feature 009).
- `IN_DELIVERY` — delivery mission is underway (Feature 010).
- `DELIVERED` — package delivered to customer; drone may still be returning.
- `CANCELLED` — order cancelled before delivery.

**Feature 007 must only seed and expose `PENDING` orders.** No status-transition API or business logic is included now. Claude should check `context/business-rules.md` for any existing lifecycle terminology and flag conflicts instead of silently overriding it.

### Origin Hub selection (requires plan approval)

For MVP, each order explicitly references an existing origin Hub. Do **not** automatically choose the nearest Hub, infer it from the destination, or create a Partner model. Automatic selection may be introduced later.

### Drone assignment (requires plan approval)

Store a nullable `assigned_drone_id` only if it is compatible with the existing architecture and agreed future mission model. No drone assignment occurs in Feature 007. If the project docs already require assignments to belong exclusively to a future `Mission` entity, raise this during planning and omit the field for now.

## 4. API contract

Add read-only endpoints, consistent with the existing `/api/hubs` and `/api/drones` conventions:

- `GET /api/orders` — list orders, stable ordering (e.g. `created_at`, then `id`).
- `GET /api/orders/{id}` — retrieve one order; unknown ID returns HTTP 404.

Return typed JSON containing the order's identifiers, origin Hub reference, destination address and coordinates, package weight, status, optional assigned drone, and timestamps. Keep naming consistent with the existing API (`snake_case`). A nested Hub summary is optional only if already consistent with repository patterns; avoid introducing an extra endpoint for this feature.

**Out of scope:** POST/PATCH/DELETE endpoints, filtering/pagination, route computation, dispatch, assignments, operator actions, notifications, real geocoding.

## 5. Seed data

Add an idempotent, insert-only development seed for **8–12 example orders** distributed among the four existing Hubs. Use plausible destinations in the Tricity area and varying weights between 0 and 3.0 kg (exclusive of zero). All orders start as `PENDING`, without assigned drones.

- Use stable IDs (`ORD-001`, etc.) and deterministic values.
- Re-running the seed inserts only missing orders; it must not overwrite existing records.
- Do not delete existing Hubs, drones, orders, or Docker volumes.
- Validate that each origin Hub exists and report a useful error if prerequisites have not been seeded.
- Clearly mark addresses and coordinates as **illustrative simulation data**; do not claim they are verified customer addresses.

## 6. Implementation expectations

1. Inspect `CLAUDE.md`, `context/project-overview.md`, `context/business-rules.md`, `context/architecture-context.md`, `context/code-standards.md`, `context/ai-workflow-rules.md`, and `context/progress-tracker.md`, plus the current Hubs/Drone implementations.
2. During `/feature-start 007`, use `task-planning`, identify any conflicting business rules, and **stop for user approval** before editing code.
3. After approval and explicit `/task-implementation`, implement the model, migration, schemas, read-only API, seed, and tests.
4. Reuse existing backend conventions and test fixtures; no new infrastructure or dependencies unless justified and approved.
5. Run `qa-tester` and `code-reviewer` subagents; address blocking findings and report residual limitations.
6. Leave spec/tracker completion updates for `/feature-finalization`; never commit or push without separate approval.

## 7. Acceptance criteria

- [x] Alembic upgrade adds the orders table without altering or deleting existing Hubs and drones.
- [x] Database enforces valid origin Hub references, valid coordinates, positive weight up to 3 kg, and allowed status values where feasible.
- [x] Seed creates the expected example orders on first run and zero new records on second run.
- [x] `GET /api/orders` returns seeded orders with the agreed JSON schema.
- [x] `GET /api/orders/{id}` returns the selected order; an unknown ID returns 404.
- [x] Existing Hubs and Drones APIs continue working.
- [x] Automated tests cover API responses, schema validation, seed idempotency, missing references, and key constraints.
- [x] Ruff check, Ruff format check, strict mypy, and backend tests pass.
- [x] PostgreSQL 17 smoke test validates migration, seed, and endpoints without resetting the development volume (done once, in-process, against PostgreSQL 17.11; not an automated test).
- [x] QA and code-review subagents actually run and their findings are reported.
- [x] No frontend, simulation, mission planning, or autonomous AI behavior is added.

## 8. Known boundaries and follow-up features

- **Feature 008:** orders list/details and destination points on the frontend map.
- **Feature 009:** mission feasibility checks and operator-approved drone assignment (battery, payload, distance, availability).
- **Feature 010:** simulated flight execution and lifecycle transitions.
- **Feature 011:** live operations dashboard.

**Important:** The SF-1's 20 km nominal range and conservative 12–14 km operating distance are future *mission-planning* constraints. Do not reject an order solely because its destination is too far away in Feature 007; store it and let the later planning feature assess feasibility. The 3 kg weight limit, by contrast, is an explicit MVP order-acceptance rule proposed here and must be approved during planning.

## 9. Decisions for plan approval

1. Approve the proposed order statuses, especially the distinction between `DELIVERED` and a drone's later return to a Hub.
2. Approve explicit `origin_hub_id` instead of automatic Hub selection.
3. Decide whether `assigned_drone_id` belongs on `DeliveryOrder` now or should be introduced later through a `Mission` entity.
4. Approve the 3 kg maximum order weight and illustrative seed orders.

Do not silently resolve conflicts with existing project documentation. Surface them in the plan and wait for approval.

## 10. Implementation and verification (recorded at finalization)

### Decisions applied (approved with the plan)

1. **Statuses:** only the initial states confirmed in `business-rules.md` section 3 exist: `CREATED`, `AWAITING_HANDOVER`, `READY_FOR_PICKUP`. The proposal in section 3 above (`PENDING`, `ASSIGNED`, `IN_DELIVERY`, `DELIVERED`, `CANCELLED`) was **not** used: `PENDING` duplicated `READY_FOR_PICKUP`, and the lifecycle after it is open (business-rules Q1). Later states are added by a migration when a feature needs them. All seeded orders are `READY_FOR_PICKUP`.
2. **Origin Hub:** explicit `origin_hub_id` (foreign key to `hubs.id`, `RESTRICT`); no automatic selection, no Partner entity.
3. **`assigned_drone_id`:** omitted. Assignment will belong to a future Mission entity, so a column here would create a second place to reconcile.
4. **Weight:** greater than 0 and at most 3.0 kg (the SF-1 payload), enforced by a database CHECK; the model constant `MAX_PACKAGE_WEIGHT_KG` is tied to the SF-1 model value by a test. Ten illustrative orders `ORD-001`..`ORD-010` (3 + 3 + 2 + 2 across the Hubs).

### Delivered (backend only; no frontend, simulation, dependency or Hubs/Drones changes)

- `app/orders/{models,schemas,repository,seed}.py`, `app/api/routes/orders.py` (router registered in `main.py`), migration `0003_create_orders.py`, `migrations/env.py` import so Alembic autogenerate sees the table.
- `GET /api/orders` (ordered by `created_at`, then `id`) and `GET /api/orders/{id}` (404 when unknown), read-only (POST/PATCH/DELETE return 405).
- Table `orders`: id, origin_hub_id, destination_address (non-blank), destination_longitude/latitude (range CHECKs), package_weight_kg, status (CHECK), created_at and updated_at (timezone-aware; python default plus server default; `updated_at` refreshed on update).
- Seed `python -m app.orders.seed`: insert-only, matched by id, validates Hubs first and fails clearly without writing if they are missing. Destinations are illustrative simulation data.

### Verification

| Check | Result |
|---|---|
| `ruff check`, `ruff format --check`, strict `mypy app tests` | Passed |
| `pytest` | Passed: 91 tests (58 before this feature) |
| PostgreSQL 17.11 smoke test on the existing `skyfleet-db` volume (in-process, volume not reset, port 5432 untouched) | Passed: migration 0003 applied, 4 Hubs and 12 drones intact, seed inserted 10 then 0, list 200 with 10 orders, `ORD-006` 200, `ORD-999` 404, Hubs and drones still served, a 3.5 kg insert rejected by the CHECK, timestamps returned with a UTC suffix |
| `qa-tester` | Pass with gaps; no critical, high or medium findings |
| `code-reviewer` | One Medium finding (`migrations/env.py` did not register the orders model): fixed. Low findings below |

### Known limitations and follow-ups

- Weight is a `Float`, not a decimal (repo convention).
- No automated test runs against PostgreSQL; the smoke test was a one-off.
- Not tested: NULL in required columns, exactly +-180/+-90 as accepted values, the seed's command-line error path. The read-only test checks routing only and must change when a write endpoint is added.
- Two simultaneous seed runs could raise a raw database error (no corruption).
- Orders added by a later seed run list after existing ones, because they get a later `created_at`.
- No Partner, no delivery instructions, no assignment, no status transitions, no distance or feasibility check (Features 008 to 010 cover the frontend, assignment and execution).

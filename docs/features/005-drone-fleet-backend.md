# Feature 005 — Drone Fleet Backend

**Project:** SkyFleet  
**Status:** Complete — approved by the project owner  
**Implementation:** Complete. Not committed.  
**Verification:** 58 backend tests, `ruff check`, `ruff format --check` and strict `mypy` pass (rerun at finalization). Real PostgreSQL 17 (Docker, host port 55432): the existing dev database was upgraded from `0001` to `0002` with its 4 Hubs and volume preserved; the drone seed run twice gave 12 inserted, then 0; both endpoints returned correct data (12 drones, `DRN-001` detail, 404 for `DRN-999`, Hubs still 200 with 4). In a throwaway database in the same container (dropped afterwards), CHECK constraints (battery, status, longitude, model payload, max speed below cruise), foreign keys and RESTRICT deletes were rejected, and downgrades to `0001` and to base plus a re-upgrade worked. The frontend is untouched (no diff). `qa-tester` and `code-reviewer` were both run: no Critical or High findings; the one Medium (no test of the migration's own CHECK constraints) was fixed with a migration test.  
**Phase:** Drone Fleet — Backend Foundation  
**Dependencies:** Feature 003 (Hubs Backend API), Feature 004 (Hubs API Frontend Integration)

## 1. Objective

Introduce the first persistent drone fleet in SkyFleet. Store one technical drone model and individual drone units in PostgreSQL, associate each unit with a Hub, and expose read-only endpoints for future frontend map integration and flight simulation.

This feature establishes data structures only. It does **not** implement flight movement, dispatching, charging automation, delivery assignment, or autonomous decisions.

## 2. Business context and decisions

- MVP supports **exactly one seeded drone model**: **SkyFleet SF-1 Courier**.
- The SF-1 Courier is a plausible near-future (circa 2030–2035) urban delivery multicopter. Its specifications are **simulation assumptions**, not certified real-world performance guarantees.
- A `DroneModel` describes shared technical capabilities; a `Drone` represents one physical unit with its own identity and operational state.
- Each drone has one assigned/home Hub. Reuse the existing `Hub` model and identifiers; do not introduce a separate DroneBase entity.
- Hub `drone_capacity` is 50. Seeded assignments must not exceed capacity.
- Later features may add new models without changing the `Drone` data model or duplicating model specifications on every drone.
- Backend remains the source of truth. No mock-only runtime data or new frontend functionality in this feature.

## 3. SF-1 Courier specification

| Property | Value | Interpretation |
|---|---|---|
| Model code | `SF-1` | Stable model identifier |
| Display name | `SkyFleet SF-1 Courier` | Human-readable name |
| Airframe | Electric hexacopter (6 rotors) | Descriptive metadata |
| Maximum payload | **3.0 kg** | Maximum parcel mass |
| Maximum total flight distance | **20 km** | Nominal upper bound on one charge, not a delivery radius |
| Conservative mission distance budget | **12–14 km** | Total route including travel to recipient and return to a suitable Hub |
| Cruise speed | **45 km/h** | Nominal cruise speed |
| Maximum speed | **60 km/h** | Upper speed limit |
| Nominal flight time | **30–35 minutes** | Approximate range in favorable conditions |
| Minimum battery reserve | **20%** | Operational planning reserve |
| Charging time | **~45 min to 80%** | Approximate planning assumption |
| Simulated operating altitude | **40–100 m AGL** | Not an authorization to fly in real airspace |
| Maximum tolerated wind | **10 m/s** | Planning assumption |
| Mass including battery, without payload | **~9 kg** | Approximate |

**Consistency rule:** The 20 km maximum and the 12–14 km conservative budget refer to **total mission distance**, not one-way delivery distance. Actual mission feasibility will be computed in a later feature; do not introduce a simplistic distance-only dispatch engine now.

## 4. Scope

### In scope

1. SQLAlchemy model and Alembic migration for `DroneModel` and `Drone`, following existing backend conventions.
2. Foreign-key relationship from each `Drone` to its technical model and assigned Hub.
3. Clearly defined initial operational status and battery percentage per drone.
4. Seed one SF-1 technical model and a small, deterministic example fleet distributed across the four existing Hubs.
5. Read-only API: `GET /api/drones` and `GET /api/drones/{id}`.
6. Pydantic response schemas with the data required by a later frontend feature: unit identity, status, battery, position, assigned Hub, and model identity/capabilities.
7. Validation, tests, real PostgreSQL smoke checks, QA and code-review subagents.
8. Documentation of run/seed commands and limitations.

### Out of scope

- Frontend drone markers, panels, or map changes (next feature).
- Movement, trajectories, simulation worker, mission assignment, routing, deliveries, AI agent, telemetry streams, real-time sockets, or external drone integrations.
- Write endpoints / CRUD for drones or models.
- Automatic charging, battery depletion, maintenance scheduling, or status transitions.
- Additional drone models or model-selection logic.
- Changes to Hub API contracts unless an essential compatibility issue is discovered and explicitly approved.
- New dependencies without justification and approval.

## 5. Proposed domain design

### `DroneModel` (technical model)

Store a stable ID/code and name, plus technical parameters needed by future planning and UI. Suggested canonical fields:

- `id` (stable string code, e.g. `SF-1`)
- `name`
- `airframe_type` (e.g. `hexacopter`)
- `max_payload_kg` (3.0)
- `max_range_km` (20.0)
- `recommended_mission_range_km` (choose one conservative documented value in the 12–14 km range, e.g. 14.0)
- `cruise_speed_kmh` (45.0)
- `max_speed_kmh` (60.0)
- `nominal_flight_time_min` (choose a documented nominal value within 30–35, e.g. 32)
- `min_battery_reserve_pct` (20)
- `charge_to_80_minutes` (45)
- `max_wind_mps` (10.0)
- `empty_weight_kg` (9.0)

The 40–100 m operating altitude may be documented as a simulation assumption instead of stored until a future feature needs it. Avoid speculative or redundant columns. Use the project's existing conventions for decimals/floats and constraints; explain choices in the plan.

### `Drone` (individual unit)

Suggested fields:

- `id` (stable identifier such as `DRN-001`)
- `model_id` (foreign key to `DroneModel`)
- `hub_id` (foreign key to `Hub`, representing assigned/home Hub)
- `status` (validated operational state)
- `battery_pct` (integer 0–100)
- `longitude` and `latitude` (finite, geographically valid coordinates)

Suggested status vocabulary for future use: `IDLE`, `IN_FLIGHT`, `CHARGING`, `MAINTENANCE`. Seed all units in a sensible stationary state, e.g. `IDLE`; no automatic transitions in Feature 005. Avoid inventing a live operational status beyond the seeded simulation state.

Position is a snapshot, initially at the assigned Hub coordinates. Later, a simulation feature can update it independently of the home Hub.

### Integrity and conventions

- Enforce valid numeric ranges and foreign keys in the database where practical.
- Use Pydantic validation and existing error-handling conventions.
- Keep list responses deterministic (e.g. sorted by ID).
- Return `404` for unknown drone IDs.
- No duplication of model technical parameters on the `Drone` row.
- Clarify in the implementation plan how Hub capacity is checked for seeding; do not overbuild concurrency-safe fleet allocation logic in this feature.

## 6. Seed data

- Seed exactly one `DroneModel`: `SF-1`.
- Seed a **small deterministic fleet** (suggestion: 12 drones, three per existing Hub; final count to be confirmed in the implementation plan).
- Stable unit IDs and Hub assignments.
- All units start at their Hub coordinates with documented initial battery values and status `IDLE`.
- Seed is **idempotent**: re-running it inserts only missing records and does not overwrite existing operational values.
- Seed assumes the four Hubs from Feature 003 exist; if they are missing, fail clearly rather than silently creating a conflicting Hub dataset.
- Preserve the existing Hub seed and avoid modifying it unless necessary.

## 7. API contract

### `GET /api/drones`

- Returns all drone units in a stable order.
- Each record includes drone ID, model ID/name (or a consistent nested model summary), assigned Hub ID, status, battery percentage, longitude, and latitude.
- Expose technical capabilities either as a nested model object or through an additional model read endpoint **only if justified during planning**. Avoid adding endpoints unnecessarily.
- Return `[]` when there are no drones.

### `GET /api/drones/{id}`

- Returns the same unit representation for one drone.
- Returns `404` for an unknown ID.

Use the existing `/api` routing conventions and existing database session/dependency patterns. Document the final JSON shape before implementation.

## 8. Acceptance criteria

- [x] Migration creates both tables with appropriate foreign keys and constraints.
- [x] One SF-1 model exists with **3.0 kg** payload and the approved specifications.
- [x] A deterministic fleet is seeded across the four existing Hubs without exceeding their capacities.
- [x] Re-running the seed creates no duplicates and does not reset existing drone state.
- [x] Every seeded drone references an existing Hub and the SF-1 model.
- [x] Drone coordinates initially match the corresponding Hub coordinates.
- [x] `GET /api/drones` returns the complete fleet and `GET /api/drones/{id}` returns a single unit.
- [x] Unknown drone ID returns `404`; empty collection returns `[]`.
- [x] Invalid battery, coordinate, payload/range/speed, and broken foreign-key data are rejected where applicable.
- [x] Existing Hub endpoints and frontend remain unaffected.
- [x] Backend lint, format check, strict mypy, and tests pass.
- [x] Real PostgreSQL 17 smoke test verifies migration, seed twice, both API endpoints, and relevant constraints.
- [x] `qa-tester` and `code-reviewer` subagents are invoked; findings are reported.
- [x] No commit or push without explicit user approval.

## 9. Verification guidance

- Unit/integration tests for model schemas, valid/invalid field ranges, list ordering, 404, and idempotent seeding.
- Regression tests for existing Hubs endpoints.
- PostgreSQL smoke: `docker compose up -d db`, apply Alembic migrations, seed Hubs if needed, seed fleet twice, inspect API responses and database constraints.
- Respect the project's database port mapping: **host 55432 → container 5432**. Do not touch the unrelated Windows PostgreSQL service on port 5432.
- Avoid reading protected `.env` / `.env.local` files; use documented `.env.example` templates and existing configured processes.
- Report any checks not run or not verified honestly.

## 10. Workflow instructions

1. Place this spec in `docs/features/feature-005-drone-fleet-backend.md`.
2. In a new Claude Code session, run `/feature-start 005`.
3. `feature-start` must read relevant project context, invoke `task-planning`, present its plan and **stop before implementation**.
4. After user approval, invoke `/task-implementation`.
5. Run QA and code-review subagents; obtain user acceptance.
6. Run `/feature-finalization` for documentation and Git status/diff only. Commit/push require separate explicit approval.

## 11. Known limitations and future work

- Model specifications are illustrative assumptions, not aviation certification or real-world flight safety guarantees.
- No live telemetry or movement exists yet; positions and statuses are seeded snapshots.
- No automated operational logic uses range, battery, payload, wind, or Hub capacity yet.
- Next logical feature: **Feature 006 — Drone Fleet Frontend Integration**.

## 12. Implementation notes (as built)

- **Structure:** flat `backend/app/drones/` package (`models`, `schemas`, `repository`, `seed`), route in `backend/app/api/routes/drones.py`, Alembic migration `0002` (`drone_models`, `drones`). `drones` depends on `hubs`, never the reverse.
- **`drone_models`:** string code id (`SF-1`) plus the specification columns suggested in §5. Seeded values: 3.0 kg payload, 20.0 km maximum range, 14.0 km recommended mission range, 45.0 / 60.0 km/h cruise / maximum speed, 32 min nominal flight time, 20% reserve, 45 min charge to 80%, 10.0 m/s wind, 9.0 kg empty weight, airframe `hexacopter`. Floats are used for measurements, matching the Hub model. The operating altitude is documented in the README and not stored. CHECK constraints: positive values, recommended range at most the maximum range, maximum speed at least cruise speed, reserve between 0 and 100.
- **`drones`:** string id (`DRN-001` style), `model_id` and `hub_id` foreign keys (RESTRICT), `status` as a string with a CHECK (`IDLE`, `IN_FLIGHT`, `CHARGING`, `MAINTENANCE`; a Python `StrEnum` types the API), `battery_pct` 0–100, and `longitude`/`latitude` with range checks. Model parameters are not duplicated on drone rows.
- **Seed (`uv run python -m app.drones.seed`):** insert-only and idempotent. 12 drones, 3 per Hub in Hub-id order (`DRN-001`..`DRN-012`), battery 100 / 90 / 80 per Hub, all `IDLE`, positions copied from the Hub rows in the database. It validates before writing: it fails clearly if the Hubs are missing and fails if a Hub's assigned-drone count would exceed its `drone_capacity`, leaving the database unchanged.
- **API:** `GET /api/drones` (ordered by id, `[]` when empty) and `GET /api/drones/{id}` (404 `{"detail": "Drone '<id>' not found"}`). A drone is `{id, hub_id, status, battery_pct, longitude, latitude, model}` with the full model object nested, so no separate model endpoint was added.
- **Tests:** shared fixtures moved to `backend/tests/conftest.py` (the Hub-only `tests/hubs/conftest.py` was removed) with SQLite foreign keys enabled. A migration test runs `alembic upgrade head` and checks the CHECK constraints and foreign keys of the migrated schema, because `compare_metadata` ignores CHECK constraints.

## 13. Decisions confirmed during planning

- Hub capacity means the number of drones **assigned** to a Hub, regardless of flight status. It is enforced during seeding only. This was an MVP simplification at the time. **Superseded for runtime occupancy by Feature 009:** Q8 is answered, and a Hub's occupancy is the number of drones physically docked there (`business-rules.md` §2). The seed-time check remains valid because every seeded drone starts docked at its assigned Hub.
- SF-1 payload capacity stays at 3.0 kg.
- Existing PostgreSQL data was preserved; the Docker volume was not reset.

## 14. Known limitations (as built)

- No runtime capacity enforcement exists; only the seed checks it.
- The model seed is insert-only, so changing SF-1 values later needs a migration.
- The fleet plan follows the sorted seeded Hub ids, so it is append-only: extend it with a new plan instead of reordering.
- Automated tests run on SQLite; PostgreSQL behavior was verified manually. NaN coordinates and over-long strings were not tested.
- A status value outside the vocabulary would cause a 500 on read; the CHECK constraint prevents it today.
- The README has no example JSON response; the shape is defined in the schemas and the API test.

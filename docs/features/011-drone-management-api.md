# Feature 011 — Drone Management API

**Status:** Implemented (backend only) and verified on SQLite; PostgreSQL row-lock behavior not verified. Not committed.

## Implementation notes (verified)
- Endpoints: `POST /api/drones` (201), `PATCH /api/drones/{id}`, `DELETE /api/drones/{id}` (204); the existing GET endpoints are unchanged. Code: `backend/app/drones/{schemas,service,repository}.py`, `backend/app/api/routes/drones.py`; tests: `backend/tests/drones/test_drones_management.py`. No migration, seed or data change.
- Create accepts `id` (`DRN-` + digits), `hub_id`, optional `battery_pct` (default 100). The drone is created `IDLE` at the Hub position with the SF-1 model.
- Update accepts only `status` (`IDLE` or `MAINTENANCE`), `hub_id`, `battery_pct`; any other field is a 422. Reassignment needs an `IDLE` docked drone and moves its position to the new Hub. Setting a drone to `IDLE` re-checks Hub capacity and requires the drone to be at a Hub.
- Delete is refused (409) for drones that are in flight, charging, or have any mission (active or history).
- Errors use `{code, message}` (`DRONE_NOT_FOUND`, `HUB_NOT_FOUND`, `DRONE_ALREADY_EXISTS`, `HUB_FULL`, `DRONE_BUSY`, `INVALID_CHANGE`, `DRONE_HAS_HISTORY`); the older GET 404 keeps its plain string `detail`.

## Verification
- Passed: full backend suite 307 passed (13 PostgreSQL-marked tests deselected by default), `ruff` and `mypy` clean; QA review: all 8 acceptance criteria supported, no critical or high findings; code review: two medium findings fixed (Hub lock on the maintenance→`IDLE` path; battery-only edit on an off-Hub drone).
- Not verified: `pytest -m postgres` ran but all 13 tests were skipped (PostgreSQL on port 55432 not reachable), so the `FOR UPDATE` locking and race handling are untested. No manual Swagger run recorded.
- Known limitations: explicit `null` or empty PATCH bodies are treated as no change; no concurrency test.

## Goal
Provide a minimal, safe backend CRUD API for administrative management of SkyFleet drones. This feature is backend-only. Existing mission planning, flight simulation, and data must remain intact.

## Context
- Backend: FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL.
- Existing read endpoints: `GET /api/drones` and `GET /api/drones/{drone_id}`.
- Drones belong to Hubs; each Hub has capacity 50.
- Existing drone states include `IDLE`, `IN_FLIGHT`, `MAINTENANCE`.
- Mission history must remain consistent.
- Feature 010 (Flight Simulation) may still have unfinalized work. Do not finalize it implicitly.

## In scope

### Create
- `POST /api/drones` (or conform to the repository's established API conventions).
- Accept only safe administrator-controlled fields supported by the existing data model (at minimum an ID and existing Hub ID; battery and other optional values only where appropriate).
- Validate unique drone ID, valid Hub, supported field ranges, and Hub capacity.
- Use the existing drone model and defaults; do not invent a new drone type or charging model.

### Read
- Preserve existing `GET /api/drones` and `GET /api/drones/{drone_id}` behavior.
- Ensure newly created/updated drones are visible through these endpoints.

### Update
- `PATCH /api/drones/{drone_id}` (or established equivalent).
- Allow only explicitly whitelisted administrative fields supported by the existing model.
- Support moving an idle drone to `MAINTENANCE` and returning it to `IDLE` when valid.
- Allow reassignment to an existing Hub only if the drone is safely docked/idle and target Hub has capacity.
- Do not allow arbitrary position, flight progress, or active-mission manipulation via CRUD.

### Delete
- `DELETE /api/drones/{drone_id}`.
- Permit physical deletion only when there are no dependent missions/history and the drone is not in flight or otherwise active.
- Otherwise return a clear conflict response; never cascade-delete missions or orders.
- Existing `MAINTENANCE` status serves as the non-destructive option for taking a drone out of service. Do not introduce `RETIRED` in this feature.

## Business rules and safety
- Reject any mutation that would conflict with an active/assigned mission.
- Keep Hub occupancy/capacity correct and consistent with the existing occupancy model.
- Reuse existing validation and service patterns; no parallel business rules.
- Validate invalid Hub, duplicate ID, invalid battery, invalid state transition, active mission, and deletion with history.
- Avoid race conditions where practical using existing transaction patterns; do not undertake a broad concurrency redesign.
- Preserve all existing seeded data and existing missions.

## Out of scope
- Frontend forms or management screens.
- Orders CRUD.
- Automatic Dispatch.
- Charging, rebalancing, airspace logic, incident simulation, AI.
- Authentication/authorization redesign.
- General refactoring or schema changes unless strictly necessary and explicitly approved.

## Acceptance criteria
1. Admin can create a valid drone in an existing Hub through Swagger and retrieve it.
2. Invalid Hub, duplicate ID, invalid values, and full Hub are rejected with useful errors.
3. Admin can update safe fields and set an eligible idle drone to/from `MAINTENANCE`.
4. Active/assigned drones cannot be edited or deleted in ways that break a mission.
5. Drone with mission history cannot be physically deleted; history remains intact.
6. Drone with no dependencies can be deleted and no longer appears in the list.
7. Existing read APIs, mission planner, and flight simulation continue to pass targeted regression tests.
8. No existing development data is reset or overwritten.

## Workflow
1. Inspect repository feature numbering, skills/agents, and Feature 010 status.
2. If `011` is available, register this specification in the repository's established feature-spec format/location, preserving its meaning.
3. Run the repository's established `/feature-start 011` workflow, allowing its planning agents/skills to produce an implementation plan.
4. STOP for user approval before code changes.
5. After approval, implement backend only, run focused tests, provide a concise checkpoint and manual Swagger test instructions.
6. Do not finalize, commit, push, or reset anything without explicit instruction.

## Token discipline
- Inspect only relevant files first; avoid dumping the whole repository.
- Prefer existing patterns and targeted tests.
- Report blockers/questions concisely; do not expand scope without approval.

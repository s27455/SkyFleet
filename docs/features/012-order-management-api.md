# Feature 012 — Order Management API

**Status:** Implemented (backend only) and verified on SQLite; independent QA and code review not run; PostgreSQL locking not verified. Not committed.

## Implementation notes (verified)
- Endpoints: `POST /api/orders` (201), `PATCH /api/orders/{id}`, `DELETE /api/orders/{id}` (204); the existing GET endpoints are unchanged. Code: `backend/app/orders/{schemas,service,repository}.py`, `backend/app/api/routes/orders.py`; tests: `backend/tests/orders/test_orders_management.py`. No migration, seed or data change.
- Create accepts `origin_hub_id`, `destination_address` (trimmed, non-empty), destination coordinates and `package_weight_kg` (greater than 0, at most 3.0, the existing limit). The backend generates the id (`ORD-` plus 8 hex characters) and sets `READY_FOR_PICKUP`; any other field (status, id) is a 422. Creating an order never creates a mission.
- Update accepts only the five fields above, requires at least one, rejects nulls. Update and delete are allowed only for a `READY_FOR_PICKUP` order that no mission (any status) references; otherwise 409 `ORDER_HAS_MISSIONS` or `ORDER_NOT_EDITABLE`. Delete never cascades.
- Errors use `{code, message}` (`ORDER_NOT_FOUND`, `HUB_NOT_FOUND`, `ORDER_HAS_MISSIONS`, `ORDER_NOT_EDITABLE`); the older GET 404 keeps its plain string `detail`.
- Decision: delete is restricted to `READY_FOR_PICKUP` orders (approved assumption). The obsolete test `test_orders_api_is_read_only` was removed because this feature intentionally adds those methods.

## Verification
- Passed: full backend suite 325 passed (13 PostgreSQL-marked tests deselected by default), `ruff` and `mypy` clean.
- Not run: independent QA and code-review agents; PostgreSQL tests (port 55432 was not reachable), so the row locking (`FOR UPDATE`) is untested; manual Swagger run.
- Known limitation: one new test compares a fresh read without `updated_at` because SQLite returns naive timestamps; not checked on PostgreSQL.

## Goal
Provide a minimal, safe backend CRUD API for administrative management of SkyFleet orders. Enable creating realistic delivery scenarios directly through Swagger and later through the Management UI, without manually editing PostgreSQL. This feature is backend-only.

## Context
- Backend: FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL.
- Existing read endpoints: `GET /api/orders`, `GET /api/orders/{order_id}`.
- Existing mission planner and mission lifecycle use order origin Hub, customer coordinates, package weight and status.
- Known order statuses include `READY_FOR_PICKUP`, `OUT_FOR_DELIVERY`, `DELIVERED`.
- Existing mission history and flight simulation must remain consistent.
- Feature 011 (Drone Management API) may be in progress. Do not implicitly finalize or overwrite any feature.

## In scope

### Create
- Add `POST /api/orders`, following existing repository routing, schemas, and service conventions.
- Accept a valid existing `origin_hub_id`, a customer destination address, longitude, latitude, and package weight in kilograms.
- Let the backend assign the initial `READY_FOR_PICKUP` status; never allow a client to create an order already delivered or in flight.
- Follow the repository's existing ID-generation convention (including user-provided IDs only if that is the established pattern); ensure uniqueness.
- Validate nonempty address, valid coordinate ranges, positive weight and the existing drone/payload business constraints where applicable. Avoid introducing a new global policy inconsistent with the mission planner.
- A destination is an independent customer point; it must not be silently snapped to a Hub. This allows testing origin Hub → customer → selected return Hub.

### Read
- Preserve existing `GET /api/orders` and `GET /api/orders/{order_id}` behavior and response compatibility.
- Newly created and updated orders must appear through existing read endpoints.

### Update
- Add `PATCH /api/orders/{order_id}` (or established equivalent) for explicitly whitelisted customer/order fields: origin Hub, destination address, destination coordinates and package weight, only when safe.
- Allow edits only when the order is `READY_FOR_PICKUP` **and has no associated mission**, including `ASSIGNED`, `IN_FLIGHT`, completed or cancelled missions. This conservative rule avoids changing a saved mission plan or history; explain conflicts clearly.
- Do not expose status, mission ID, flight progress, timestamps or other lifecycle-managed fields for arbitrary updates.

### Delete / cancellation
- Add `DELETE /api/orders/{order_id}` for physical deletion only when the order has no associated mission or other dependent history and is not being processed.
- If any mission/history references the order, return a clear `409 Conflict` (or repository-standard conflict response), preserving all data. Never cascade-delete missions or flights.
- Do **not** add a new `CANCELLED` order status just for this feature. If order cancellation already exists in the data model, reuse it only when its semantics and mission-state rules are already defined. Otherwise document cancellation of linked orders as a future enhancement and keep the safe conflict response.

## Business rules and safety
- Reuse the existing order model, validation patterns, and mission service logic. No duplicate or competing planning algorithm.
- Reject unknown Hub, duplicate ID (where applicable), invalid destination/coordinates, invalid package weight, forbidden status updates, and mutations to orders with mission history.
- Use existing database transactions to prevent partially applied changes. Handle conflicts predictably; do not redesign the entire concurrency model.
- Preserve all seeded and previously created orders, drones, missions and flight records. No destructive migrations or database resets.
- Avoid silently changing mission eligibility or automatically starting missions when an order is created.

## Out of scope
- Frontend Management UI (planned Feature 013).
- Drone CRUD (Feature 011).
- Automatic Dispatch and automatic mission creation/start.
- New order lifecycle states, broad schema redesign, customer accounts, payments, authentication redesign.
- Charging, rebalancing, AI, incident simulation or airspace features.

## Acceptance criteria
1. Through Swagger, create a valid order with an existing origin Hub and a customer address/coordinates distinct from Hub coordinates.
2. Retrieve the created order through existing list and detail endpoints.
3. The order initially has `READY_FOR_PICKUP` status and can be evaluated by the existing `GET /api/missions/plan` flow with an eligible drone.
4. Edit a mission-free pending order and verify the changed destination, origin Hub or package weight is reflected in subsequent reads/planning.
5. Reject unknown Hub, invalid coordinates, empty address, invalid weight and duplicate ID (if IDs are client-provided) with useful errors.
6. Reject updates/deletions of an order associated with any mission; mission/flight history remains unchanged.
7. Physically delete a newly created, mission-free test order and verify it disappears from the API.
8. Existing mission planning, simulation and order read endpoints pass targeted regression tests.
9. No existing development data is reset, overwritten or automatically dispatched.

## Workflow
1. Read repository feature workflow instructions, relevant skills/agents, and current Git/feature state briefly.
2. Verify that feature number `012` is free; if occupied, report the conflict and stop rather than overwriting it.
3. Register/adapt this specification in the established feature location and format without expanding its scope.
4. Run the established `/feature-start 012` workflow to produce a plan using the repository's designated skills/agents.
5. STOP and wait for user approval before implementing code.
6. After approval, implement backend only, run focused tests, and provide a concise checkpoint plus manual Swagger verification steps.
7. Do not finalize, commit, push, modify existing data or reset the database without explicit instruction.

## Token discipline
- Inspect relevant order, mission and API files only; avoid full repository dumps and unnecessary research.
- Reuse existing architecture, schemas, validation and tests.
- Keep planning/reporting concise and do not redesign other features.

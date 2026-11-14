# Feature 019A — Manual Drone Relocation

**Status:** Implemented and verified by automated checks; Live QA approved by the owner; not yet committed. PostgreSQL concurrency tests written but not run; no QA or code-review agent run. Decisions: `docs/decisions/0009-manual-drone-relocation.md`  
**Project:** SkyFleet  
**Scope:** MVP, manual relocation only  
**Suggested path:** `docs/features/019a-manual-drone-relocation.md`

## 1. Goal

Allow an operator to select an available drone and instruct it to relocate from its current hub to another hub. Relocation is a real, empty flight: it takes time, changes position, consumes battery and is visible in the simulator. The drone's home/current hub association changes **only after landing** at the destination. This feature establishes one reusable relocation execution mechanism for future **019B — Automatic Fleet Rebalancing**; it does **not** implement automatic decisions.

## 2. Operator workflow

1. Open Fleet/Drone Management and select a drone.
2. Choose **Relocate** and select a different destination hub.
3. See the origin, destination and a clear feasibility/availability result; confirm the action.
4. The simulator starts an empty relocation flight and shows the drone as **Relocating to [hub]** on the map, drone details and relevant flight views.
5. The drone travels normally and uses the existing battery model.
6. On successful landing it docks at the destination hub, updates `drone.hub_id`, and returns to the normal availability/charging rules. The operator can see the completed relocation in history.

If a request cannot be accepted, explain why without changing the drone, mission or database state.

## 3. Business rules

### 3.1 Eligibility and validation

- Only a drone that is **IDLE**, physically at its current hub and not assigned to an active mission may be manually relocated.
- The destination must be an existing hub different from the current hub.
- Reuse existing reachability, battery reserve and dispatch constraints for an **empty** flight. Do not create a new battery model or bypass existing safeguards.
- A charging or maintenance drone cannot be relocated until it becomes eligible through existing rules.
- Validation and creation must be atomic: concurrent dispatch or another relocation cannot assign the same drone twice. Rejected/duplicate requests must not create phantom flights or events.
- The operator may choose a particular drone even when there is local demand at its source hub; show an informative warning if appropriate, but do not silently override a valid manual command. Automatic protection of source-hub capacity belongs to 019B.

### 3.2 Relocation flight lifecycle

- A relocation is a **mission/flight without an order or parcel**. It must not create a fake order, alter order statuses, or emit delivery events.
- Prefer extending the existing mission/flight engine with an explicit mission purpose/type (or equivalent existing representation). Claude should audit schema assumptions about non-null order references and propose the smallest safe change.
- The drone follows a real timed route from hub to hub, with continuous position and empty-flight battery drain; no teleportation or instantaneous hub reassignment.
- While in transit it is unavailable to delivery dispatch and to other relocation commands.
- On landing, complete the relocation mission and update the drone's hub, then apply normal IDLE/charging behavior according to the existing engine.
- Store sufficient durable state to survive API/worker restarts without duplicate launches or repeated landing effects.
- Record the operator-initiated relocation and its outcome using existing operational event/history conventions where practical. Avoid unrelated event-system redesign.

### 3.3 Compatibility with existing features

- **018C — Drone Failure:** a relocating drone is an eligible flying drone for the existing failure/emergency behavior where compatible. A failure ends the relocation without assigning the destination hub; the drone follows existing emergency/maintenance rules.
- **018E — LPR:** an active relocation must obey the same corridor/hold rules as other flights, including battery cost and resume behavior.
- **018B — Cancellation:** relocation has no order to cancel; order cancellation must not target it.
- **018D — Failed Delivery:** relocation carries no parcel and has no delivery milestone.
- **Dispatch/charging:** no duplicate assignment; destination hub becomes available for subsequent dispatch only after successful landing and according to the existing charging rules.
- Existing delivery flights, order details, event queries and history must continue to work when a mission has no associated order.

## 4. Backend/API

Provide one authenticated/authorized-in-the-existing-project-sense operator action using current API conventions, for example `POST /api/drones/{drone_id}/relocate` with `destination_hub_id`. The exact route and payload should follow the repository's patterns.

- Success returns the created relocation mission/flight and destination information suitable for immediate UI feedback.
- Invalid drone, hub, same-hub destination, ineligible drone, insufficient battery and assignment races return clear, consistent errors (use established response conventions).
- Reuse the worker and flight engine; do not create a second movement loop.
- Add only the minimal persistence/migration required by existing schema constraints. Do not assume a migration number until Initialize audits the current Alembic head.
- Keep a shared relocation execution service suitable for invocation by the future 019B scheduler, without implementing that scheduler now.

## 5. Frontend/UI

- Add **Relocate** to an appropriate drone-management/details surface, not as a hidden simulation-only shortcut.
- Show available destination hubs, confirmation, pending/success/error feedback and disabled state for ineligible drones.
- Clearly distinguish relocation flights from delivery, recall, failed delivery and emergency flights. Suggested visible label: **Relocating to [hub]**.
- Show the active flight and target hub in drone/flight details, and the completed action in existing history/activity where possible.
- Prefer existing map markers, paths, panels and design tokens. Do not introduce a new dashboard or a broad UI redesign.

## 6. Explicitly out of scope

- **019B** automatic rebalancing, demand forecasting, source-hub reserves, cooldowns, recurring scheduling and automatic relocation decisions.
- Relocating a drone that is already flying, cancelling or redirecting an active relocation through a new UI, or multi-stop relocation routes.
- AI optimization, pathfinding, new airspace planning, parcel inventory or logistics analytics.
- Reworking existing incidents, changing technical DELETE behavior or creating fake orders for relocation.

## 7. Acceptance criteria / Live QA

1. Operator selects an eligible IDLE drone and a different hub, confirms, and a relocation flight starts.
2. The map and drone/flight panels identify the flight as a relocation, with the correct destination.
3. The drone moves continuously and consumes battery using the empty-flight rate; its hub stays unchanged until landing.
4. After landing, the drone is associated with the destination hub and returns to normal IDLE/charging/dispatch behavior.
5. Ineligible or duplicate relocation attempts are rejected clearly and create no duplicate flight.
6. A relocation survives API/worker restart without teleporting or repeating its start/completion.
7. Existing delivery/incident behavior remains intact; specifically, test LPR hold and drone failure on a relocating drone.
8. Relocation appears in relevant history/activity without a fabricated customer order.

## 8. Verification expectations

- Backend tests: eligibility, same-hub and battery rejection, mission/flight creation, empty-flight consumption, landing and hub reassignment, restart/idempotency and compatibility with order-less missions.
- PostgreSQL concurrency tests: relocation versus relocation and relocation versus dispatch; relevant failure and LPR overlap tests.
- Frontend tests: availability, hub selection, confirmation, feedback, active label and history.
- Standard project gates: backend tests, PostgreSQL tests on a temporary database, Ruff/format/mypy, frontend lint/typecheck/format/tests/build.
- Migration upgrade/downgrade tested on temporary databases if required. **Do not apply a migration to the development database without separate approval.**

## 9. Initialize audit / decisions for approval

Claude Code should inspect the repository before proposing implementation, especially:

- Whether missions and flights can exist without an order, and all API/serialization/history/event assumptions that require an order ID.
- Whether existing flight legs can represent hub-to-hub empty travel without a delivery stop, and any index-based assumptions remaining after 018E.
- How the engine distinguishes mission completion, emergency termination, charging and hub reassignment.
- How dispatch locking and the 018E LPR hold interact with relocation creation and progression.
- The smallest explicit mission-type representation and API/UI changes.

Propose the minimal plan and only genuine approval decisions. **Initialize is audit/planning only**: no implementation, migration application, simulation data changes, process restarts or commits. Proceed to implementation only after plan approval.

# Feature 010 — Flight Simulation

**Project:** SkyFleet  
**Status:** Specification consolidated; implementation plan requires approval  
**Dependency:** Completed Feature 009 — Mission Planning & Assignment  
**Document policy:** This is the single source of truth for Feature 010. It supersedes earlier `feature-010-decisions.md` and `feature-010-plan-decisions.md` drafts.

## 1. Goal and product direction

Simulate execution of an already assigned drone delivery mission: takeoff from the origin Hub, flight with the parcel, successful delivery, empty return flight, and landing at an available Hub. Visualize flights on the existing Mapbox interface, using backend-authoritative flight state.

Feature 010 is the foundation for the future **live autonomous SkyFleet operations map**. Its manual mission-start action is a temporary demonstration control. Feature 011 will automatically select and dispatch drones; Feature 012 will rebalance idle drones across Hubs. A later order-generation simulation will introduce new orders automatically; completed orders should leave the active view but remain available in history once that UI behavior is implemented.

## 2. Approved decisions

### 2.1 Implementation stages and checkpoints

Implement Feature 010 in **two stages**:
1. **Backend:** simulation engine, mission start, flight progress/read API, landing logic, data migration(s), tests, QA and code review. **Stop for a user checkpoint before frontend work.**
2. **Frontend:** Mapbox flight visualization, live progress/status display, minimal manual Start Mission control, frontend tests, QA and code review.

Neither stage may be finalized, committed, or pushed without explicit authorization. Do not begin implementation until the revised plan is approved.

### 2.2 Order lifecycle

Preserve the existing locker-to-Hub readiness flow:
- `CREATED`: order created;
- `AWAITING_HANDOVER`: parcel not yet confirmed at the origin Hub;
- `READY_FOR_PICKUP`: parcel physically ready at the origin Hub and eligible for assignment.

Add:
- `OUT_FOR_DELIVERY` at mission takeoff;
- `DELIVERED` when the parcel reaches the delivery destination successfully.

**Parcel delivery and mission completion are separate events.** The order becomes `DELIVERED` before the drone returns and the mission is `COMPLETED`. Update backend validation and the frontend's strict order-status adapter/whitelist as part of the relevant stage. Preserve historical delivered orders; do not delete them.

### 2.3 Mission and flight lifecycle

Preserve mission statuses `ASSIGNED`, `IN_FLIGHT`, and `CANCELLED`; add `COMPLETED`.

- Only `ASSIGNED` missions can start.
- At takeoff, mission and drone transition to `IN_FLIGHT`, and the order to `OUT_FOR_DELIVERY`.
- Flight-specific phases/progress belong to a **flight record**, rather than overloading mission status. Claude should propose the exact phase names and schema.
- At successful parcel delivery, the order becomes `DELIVERED`; the mission remains `IN_FLIGHT` during the return leg.
- After successful landing, the mission becomes `COMPLETED`, and the drone returns to an appropriate idle/available state, subject to its remaining battery.
- Feature 009 cancellation remains **pre-takeoff only**. Do not silently extend cancellation to an in-flight mission.
- Normal delivery always succeeds in Feature 010. Failed delivery and parcel-return workflows are deferred.

### 2.4 Simulation duration and transport

- A normal **complete** mission (outbound + delivery + return) takes approximately **30–90 seconds** in accelerated simulated time.
- Scale duration by planned route distance: shorter routes nearer 30 seconds, longer routes nearer 90 seconds.
- Document the **exact deterministic mapping**, phase timing, update cadence, and test strategy in the implementation plan.
- Acceleration is a simulation time-scale adjustment; do **not** change the SF-1 Courier's published cruise/max-speed specifications.
- The backend owns simulation time, flight phase, coordinates, drone status, mission state and battery. The frontend may visually interpolate between authoritative updates but must not execute the mission independently.
- Use **REST polling** for this feature. Keep the flight response suitable for future streaming, but defer WebSocket/broadcaster infrastructure.
- Explain persistence, restart recovery, polling reconnection and idempotency.

### 2.5 Energy and charging

Reuse the Feature 009 weight-aware model and approved parameters:
- Maximum parcel weight: **3 kg**.
- Nominal model range: **20 km**.
- Recommended mission distance budget: **14 km**.
- Default `payload_energy_factor = 0.5`.
- Empty rate = `100 / max_range_km` battery percentage points per km.
- Loaded rate = empty rate × `(1 + payload_energy_factor × parcel_weight / max_payload_kg)`.
- Normal flight uses the **loaded outbound leg** and **empty return leg**.
- Feature 009 planning also checks a conservative **fully loaded return** contingency and the **20% minimum battery reserve**.

Battery consumption must be consistent with traveled distance and flight phase. Normal mission planning must not intentionally violate the 20% reserve. Emergency situations are exceptional and must be represented explicitly.

**No automatic charging** in Feature 010. Remaining battery carries over between missions; subsequent eligibility must be checked using the actual battery. Document charging as future work.

### 2.6 Hub occupancy: physical presence only, NO reservations

These are definitive business rules, superseding any earlier reservation proposal:
- Each Hub has **50 physical drone places**.
- Occupancy counts **only drones physically present/docked at the Hub**.
- At takeoff, the drone immediately ceases to count at the origin Hub.
- In-flight drones occupy **no Hub**, even if their return destination is known.
- A drone counts at a destination Hub only after successful landing/docking.
- Assignment, confirmation, takeoff and flight create **no landing-place reservations**.
- Do not introduce reservation tables, counters, reserved-arrival occupancy or reservation-release logic.
- Administrative `hub_id` must not be treated as authoritative physical occupancy; clarify its meaning against existing models.
- In the MVP, physical docking is approximated from drone status and position, consistent with previous features. Future hardware would provide authoritative docking signals.

The **40/50** threshold is a future Feature 012 **rebalancing target**, not a hard landing limit. The future system will aim to maintain roughly 10 free places by relocating suitable idle drones; it is not a guarantee that a Hub can never become full. Temporary occupancy above 40 is allowed; occupancy above 50 is not.

### 2.7 Return Hub, full Hub and emergency behavior

- Feature 009 selects the nearest currently suitable return Hub, including the origin Hub if appropriate. **No landing slot is reserved.**
- Feature 010 must **recheck actual physical capacity before landing**.
- If the planned Hub is full, attempt a reachable alternative Hub, accounting for remaining battery and safety assumptions.
- Use **transactionally safe, per-Hub row locking at landing** so concurrent landings cannot push physical occupancy beyond 50. Do not add future-capacity reservation locks.
- **Do not implement indefinite airborne holding that drains battery to 0%, or treat flight at 0% as safe.**
- In the exceptional case where no safe Hub landing is possible, or battery becomes critical, represent a **minimal simulated emergency landing/exception outcome** and notify the operator.
- For MVP, an emergency may be modeled as an explicit terminated/exceptional simulation state and visible alert. **Do not claim to compute a real-world safe emergency landing site**, and do not silently mark the mission as successfully completed.
- Claude must propose the smallest coherent mission/flight/drone state and API changes for this emergency outcome, including how a parcel already marked `DELIVERED` remains delivered if the emergency occurs on return. **This precise state model still requires approval in the revised plan.**
- Preserve the 20% reserve for normal planning; do not use emergency behavior to justify unsafe planned missions.
- Full real-world incident management, realistic emergency-site selection and hardware control are out of scope.

### 2.8 Manual start is temporary

Add a **minimal operator-facing `Start Mission` control** for an already `ASSIGNED` mission in the existing map UI. This allows a demonstration without using Swagger.

- The control calls backend-authoritative start validation and execution.
- Do **not** build a large assignment/mission-management interface.
- It does not select a drone or assign an order; Feature 009 already handles assignment.
- Feature 011 will automatically choose, assign **and start** missions through the same backend service/API. Design for reuse; the manual control must not become a required step in autonomous operation.
- Claude should propose the smallest sensible placement and how an operator finds an assigned mission. **Exact UI placement is a plan decision, not yet fixed.**

## 3. Functional scope

### Backend

- Start an `ASSIGNED` mission exactly once, safely under concurrent requests.
- Create/store authoritative flight progress and phases.
- Simulate loaded outbound travel, successful delivery, empty return, and landing.
- Update drone coordinates, battery and statuses coherently.
- Record order `OUT_FOR_DELIVERY` and `DELIVERED`, and mission `IN_FLIGHT` and `COMPLETED` at the correct events.
- Expose flight read API(s) for REST polling.
- Recover correctly after backend restart or delayed polling.
- Recheck landing Hub capacity atomically and divert if a safe alternative is available.
- Represent an exceptional/emergency outcome explicitly, without indefinite battery-draining holding.
- Preserve Feature 009 assignment uniqueness, planning and preflight cancellation behavior.

### Frontend

- Animate in-flight drones smoothly on Mapbox using backend-provided position/progress.
- Display flight phase, mission status and battery.
- Provide minimal `Start Mission` for already assigned missions.
- Keep Hub physical drone counts consistent with takeoff and landing.
- Recognize `OUT_FOR_DELIVERY` and `DELIVERED` in order displays.
- Show an understandable exception/alert for simulated emergency outcomes.
- Handle refresh, API outages and reconnection without fabricating flight state.

## 4. Explicit non-goals

- Autonomous drone assignment/dispatch (**Feature 011**).
- Automatic fleet rebalancing at ~40/50 (**Feature 012**).
- Automated order generation (**later feature**, not yet numbered).
- Automatic battery charging (future feature).
- Failed parcel delivery, returned parcels, post-takeoff manual abort/pause, or full incident management unless separately approved.
- Real drone control, certified flight safety, airspace/weather integration, collision avoidance, physical docking hardware, parcel-locker integration.
- WebSockets/broadcaster implementation.
- Landing-capacity reservations.

## 5. Verification and acceptance criteria

- Only an assigned mission starts; duplicate/concurrent start attempts cannot create conflicting flights.
- Normal complete missions take ~30–90 seconds according to a documented deterministic mapping.
- Backend state is authoritative and survives refresh/reconnection and the proposed restart model.
- Loaded outbound and empty return have different energy use; weight and reserve rules remain consistent with Feature 009.
- Order transitions to `OUT_FOR_DELIVERY` at takeoff and `DELIVERED` at parcel handoff; mission completes **only after landing**.
- In-flight drones are not counted at Hubs; assignment and flight create **no reservations**.
- Return to origin Hub is allowed when suitable.
- Full planned Hub triggers safe alternative selection if possible.
- A full Hub is never overfilled, including by simultaneous arrivals.
- Critical battery/no safe landing path produces an explicit **simulated emergency/exception**, never an endless hold or fabricated successful landing.
- Mission cancellation remains restricted to pre-takeoff.
- Frontend Start Mission is a temporary, minimal action; future automatic dispatch can reuse the backend.
- Frontend recognizes new order statuses, renders live progress, and handles errors/reconnects.
- Automated tests, relevant PostgreSQL concurrency tests, QA and code review pass for both stages.

## 6. Required decisions in Claude's revised plan

Before implementation, inspect `CLAUDE.md`, existing context and specs, Feature 009 models/APIs/migrations/tests, frontend architecture and any relevant ADRs. Present:

1. Exact backend flight record, phase model, mission/order/drone status transitions, migration and API contracts.
2. Exact 30–90 second timing formula, simulation tick/poll cadence, persistence and restart/recovery.
3. Minimal deterministic emergency/exception state model and operator notification, without claiming real-world landing-site safety.
4. Alternative-Hub selection and **atomic** landing-capacity logic without reservations.
5. Minimal placement/discovery of the manual Start Mission control.
6. Compatibility changes needed for existing frontend status adapters and physical Hub occupancy.
7. Backend-first implementation/test/review checkpoint, followed by frontend stage only after approval.
8. Test coverage for state transitions, energy, timing, restart, no reservations, full-Hub diversion, emergencies and concurrent landings.

Flag genuine remaining conflicts or choices rather than silently inventing requirements.

## 7. Workflow and approval gates

1. **Now:** reread this consolidated specification, revise the Feature 010 implementation plan, and **stop for explicit approval**.
2. **After plan approval:** implement and verify **backend stage only**, then stop at a user checkpoint.
3. **After backend checkpoint approval:** implement and verify frontend stage, then stop for manual review.
4. Finalization, documentation updates, commit and push require separate explicit user authorization under the established SkyFleet workflow.

**Do not implement, finalize, commit or push merely because this specification was provided.**

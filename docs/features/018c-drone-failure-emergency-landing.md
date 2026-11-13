# Feature 018C — Drone Failure & Emergency Landing

**Status:** Implemented and verified (Live QA passed per the owner); not yet committed  
**Project:** SkyFleet MVP  
**Dependencies:** 018A (operational events), 018B (order cancellation and recall)

## Goal

Simulate a drone malfunction during an active flight, visibly interrupt its mission, guide it to a simulated nearby emergency landing point, and leave it grounded and unavailable for dispatch. Preserve an auditable incident history and avoid accidentally restoring a failed drone through order cancellation or other workflows.

## User-facing behavior

1. The **Drone failure** manual incident control in Management / Simulation Events becomes available when at least one eligible drone is actively flying. The control chooses one eligible flying drone, following the established incident-control convention. If none is eligible, show clear feedback; do not fabricate an incident.
2. When triggered, show immediate, conspicuous failure feedback on the map and in relevant drone, flight, mission and order details. The drone changes from its normal flight toward a simulated nearby emergency landing point; its position progresses continuously rather than teleporting.
3. During the emergency approach, clearly indicate that the drone is in an emergency state and no longer performing its original delivery or recall route.
4. On landing, the drone remains grounded, visibly marked as requiring service, and cannot be assigned new missions. Do not automatically reset it to IDLE, CHARGING or normal operation.
5. Show the emergency landing location on the map, with a clear red warning/marker. The UI must distinguish an active emergency approach from an already-grounded failed drone.
6. Preserve the affected order, mission and flight records and expose a durable incident event in the existing Activity timeline. No incident should be silently erased by subsequent polling or ordinary cancellation.
7. The manual trigger and any future automatic trigger must call the same backend incident behavior. Do **not** enable or implement random incidents in 018C unless the existing spec explicitly requires it; leave the general random-incidents switch disabled.

## Simulation and business rules

- **Eligible target:** a drone currently flying a normal mission or an active recall, where an emergency transition is technically valid. Exclude idle, charging, maintenance, already-failed or already-emergency drones. The Initialize audit must confirm exact eligibility against the current flight/mission state model.
- **Failure transition:** record the incident once, stop normal delivery/recall progression, and create an emergency landing trajectory starting at the drone's current simulated position and battery level. No teleportation, battery reset, or instant hub assignment.
- **Emergency landing point:** select a nearby *simulated* safe point using a deterministic, testable MVP rule compatible with the existing flight engine. This is not a real-world safety or terrain assessment. Avoid a GIS, obstacle-avoidance or airspace subsystem.
- **Battery:** retain continuous battery accounting. Do not reopen hypothetical no-reachable-hub design work from 018B; emergency landing is a separate 018C incident behavior.
- **After landing:** keep the drone unavailable for dispatch and explicitly requiring service. Reuse existing MAINTENANCE / EMERGENCY concepts where semantically appropriate; the Initialize audit should recommend the smallest consistent state representation. A full repair workflow is out of scope.
- **Order and mission:** an interrupted undelivered delivery must not become DELIVERED. Define the smallest consistent terminal/interrupted mission state and user-visible order outcome based on existing enums and rules. Preserve historical records; do not silently create a new delivery attempt. If a parcel was already delivered, the delivered order remains delivered even if the drone fails on the return leg.
- **Interaction with 018B:** cancelling an order must not heal a failed drone, override its emergency trajectory, or clear its service requirement. Preserve idempotency and transaction/concurrency safeguards.
- **Events:** use the 018A operational-events foundation, recording the failure once with target references, origin MANUAL, and relevant metadata. Do not create duplicate events on worker ticks or repeated requests.

## UI scope

- Enable the existing Drone failure incident icon when a valid target exists, with pending/success/error feedback.
- Show the failure and emergency landing state in the existing map and drone/flight/order detail views, with accessible labels and legend updates where appropriate.
- Keep the incident visible after landing so it is inspectable; propose a simple MVP visibility rule during Initialize rather than silently disappearing after the ordinary 120-second order-marker window.
- Reuse current polling, map markers, status components and Activity timeline. No new dashboard, route-polyline system, or full maintenance management UI.

## API and persistence

During Initialize, audit existing drone, mission, order, flight, event and simulation-worker models and propose:

- the smallest backend manual-trigger endpoint and eligible-target selection strategy;
- exact state transitions for failure before delivery, failure during recall, and failure after delivery while returning;
- restart-safe persistence of emergency trajectory, landing point and service requirement;
- transaction locks, idempotency and race handling versus worker ticks and order cancellation;
- any necessary migration, with a minimal schema change and no unrelated backfill.

Do not prescribe new enums or columns before the audit establishes what can be reused.

## Acceptance criteria / Live QA

1. With no eligible flying drone, the manual control is disabled or gives a clear no-target message, with no event created.
2. With an eligible drone in flight, manual Drone failure triggers one incident and a visible red warning.
3. The drone diverts from its current position to a nearby simulated emergency landing point without teleporting or resetting battery.
4. The drone lands and remains unavailable for dispatch, visibly requiring service; its original mission does not resume.
5. The interrupted order and mission show consistent, non-delivered outcomes; history and exactly one failure event remain visible in Activity.
6. Failure on a post-delivery return does not undo the completed delivery.
7. Failure during an active 018B recall does not clear the cancellation or revive the drone.
8. Reloading the browser and restarting the worker preserves the emergency/grounded state; no duplicate incident or resumed original flight.
9. Existing dispatch, charging, order generation, cancellation/recall and delivered-marker behavior remain intact.

## Non-goals

- Random/automatic incident generation (future feature), LPR helicopter or safety zones (018E), recipient-unavailable failure (018D).
- Repair scheduling, recovery vehicles, tow operations, spare drone assignment or re-dispatch of stranded parcels.
- Real-world terrain analysis, certified landing zones, obstacle avoidance, regulatory flight safety or realistic component-failure physics.
- New global incident dashboard or substantial map architecture redesign.

## Workflow

**Initialize:** audit only; read this spec and project skills, identify ambiguities, recommend minimal state model, API, persistence, UI and test plan. No code changes, migrations, restarts, data changes or commits.  
**Start Implementation:** only after plan approval.  
**Live QA:** manual browser verification using the criteria above.  
**Finish:** update project docs, run final checks and commit only with explicit approval; no push.

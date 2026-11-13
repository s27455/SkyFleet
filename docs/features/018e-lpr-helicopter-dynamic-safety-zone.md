# Feature 018E — LPR Helicopter & Dynamic Safety Zone

**Project:** SkyFleet  
**Stage:** Implemented and verified (Live QA passed per the owner); not yet committed  
**Scope:** Manually triggered MVP simulation  
**Dependencies:** 018A operational events, 018B cancellation/recall, 018C drone failure, 018D failed delivery/parcel return

## 1. Goal

Simulate a priority LPR emergency helicopter passing through the SkyFleet operating area. Show the helicopter and a moving safety zone, make affected delivery drones yield temporarily, then resume their valid missions when the conflict clears. This is a fictional simulation, **not** a real-world aviation safety system.

## 2. Operator scenario

1. The operator triggers **LPR helicopter** using the existing Management incident control.
2. A helicopter appears on the map and travels along a deterministic route.
3. A clearly visible circular safety zone moves with the helicopter.
4. Drones affected by the zone visibly yield; unaffected drones continue normally.
5. Affected drones resume their original valid missions when the conflict clears.
6. The helicopter completes its route, the zone disappears, and Activity records the incident.

## 3. Business rules

- LPR has priority over SkyFleet delivery traffic.
- Triggering LPR does not itself cancel, deliver, fail, or delete an order.
- Only **one active LPR scenario** at a time in MVP; duplicate triggers receive clear feedback.
- The helicopter is not a fleet drone: it has no orders, fleet battery, hub docking or maintenance.
- Route, speed, zone radius and duration are deterministic **simulation parameters**, not real aviation values. Initialize proposes practical defaults that make Live QA observable.
- The zone is centered on the moving helicopter; map rendering and conflict logic share authoritative scenario state.
- Affected drones must not continue through the active zone as if nothing happened. Unaffected drones continue.
- Drone response is **temporary and reversible**, without teleportation, battery resets, duplicated delivery milestones or phantom landings.
- **Do not prescribe hover versus rerouting before auditing the engine.** Initialize recommends the smallest mechanism compatible with existing movement, timing, battery and emergency safeguards.
- Existing order and mission outcomes remain intact. LPR does not introduce a terminal order status.
- Battery use while yielding must be explicit and consistent with simulation rules; retain existing critical-battery and emergency safeguards.
- Scenario and drone-response state must survive API/worker restarts through shared persistence.

## 4. Interactions with 018B–018D

- **018B cancellation:** a recalled drone still respects LPR restrictions; loaded return resumes when clear.
- **018C drone failure:** actual failure overrides a temporary LPR response; grounded/emergency drones never resume because the zone clears.
- **018D recipient unavailable:** a pending handover cannot complete before arrival; loaded failed-delivery returns respect the zone and retain `DELIVERY_FAILED`.
- Normal delivery, landing, hub assignment and critical-battery safeguards remain correct. No new recovery workflow.

## 5. Operator UI

- Enable existing LPR trigger in Management, with started, already-active and error feedback.
- Display a distinct helicopter marker and translucent moving circular safety zone on the map.
- Clearly label drones temporarily yielding to LPR in existing flight/drone views, distinct from `EMERGENCY` and `MAINTENANCE`.
- Restore normal labels after resumption; include a concise map legend entry.
- Reuse existing frontend polling; no WebSockets or separate incident dashboard.

## 6. Activity, API and persistence

- Reuse durable operational events from 018A; record scenario start and completion once, without per-tick spam.
- Preserve manual-trigger origin semantics from 018D; audit event types before adding new ones.
- Reuse existing incident API/service conventions and clear conflict handling for a second active trigger.
- Keep minimal authoritative state in PostgreSQL, visible to API and worker; no process-local-only scenario state.
- Respect transaction and locking patterns to avoid races with worker milestones, cancellation and drone failure.
- Any migration must be additive and tested on a temporary database before separate approval for the development database.

## 7. Live QA acceptance criteria

1. Manual trigger starts one LPR scenario; repeated trigger does not create a duplicate.
2. Helicopter moves and its safety zone follows it on the map.
3. Affected drone visibly yields; unaffected drone continues.
4. Yielding drone does not teleport, lose its mission or prematurely complete a delivery.
5. Drone resumes when safe; zone disappears when the scenario ends.
6. Existing 018B recall, 018C failure and 018D loaded return retain their outcomes when overlapping with LPR.
7. Activity records the lifecycle without duplicates; API/worker restart preserves coherent state.

## 8. Out of scope

Real LPR tracking, ADS-B, live aviation feeds, real-world safety guarantees, regulatory compliance, altitude separation, advanced pathfinding, multiple helicopters, operator-drawn zones, automatic incidents, rescue/recovery systems, new parcel logistics, dedicated incident dashboard.

## 9. Initialize audit and decisions

Before implementation, Claude Code should audit flight phases, tick timing, movement, delivery milestones, battery, landing and emergency behavior. Present a concise plan recommending:

1. The simplest reversible drone response to a moving safety zone.
2. Deterministic helicopter route, speed, radius, duration and conflict checks.
3. Minimal persistence, endpoint, events and frontend changes.
4. Priority/locking behavior with 018B–018D.
5. Tests, migration scope and genuine decisions requiring approval.

**Workflow:** Initialize is analysis/plan only. Do not implement, apply development migrations, modify simulation data, restart user-owned processes or commit. Wait for plan review before Start Implementation.

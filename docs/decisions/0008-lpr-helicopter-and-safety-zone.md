# 0008 — LPR helicopter and dynamic safety zone (Feature 018E)

**Status:** Accepted for the MVP (demo-only control; a fictional simulation, not an aviation safety system).

## Decisions

- **Hold in place, as a leg of the stored schedule.** A drone yields by standing still: the leg being flown is split where it stops, a `HOLD` leg is inserted and every later leg shifts later by the hold. Elapsed time stays equal to real time, so cancellation (018B), drone failure (018C) and the recipient-unavailable trigger (018D) keep cutting the same leg list. Nothing teleports, and the route, the delivery stop and the landing are unchanged, only later. Rerouting would need pathfinding and is out of scope.
- **Refactor first.** The delivery stop is the last `DELIVERY` leg (`delivery_leg`), not `legs[1]`, in five places; a hold can split the stop, and the handover waits for its last part.
- **Battery is explicit.** A hold costs like cruising at the flight's original pace (an equivalent distance on the leg), at the loaded rate while the parcel is on board; a hold cut short keeps its cost in proportion. The hold keeps the phase of the flight it interrupts, so no phase or check constraint changes.
- **Corridor, not the moment of meeting.** Standing where the helicopter is about to pass is no yield. The drone stops where standing is still outside the corridor (the hold distance either side of the route) and waits until its own continued path is conflict-free, so the zone passes beside it. A drone inside the corridor flies on to the edge if it can leave before the conflict; otherwise it stands where it is and the zone passes over it. This is documented as a simulation limit, not a safety guarantee.
- **Predictive detection.** On each worker tick, inside the flight's own transaction (same locks as the engine), the drone's scheduled path is solved exactly against the helicopter's route over a look-ahead of at least two ticks (more if the worker is late). The result does not depend on tick timing, and a hold already ahead is not inserted again.
- **Unaffordable hold = the existing emergency.** If the hold would take the battery below the critical floor, the drone ends in the existing `BATTERY_CRITICAL` emergency where it stands, outside the zone; no new recovery workflow. The order keeps `OUT_FOR_DELIVERY` and leaves the active views the visibility window after the landing (the interrupted-order rule of 0006 now covers any emergency before the handover).
- **Scenario state in PostgreSQL.** The table `lpr_scenarios` stores the values the scenario started with; a partial unique index allows one `ACTIVE` scenario, so a duplicate trigger answers 409 `LPR_ALREADY_ACTIVE` whatever a pre-check saw. The helicopter flies a straight route at a constant speed, so its position is a pure function of the row and the clock; nothing is written per tick. The worker completes the scenario after its end time, and the zone ends by the clock even without the worker.
- **Defaults (fictional).** A fixed west-to-east corridor at latitude 54.3925 (about 1.1 km north of Galeria Bałtycka, clear of the other Hubs), 80 m/s, a 500 m zone, a 250 m hold margin and a 100 m release extra (`SIM_LPR_*`); a pass takes about 3 minutes.
- **Events.** `LPR_TRANSIT` records the scenario started and completed once each (no order or drone reference) and the first yield of each mission once, with the scenario's origin. Resume is not a separate event. The trigger's origin is stored on the scenario (`MANUAL` today).
- **Precedence.** A failing drone is never held and a grounded drone never resumes; a recall cuts the hold and the drone yields again if needed; the handover waits until arrival and a loaded failed-delivery return keeps `DELIVERY_FAILED`.

## MVP assumptions (not approved business rules)

- Holds are decided on worker ticks: a stopped worker holds nothing, and the zone still ends by the clock.
- The scenario's own started and completed events are not shown in an order's Activity, because `GET /api/events` needs an order, mission or drone filter; the operator sees the lifecycle in the Management panel and the affected orders show the yield. The events API was not changed.
- An order stopped by a battery emergency before the handover keeps the blue "In delivery" marker until it leaves the active views; only Order Details says it was interrupted.

## Consequences

- Any new code that reads the delivery stop must use `delivery_leg`, never an index.
- Random or automatic LPR scenarios are not implemented; the Random incidents switch stays disabled. A future trigger can call `start_scenario` with `origin=AUTOMATIC`.

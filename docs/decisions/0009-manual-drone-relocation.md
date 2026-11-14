# 0009 — Manual drone relocation (Feature 019A)

**Status:** Accepted for the MVP (manual relocation only; automatic rebalancing is 019B and is not implemented).

## Decisions

- **A relocation is a mission without an order.** `missions.purpose` (`DELIVERY` default, `RELOCATION`) and a nullable `missions.order_id`, with checks that a relocation has no order and a delivery has one. Migration `0015` also recreates the partial unique indexes on active missions per drone, so a drone cannot be assigned twice, and widens the phase (`RELOCATING`) and event-type (`DRONE_RELOCATION`) checks. Its downgrade fails while a relocation exists.
- **Reuse the engine.** A relocation is created directly `IN_FLIGHT` with a `MissionFlight` of phase `RELOCATING` and one `RELOCATE` leg. State is still a pure function of the legs and the clock, so it survives restarts. There is no second movement loop. The engine skips the delivery milestone for it and carries no parcel.
- **One reusable service.** `start_relocation(...)` in `simulation/relocation.py` (with `origin`, default `MANUAL`) locks the drone, then the destination Hub, revalidates and writes the mission, flight, drone status and `STARTED` event in one transaction. It refuses when the worker heartbeat is stale. A future 019B can call it.
- **Eligibility is deterministic.** The drone is IDLE, docked and without an active mission; the destination is a different, existing Hub within the 14 km budget with room; the battery covers the empty-flight energy plus the 20% reserve (no 100% rule). Orders waiting at the source Hub or an unreserved destination are warnings, not blockers. Refusals answer 409 `RELOCATION_NOT_ELIGIBLE` with the plan.
- **The Hub changes on landing only.** The landing decision reuses the existing capacity handling under the Hub lock. If the destination is full the drone diverts, and `hub_id` follows the Hub it actually lands at.
- **Events.** One type, `DRONE_RELOCATION`, with `details.phase` `STARTED`, `COMPLETED` (with `diverted`) or `EMERGENCY`, deduplicated per mission. The existing Activity timeline is reused for drones through `GET /api/events?drone_id=`.
- **Compatibility.** Drone failure treats `RELOCATING` as a failable phase (never loaded). Cancellation, failed delivery and dispatch skip order-less missions.
- **UI.** The Relocate control exists only in `DroneDetailPanel`; the backend decides eligibility and the UI shows its answer.

## MVP assumptions (not approved business rules)

- The relocation distance budget and reserve reuse the existing dispatch constants.
- A relocation cannot be cancelled or redirected once started (out of scope in the spec).

## Consequences

- Code that reads `mission.order_id` must handle `None`.
- The four PostgreSQL concurrency tests (`tests/simulation/test_relocation_postgres.py`) are still to be run.

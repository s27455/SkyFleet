# 0006 — Drone failure and emergency landing (Feature 018C)

**Status:** Accepted for the MVP (demo-only control).

## Decisions

- **One backend behavior for every trigger.** `POST /api/incidents/drone-failure` takes no body and calls `trigger_drone_failure`, which chooses the target (injectable RNG for tests), performs one real transition and appends one `DRONE_FAILURE` event in the same transaction, or answers 409 `NO_ELIGIBLE_TARGET` and changes nothing. A future automatic trigger calls the same service (`origin=AUTOMATIC`).
- **Eligible target.** A flight in `OUTBOUND`, `DELIVERING`, `RETURNING` or `DIVERTING` (a 018B recall included), with its drone and mission in flight, not already failed, and whose next milestone is not already due. Locks follow the engine's order (flight, mission, order, drone); a candidate that changed is skipped.
- **Emergency approach.** `mission_flights.failed_at` marks the failure. The remaining legs become the leg flown so far plus one `EMERGENCY` leg to a landing point 250 m along the current heading (`SIM_EMERGENCY_LANDING_DISTANCE_M`, due north when the heading is unknown). Position and battery continue without a jump; phase `EMERGENCY_APPROACH`. No GIS, terrain or obstacle check.
- **Grounding.** When the approach ends the engine sets the flight to `EMERGENCY` (reason `DRONE_FAILURE`, `emergency_at` and `ended_at` from real UTC), the mission to `EMERGENCY` and the drone to `MAINTENANCE` at the landing point. `MAINTENANCE` is the "requires service" state: never counted as docked, never dispatched or charged. No repair workflow. The original mission and any recall never resume.
- **No new order status.** An undelivered order stays `OUT_FOR_DELIVERY`; the UI shows "Delivery interrupted by drone failure", derived from the failed flight. Delivered and cancelled orders keep their status. An interrupted order stays in the full history and leaves the active views and the map 120 s after `ended_at` (an `exists` subquery in `list_active_orders` mirrored by the pure `is_order_active(..., interrupted_at=)`).
- **Cancellation stays blocked.** Cancelling an order whose drone is failing or grounded returns 409 `DRONE_FAILED` with a message that differs for an approach in progress and a grounded drone; it never repairs or resets the drone.
- **Migration `0012`.** Adds the nullable `failed_at`, widens `phase` to `String(24)` (`EMERGENCY_APPROACH` has 18 characters; found by the PostgreSQL tests, not by SQLite) and widens the phase and emergency-reason CHECK constraints. It touches no row.

## MVP assumptions (not approved business rules)

- The parcel of an interrupted order is not handled further; there is no reassignment, recovery or compensation (`business-rules.md` Q3 and Q6 stay partly open).
- *Corrected (Feature 022):* it was assumed that the Management drone status toggle could return a grounded drone to `IDLE`. It cannot: `IDLE` requires the drone to be within the 50 m docking radius of a Hub, and a grounded drone stops about 250 m away by design, so a grounded drone had no way back into service until Feature 022.
- The approach window is short (about 5 to 20 s with default timings; `SIM_FLIGHT_MIN_SECONDS` and `SIM_FLIGHT_MAX_SECONDS` can slow flights).

## Consequences

- 018D and 018E must keep order, mission and drone state independent and reuse `append_event` and the same trigger convention.
- Random or automatic failures are not implemented; the Random incidents switch stays disabled.

## Update: recovery (Feature 022)

A grounded drone is no longer permanently out of service. 120 s of real time after the landing (`mission_flights.emergency_at`) the worker recovers **every** completed `DRONE_FAILURE` landing, whether the failure was automatic or manual: the drone moves straight to the nearest Hub with a free place (no flight), keeps its battery, becomes `CHARGING` below 100 % (else `IDLE`) and one `DRONE_RECOVERED` event (unique key `DRONE_RECOVERED:<mission>`) is appended. The mission stays `EMERGENCY`, the flight stays an emergency, and the order keeps its status (an interrupted order is still not resurrected). A drone an operator put into `MAINTENANCE`, one that stopped for another emergency reason, or one still in its emergency approach is never recovered. See `docs/features/022-incident-acknowledgement-drone-recovery.md`.

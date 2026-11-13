# 0005 — Order cancellation and drone recall (Feature 018B)

**Status:** Accepted for the MVP (demo-only controls).

## Decisions

- **Cancellation is a business transition, not deletion.** `POST /api/orders/{id}/cancel` sets the order to `CANCELLED`, stamps `cancelled_at` with the real UTC time and appends an `ORDER_CANCELLED` event (origin `MANUAL`, dedupe key `ORDER_CANCELLED:<order_id>`) in the same transaction. The technical `DELETE /api/orders/{id}` is unchanged and still only accepts a mission-free `READY_FOR_PICKUP` order, so a cancelled order is refused (`ORDER_NOT_EDITABLE`).
- **Eligibility matrix** (checked under row locks; nothing is partially applied):

  | State | Result |
  |---|---|
  | No active mission, status `CREATED` / `AWAITING_HANDOVER` / `READY_FOR_PICKUP` | Order `CANCELLED` |
  | `ASSIGNED` mission (not airborne) | Mission `CANCELLED`, order `CANCELLED`, drone untouched |
  | In flight, parcel not yet handed over | Order `CANCELLED`, drone recalled |
  | `DELIVERED`, or elapsed time already past the delivery stop | 409 `ORDER_ALREADY_DELIVERED` |
  | Already `CANCELLED` | 200, current order, no second event or recall |
  | Drone not flying normally | 409 `DRONE_NOT_RECALLABLE`, nothing changes |

- **Recall.** The flight's remaining legs are replaced by one loaded `RECALL` leg from the current position to the nearest Hub reachable with the loaded consumption rate, and `mission_flights.recalled_at` marks it. The drone keeps its position and battery (no teleport). The engine skips the delivery milestone for a recalled flight, uses the loaded rate for reachability and diversion, and lands it with the normal landing logic. The mission stays `IN_FLIGHT` until landing, and `drone.hub_id` changes only then (Feature 017C). A defensive 409 `RECALL_NOT_POSSIBLE` refuses the cancellation without changing anything if no Hub is reachable; no new workflow is built around battery shortages.
- **Concurrency.** Locks are taken in the engine's order (flight, mission, order, drone); a cancel that finds a mission it did not lock the flight for (takeoff just committed) retries from the start. Duplicate cancellations are idempotent through the order status and the event dedupe key.
- **Visibility.** A cancelled order stays in the active views for the same window as a delivered one, measured from `cancelled_at`, and stays in the full history.
- **Independence.** Cancellation never changes a drone's health and never overrides an emergency state.

## MVP assumptions (not approved business rules)

- A recalled parcel stays on the drone and counts as returned when the drone lands; nothing further is done with it (`business-rules.md` Q3 and Q5 stay partly open).
- No route polyline: a recall is shown through the flight phase ("Recalled: returning with the parcel"), the target Hub and the drone's movement.

## Consequences

- 018C to 018E must keep order, mission and drone state independent, as 018B does.
- An undelivered emergency is now possible for a recalled flight (existing emergency semantics, order stays `CANCELLED`).

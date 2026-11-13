# 0007 — Failed delivery and parcel return (Feature 018D)

**Status:** Accepted for the MVP (demo-only control).

## Decisions

- **A real order status.** `DELIVERY_FAILED` is a new terminal order status with `orders.delivery_failed_at` (real UTC time of the transition). Unlike the drone failure of 0006, where the order was only interrupted and the owner asked for no new status, a failed handover is a definite business outcome that must differ from `DELIVERED`, `CANCELLED` and an interruption; a status gives lists, history and the 120 s window a single source. The flight carries the process state, not the outcome: `recipient_unavailable_at` (pending, set at trigger), `recipient_unavailable_origin` and `handover_failed_at` (the real failure).
- **One backend behavior for every trigger.** `POST /api/incidents/recipient-unavailable` takes no body and calls `trigger_recipient_unavailable`, which chooses the target (injectable RNG), stamps the pending outcome and returns it, or answers 409 `NO_ELIGIBLE_TARGET` and changes nothing. The trigger's `origin` (`MANUAL` by default, `AUTOMATIC` for a future trigger) is stored on the flight.
- **Eligible target.** An `OUTBOUND` or `DELIVERING` flight of an `OUT_FOR_DELIVERY` order, with its mission and drone in flight, not recalled (018B), failed (018C), delivered or already marked, whose delivery milestone the worker has not reached, and with a Hub reachable from the destination at the loaded rate. A drone already at the delivery stop is eligible. Locks follow the engine's order (flight, mission, order, drone); a candidate that changed is skipped.
- **The failure becomes real at the attempt.** The trigger changes no route. At the delivery milestone the engine, in one transaction, sets the order to `DELIVERY_FAILED`, stamps `handover_failed_at`, replaces the empty return by one loaded return leg to the nearest reachable Hub (the helper `nearest_reachable_hub`, shared with the 018B recall) and appends one `RECIPIENT_UNAVAILABLE` event with the stored origin and dedupe key `RECIPIENT_UNAVAILABLE:<mission_id>`. The event is therefore written at the failed handover, never at the trigger, so the timeline cannot claim a failure that has not happened. If no Hub is reachable (not expected: missions keep a reserve), the planned return Hub is kept and the existing safeguards apply; no new workflow.
- **Loaded return and landing.** Position and battery continue without a jump at the loaded rate; the engine treats a flight with `handover_failed_at` like a recalled one (loaded diversion, critical-battery check, emergency invariant) and the normal landing docks the drone: `IDLE`, mission `COMPLETED`, `drone.hub_id` only on landing.
- **Precedence.** Cancellation while the outcome is pending recalls the drone and the order stays `CANCELLED`. A `DELIVERY_FAILED` order cannot be cancelled (409 `ORDER_NOT_CANCELLABLE` with an explanation). A drone failure while pending wins (the order stays interrupted); a drone failure on the way back keeps `DELIVERY_FAILED` (failure stage `HANDOVER_FAILED`).
- **Visibility.** A failed delivery stays in the active views for the same window as a delivered one, measured from `delivery_failed_at`, and stays in the full history.
- **Migration `0013`.** Widens `ck_orders_status_valid` and adds four nullable columns; it touches no row.

## MVP assumptions (not approved business rules)

- The returned parcel counts as returned at landing; nothing further happens to it (`business-rules.md` Q3 stays partly open). No redelivery, retry scheduling or inventory.
- The trigger window is short (roughly 10 to 60 s per flight with default timings; `SIM_FLIGHT_MIN_SECONDS` and `SIM_FLIGHT_MAX_SECONDS` can slow flights).

## Consequences

- 018E must keep order, mission and drone state independent, reuse `append_event` and the same trigger convention (an `origin` parameter, a stored origin when the event comes later).
- Automatic or random triggering is not implemented; the Random incidents switch stays disabled.

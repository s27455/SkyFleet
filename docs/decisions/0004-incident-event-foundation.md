# 0004 — Incident event foundation and extension guide (Feature 018A)

**Status:** Accepted for the MVP (demo-only controls).

## What exists after 018A

- Table `operational_events` (migration `0010`): append-only, with a stable integer id, an
  `event_type` code, the real UTC `occurred_at`, an `origin` (`SYSTEM`, `AUTOMATIC`, `MANUAL`),
  optional `order_id` / `mission_id` / `flight_id` / `drone_id` references, a short `reason`,
  bounded JSON `details` and an optional unique `dedupe_key`. Order is `occurred_at`, then `id`.
- `app/events/service.py: append_event` adds an event to the caller's open transaction and never
  commits. `GET /api/events` is read-only and requires `order_id`, `mission_id` or `drone_id`
  (default limit 50, maximum 200; the newest events, oldest first).
- The only emitted event is `ORDER_CREATED` (`MANUAL` for `POST /api/orders`, `AUTOMATIC` for
  generated orders), written in the same transaction as the order insert. Existing orders have no
  events; that is valid and is shown as an empty timeline. Nothing is backfilled.
- The incident catalog codes are reserved: `ORDER_CANCELLED` (018B), `DRONE_FAILURE` (018C),
  `RECIPIENT_UNAVAILABLE` (018D), `LPR_TRANSIT` (018E). They are categories, not statuses.
- The Simulation Events controls and the Random incidents switch are visible but disabled. No
  trigger endpoint, scheduler or random incident exists.

## Decisions

- **Timestamps** are the real UTC time of the committed transition, never the simulated flight
  timeline. The API always sends an explicit UTC offset.
- **Foreign keys** are all `ON DELETE RESTRICT`, so history is never silently detached.
- **Cancellation vs. technical deletion.** Normal operations cancel orders (018B adds the
  `CANCELLED` status and keeps all history). `DELETE /api/orders/{id}` stays a technical
  maintenance tool for test data, with unchanged eligibility rules; it explicitly deletes the
  order's events in the same transaction. Nothing in normal operation may use it instead of
  cancellation. `DELETE /api/drones/{id}` is unchanged: a drone that has events has operational
  history and is refused with the existing `DRONE_HAS_HISTORY` error.
- **Idempotency.** `dedupe_key` uses `INSERT ... ON CONFLICT DO NOTHING`, so a repeated append
  neither raises nor aborts the PostgreSQL transaction, and `append_event` returns `False`. This is
  at-most-once recording per key, not an exactly-once guarantee. Keys are domain-derived, for
  example `ORDER_CREATED:<order id>`.

## Extension guide for 018B to 018E

Keep it a small contract, not a framework.

1. **One service per scenario**, called by both the manual trigger and (later) the automatic
   scheduler. A trigger is one request: the backend picks an eligible target, performs a real
   domain transition, appends the event, and answers with the actual affected entities or a clear
   `NO_ELIGIBLE_TARGET`. Never add an endpoint that accepts a trigger and does nothing.
2. **Handler shape:** open the transaction; lock the rows with the existing `FOR UPDATE`
   conventions (order, mission, drone); validate eligibility on the locked rows; change the domain
   state; `append_event(...)` with a `dedupe_key`; commit once. A failure rolls back both.
3. **No duplicate or conflicting incidents.** Enforce it in the database, as missions do: an
   explicit active-incident row with a partial unique index (one active incident per mission),
   plus the locked eligibility check. A worker retry or restart finds the active row or the
   existing `dedupe_key` and does nothing.
4. **Active state is separate from history.** Map badges read an explicit active-incident state
   exposed by the later feature. Never infer "still active" from the event history.
5. **Automatic scheduling** is added incrementally to the existing simulation worker (no second
   worker, no client-side state machine), calling the same services. Moderate demo-friendly
   proposal, not activated: at most one random incident per 3 to 5 minutes, a 2 to 3 minute
   cooldown per incident type, never more than one active incident per mission.
6. **Decide first, then build:** parcel custody, battery and route feasibility, and the order,
   mission and drone state machines. Cancellation must not erase history or resolve a drone
   failure; order, mission and drone states stay logically independent and consistent.
7. Each feature enables only its own control after its backend handler and visual behavior are
   complete. All of this is MVP/demo-only.

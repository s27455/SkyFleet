# Feature 018B — Order Cancellation & Drone Recall

**Project:** SkyFleet  
**Status:** Implemented and verified (Live QA passed per the owner); not yet committed  
**Depends on:** Feature 018A — Incident Foundation & Simulation Controls

## 1. Goal

Implement a real, user-visible **Cancel order** action. Cancellation is a business state transition, not deletion: the order remains in the database and history, with an auditable operational event. If a healthy drone is already carrying the parcel, it is recalled to the nearest reachable hub instead of continuing delivery.

Keep the feature deliberately small. Do not implement drone failures (018C), failed deliveries (018D), LPR safety zones (018E), or automatic/random incident generation.

## 2. Existing architecture and constraints

- FastAPI backend, PostgreSQL, simulation worker, React frontend with two-second polling.
- 018A introduced durable `operational_events`, `GET /api/events`, an order Activity timeline, and disabled incident controls.
- 018A emits `ORDER_CREATED` transactionally; historic orders have no fabricated events.
- 017C already supports nearest **reachable** hub selection for post-delivery returns and updates a drone's current hub only on landing. Reuse this behavior where suitable; do not assume a hub is reachable merely because it is geographically closest.
- A separate technical DELETE endpoint exists for eligible test/maintenance orders. Preserve its current behavior and eligibility rules; it is not the user-facing cancellation mechanism.
- Order, mission, flight, drone and parcel/assignment state must stay internally consistent. Confirm actual models and statuses during Initialize rather than assuming names or fields not present in the repository.

## 3. User stories

1. As an operator, I can cancel an eligible order from **Management → Orders** and immediately see its cancelled status.
2. If the order has not started flying, cancellation prevents dispatch and does not launch a recall flight.
3. If a healthy drone is en route with the parcel, cancellation redirects it to a reachable hub, with a visible updated route and continued battery/position simulation.
4. I can inspect an Activity entry identifying the cancellation, its time, origin and reason, without losing prior history.
5. If cancellation is not allowed, I get a clear explanation and no partial changes occur.

## 4. Cancellation eligibility and state transitions

During Initialize, inspect the actual order, mission, flight and drone state machines and propose a precise eligibility matrix before implementation.

Required policy:

- **Pre-flight:** An order not yet delivered and not physically in flight can be cancelled if its current state permits it. Prevent subsequent dispatch. Release any reservation/assignment safely according to existing state semantics. Do not create a fictitious flight or parcel return.
- **In flight, healthy drone:** Cancel the delivery order, terminate/redirect its delivery intent, and create or transition to a **return-with-parcel** flight/mission as appropriate to existing architecture. Choose the nearest hub reachable with the drone's current position, battery and existing safety constraints. Do not teleport the drone or instantly mark it IDLE. Update hub association only upon landing.
- **Already delivered:** Cancellation is rejected. Do not rewrite delivery history.
- **Already cancelled:** Idempotent behavior; do not generate another cancellation event or duplicate recall. The API should have a documented, predictable response.
- **Ineligible/conflicting state:** Reject with an explicit error; do not partially mutate records.
- **Drone already failed, grounded, or otherwise incapable of recall:** Cancellation must **not** heal the drone, override an emergency state or silently turn it into a normal return. Preserve independent technical state. During Initialize, propose the safest minimal behavior supported by current state models; if unsupported, reject cancellation cleanly with a clear reason rather than introducing 018C behavior.

Define exactly what happens when an order is assigned but the drone has not yet taken off, and when an in-flight return is already in progress. Handle these boundary cases consistently.

## 5. Backend and persistence

- Add a focused cancellation API action following existing API naming and response conventions; prefer a business operation such as `POST /api/orders/{order_id}/cancel`, not HTTP DELETE.
- Validate eligibility and perform cancellation, event insertion and any mission/flight reassignment atomically in PostgreSQL.
- Use appropriate row locking / concurrency control so dispatch, the simulation worker and simultaneous cancellation requests cannot double-dispatch, duplicate recall or leave inconsistent states.
- Persist the order's `CANCELLED` state, using a migration only if the current schema genuinely requires one. Follow the existing enum and migration conventions.
- Append a durable `ORDER_CANCELLED` operational event using the 018A event mechanism, with correct references, UTC `occurred_at`, `origin=MANUAL`, and a concise human-readable reason. Ensure at-most-once semantics for repeated requests.
- If a distinct recall-start event materially improves the existing Activity timeline, propose it in Initialize and justify it; avoid event proliferation.
- Ensure cancelled orders are excluded from future automatic dispatch and do not count as successful deliveries.
- Preserve the technical DELETE endpoint and its existing restrictions and event cleanup behavior.

## 6. Simulation and drone recall

- Reuse existing flight simulation and reachable-hub calculations where possible.
- The drone must visibly stop following the customer delivery leg and follow a return route to the selected reachable hub.
- The parcel stays with the drone during recall and is considered returned only after landing. Record the result in existing mission/flight/order state in a way that remains inspectable.
- Continue normal position, battery, speed and flight updates while returning; do not reset battery or teleport.
- On arrival, complete the return cleanly and make the drone available only if normal battery/charging/maintenance rules allow it.
- If no hub is reachable, do **not** fake a successful return or silently pick an unreachable hub. Propose and implement a minimal, consistent failure response or safe fallback based on existing simulation capabilities, without implementing 018C emergency-landing incidents.
- Avoid creating multiple active flights or missions for the same drone. Keep order cancellation independent from drone health.

## 7. Frontend UX

- Enable the existing **Cancel order** control introduced in 018A only for eligible orders. Keep the other three incident icons and the random-events placeholder disabled.
- Provide a compact confirmation interaction that clearly states that cancellation is permanent for the order; when a parcel is in flight, explain that the drone will return to a reachable hub.
- Show pending, success and actionable error states. Prevent accidental double submission.
- Update order status to `CANCELLED` and reflect the cancellation in the Activity timeline through the existing events API.
- Show recall visually on the map: updated route and drone movement toward the selected hub. Preserve established order/marker display rules; a cancelled delivery must not appear as a delivered green marker.
- Keep the layout usable at narrow mobile widths (including 375px).
- Do not redesign the Orders screen or add a new incident dashboard.

## 8. Testing and acceptance criteria

Automated tests should cover, at minimum:

1. Cancellation of an eligible unassigned/pre-flight order; remains persisted and cannot be dispatched.
2. Cancellation of an assigned but not airborne order, including safe release of assignment if applicable.
3. Cancellation of an active delivery flight; exactly one recall is initiated toward a reachable hub.
4. Recall follows normal simulation movement and battery consumption, lands, and only then updates the drone's current hub.
5. Delivered orders cannot be cancelled.
6. Repeated/concurrent cancellation does not duplicate `ORDER_CANCELLED` or create multiple recall flights.
7. Cancellation racing with dispatch/worker processing maintains valid invariants.
8. No reachable hub does not produce a fictitious successful recall.
9. Existing failed/grounded/maintenance states are not overwritten by cancellation.
10. The order and Activity history remain accessible; the technical DELETE endpoint still behaves as before.
11. Frontend button eligibility, confirmation, loading, errors, event timeline and map route update.
12. Regression coverage for automatic dispatch, order generation, delivery history, map markers and charging.

Manual browser QA:

- Cancel a newly created pre-flight order: `CANCELLED`, one Activity event, no dispatch.
- Cancel an in-flight order: delivery route switches to a visible return route; drone reaches a reachable hub without teleporting; parcel return is represented consistently.
- Refresh the page: cancellation status and Activity persist.
- Attempt cancellation of delivered/already-cancelled/ineligible orders: clear and consistent behavior.
- Verify other three incident buttons and random-events control remain disabled.
- Verify narrow layout and normal simulation still work.

## 9. Explicitly out of scope

- Technical DELETE changes, data cleanup, or historical event backfills.
- Drone failure, emergency landing, repairs or recovery (018C).
- Recipient unavailable / failed delivery (018D).
- LPR helicopter, moving safety zones or airspace conflict resolution (018E).
- Random incident scheduler or automatic cancellation incidents.
- Docker deployment, runtime restructuring, new services or broad UI redesign.

## 10. Implementation workflow

**Initialize — audit and plan only:** inspect actual models, statuses, existing routing/return implementation, API, events and frontend controls. Identify gaps, define the state-transition matrix, event strategy, concurrency approach, unreachable-hub policy, file list, tests and any migration. Flag ambiguities and stop for approval. No code changes, DB changes, process restarts or commits.

**Start Implementation — after approval:** implement only the agreed 018B scope, run focused and regression tests, and report without committing. Do not stop or restart user-owned PowerShell processes without permission.

**Browser QA:** verify the acceptance scenarios against the running application.

**Finish — only after QA approval:** update feature documentation and progress tracker, review the final diff, run final checks and create a focused commit. Do not push.

## 11. Decisions to confirm in Initialize

- Exact eligibility and transitions for all existing order/mission/flight statuses.
- Representation of parcel ownership and completion of a recall in the current schema.
- Whether recall reuses an existing return flight/mission type or needs a narrowly scoped new type.
- Behavior when no reachable hub exists, without simulating an 018C failure.
- Event types beyond `ORDER_CANCELLED`, if any, and their deduplication strategy.
- How to prevent worker/dispatch/cancellation races using the existing database patterns.

## 12. Implementation result

Delivered as planned, with the approved correction that a recalled drone simply returns, loaded, to the nearest reachable Hub using the existing return and diversion logic (no new no-reachable-Hub or emergency workflow; a defensive refusal that changes nothing remains). Decisions and the state matrix: `docs/decisions/0005-order-cancellation-and-recall.md`.

Initialize answers (section 11): eligibility matrix and transitions are in the decision record; a recall is a flight whose remaining legs were replaced by one loaded `RECALL` leg, marked by `mission_flights.recalled_at` (no new flight phase, no new mission type); the parcel stays on the drone and counts as returned at landing (MVP simplification); the only event beyond `ORDER_CANCELLED` is none, with dedupe key `ORDER_CANCELLED:<order_id>`; races are prevented by row locks in the engine's order plus a retry, and the active-mission uniqueness indexes.

Live QA fix (frontend only): the first UI offered Cancel only as a shortcut in the Management overlay, which hid every way to select an order. The final UI adds Cancel order to Order Details, selectable ids in the Management table, a solid red Cancelled marker with a legend entry, an explicit "Recalled: returning with the parcel" phase, the cancelled notice and recalled flight in Order Details, and an Activity timeline that refreshes at once.

Verification: backend pytest 561 passed (32 PostgreSQL-marked deselected); full PostgreSQL suite 32 passed on a temporary database; ruff, ruff format, mypy clean; frontend lint, typecheck, format check, 649 unit tests and a production build pass; migration `0011` applied to the development database with approval. Not run: QA or code-review agents. Known limitations: see the progress tracker.

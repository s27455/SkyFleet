# Feature 018D — Failed Delivery & Parcel Return

**Project:** SkyFleet  
**Stage:** Implemented and verified (Live QA passed per the owner); not yet committed  
**Scope:** MVP, one independent feature in the 018 incident series

## 1. Goal

Simulate an unsuccessful delivery when the recipient is unavailable. The drone reaches the delivery location, cannot hand over the parcel, and returns **with the parcel** to the nearest reachable hub. The order must not be recorded as delivered. The drone remains operational and becomes available again after landing, subject to existing charging/dispatch rules.

This is a **delivery failure**, not a drone failure (018C), order cancellation (018B), or a real-world logistics workflow.

## 2. User-facing scenario

1. An order is dispatched and a drone flies toward its delivery point.
2. The operator triggers **Recipient unavailable** from the existing Simulation Events controls. The system chooses an eligible delivery in progress; the UI should clearly identify the affected order/drone. If the existing incident controls support selecting a specific target, reuse that pattern without inventing a separate targeting interface.
3. The failure is applied **at the delivery attempt**, not as an arbitrary mid-flight turnaround. If triggered while outbound, record a pending recipient-unavailable outcome and let the drone reach the destination first. The UI must make the pending outcome understandable.
4. At the delivery point, no successful handover occurs. The drone turns back **still carrying the parcel** toward the nearest reachable hub.
5. The order is marked as an unsuccessful delivery, an operational event is persisted, and the drone returns visibly with continuous position and battery consumption appropriate to a loaded flight.
6. After landing, the drone's hub association is updated and it follows the normal availability/charging rules. The unsuccessful order remains in full history.

## 3. Business rules

- The recipient-unavailable incident applies only to an active, not-yet-delivered delivery with a functioning drone. It must not overwrite a cancelled order, a completed delivery, an active recall, or an 018C failure/emergency.
- The incident must be idempotent for a given delivery: repeated requests or worker ticks cannot create duplicate failure outcomes or events.
- The parcel is **not delivered** and must not set `delivered_at` or emit a successful-delivery outcome.
- A loaded return consumes energy using the existing loaded-flight rules; no teleportation, battery reset, or premature `drone.hub_id` change.
- The nearest reachable hub is chosen using existing hub reachability/capacity and diversion logic. Retain existing defensive safeguards; do not design new battery-shortage workflows for this MVP.
- A successful return ends the mission and leaves the drone usable under existing rules; it must not put the drone in `MAINTENANCE` merely because the recipient was unavailable.
- Keep unsuccessful deliveries in full order history. In active views and on the map, show the failure distinctly while relevant and then use the project's established 120-second post-completion visibility convention. Confirm the exact timestamp and filtering implementation during Initialize.
- Existing technical DELETE semantics are unchanged.

## 4. Status and data design — audit before choosing

The current order, mission, flight and event schemas must be audited during Initialize. Propose the **smallest persistent representation** that distinguishes an unsuccessful delivery from `DELIVERED`, `CANCELLED`, and a drone emergency. A dedicated order status such as `DELIVERY_FAILED` may be appropriate, but is **not pre-approved**; compare it with a minimal failure field and explain the implications for active lists, history, analytics, and existing constraints. Avoid multiple overlapping statuses or a generic incident framework.

Persist enough information to survive a worker restart between trigger, delivery attempt and loaded return. The exact moment at which the failure event is recorded must be explicit and consistent with the UI (trigger versus actual unsuccessful handover). Use the existing `operational_events` foundation, with a meaningful event type, origin and deduplication key.

## 5. Backend behavior

- Reuse the 018A incident/event conventions and 018B loaded recall/return primitives where practical.
- Add one small backend trigger service and endpoint, reusable later by automatic incidents in 018E or subsequent work.
- Choose an eligible order/flight under the established locking and concurrency conventions; revalidate eligibility inside the transaction. Return clear feedback if no eligible target exists.
- If triggered before arrival, store the pending outcome without altering the drone's current position or bypassing the destination.
- At the delivery milestone, branch to unsuccessful handover and loaded return rather than successful delivery and unloaded return.
- Handle landing and any existing hub diversion with the parcel still onboard.
- Preserve 018B/018C invariants under races: cancellation, drone failure, worker tick and duplicate trigger must not create conflicting order/mission/flight states.
- Prefer additive, reversible schema changes only where justified. Any development-database migration requires separate approval.

## 6. Frontend and map

- Enable the existing **Recipient unavailable** simulation control when an eligible delivery exists; keep the other incident controls unchanged.
- Show a clear pending/success/no-target/error message and identify the affected order and drone. Do not imply a delivery failed before the delivery attempt actually occurs.
- Distinguish the unsuccessful delivery from waiting (gray), out-for-delivery (blue), delivered (green), cancelled (red), and interrupted by drone failure (018C). Choose a visually accessible marker style/color and legend entry that does not conflict with existing states.
- Show the unsuccessful-delivery status/reason in Order Details, the Management Orders table and full history.
- Make the loaded return visible in the existing Flight/Drone panels: meaningful phase label, target hub and continuous map movement. No new route polyline.
- Refresh the Activity timeline promptly after the persisted event; do not rely on duplicate events from polling.
- Keep the UI compact and reuse existing components and confirmation/feedback patterns.

## 7. Live QA acceptance criteria

1. **Eligibility:** Recipient unavailable can be triggered for an eligible delivery; no eligible delivery gives understandable feedback and no event.
2. **Before arrival:** Trigger while outbound; drone continues to recipient, with pending failure clearly indicated.
3. **At destination:** The parcel is not delivered; order is visibly unsuccessful and no successful-delivery timestamp/outcome is written.
4. **Loaded return:** Drone flies back with parcel to an appropriate hub, preserving position and battery continuity, and changes hub association only on landing.
5. **After landing:** Drone is operational under normal rules; order remains unsuccessful in full history, with appropriate active-map expiry.
6. **History and regressions:** Exactly one operational event; cancellation and drone failure do not override one another; ordinary deliveries, charging and dispatch continue to work.

## 8. Tests and verification

Backend unit/integration tests for eligibility, timing of the pending outcome, failed handover, loaded battery consumption, return/diversion, landing, persistence after restart, idempotency and interactions with 018B/018C. PostgreSQL concurrency tests for trigger-versus-worker, trigger-versus-cancel and trigger-versus-drone-failure where relevant. Frontend tests for control feedback, order state, marker/legend, flight label and Activity refresh. Run the project's existing backend/frontend verification gates.

## 9. Out of scope

- Automatic/random triggering (later feature)
- Redelivery, retry scheduling, customer contact, parcel collection or inventory tracking
- Drone hardware failure, emergency landing, repair workflow
- New route polylines, detailed terrain/GIS, airspace restrictions
- Broad incident architecture refactors, deployment changes, unrelated fixes

## 10. Initialize questions for Claude Code

Audit and recommend, without implementing:

1. The smallest durable order/flight state representation for failed delivery and pending recipient-unavailable outcome.
2. Precise trigger eligibility and timing relative to the delivery milestone; whether a manual trigger should also support a drone already at the delivery stop.
3. How to reuse 018B's loaded return and existing hub/diversion logic without duplicating the flight engine.
4. Exact event semantics and idempotency under worker/incident races.
5. Active-map expiry timestamp, UI marker differentiation and any genuine blockers requiring product approval.

**Initialize is analysis only.** No implementation, migrations, database modifications, process restarts or commits until the plan is reviewed.

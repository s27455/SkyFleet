# Feature 017B — Delivery Marker States

**Project:** SkyFleet  
**Status:** Implemented and tested; finalized by the owner (2026-11-13). The full blue → green → expired sequence was not observed in a browser by the implementer. See section 12.  
**Priority:** MVP map clarity  
**Depends on:** Feature 017A — Delivered Orders Lifecycle

## 1. Goal

Make delivery-address diamonds on the map communicate the current order lifecycle. Pending, in-progress and recently delivered orders should be visually distinguishable. Delivered markers must disappear from the operational map after the **same 120-second visibility window** established by 017A.

This feature changes **delivery destination markers**, not hub markers or drone markers.

## 2. User story

As a fleet operator, I want to see which delivery addresses are waiting, being served or have just been delivered, so I can understand operational progress at a glance without opening each order.

## 3. Expected behavior

| Order lifecycle | Marker appearance | Visibility |
|---|---|---|
| Pending / waiting for assignment | Neutral gray diamond | Visible while active |
| Assigned / in delivery | Blue diamond | Visible while active |
| DELIVERED, less than 120 s since `delivered_at` | Green diamond | Visible during the 017A grace period |
| DELIVERED, 120 s or more since `delivered_at` | No marker | Excluded by 017A active-order API |
| Failed / cancelled / other exceptional states | Existing neutral or clearly labeled state; do not invent exception behavior | Follow current operational visibility rules; defer dedicated exception palette to future events feature |

**Important:** Audit actual backend `OrderStatus` values and map each existing status explicitly. Do not invent new backend statuses or assume that a flight phase equals an order status.

## 4. Functional requirements

1. **Single source of truth.** Derive marker state from the order status already returned by the backend. Reuse the `getActiveOrders` / `GET /api/orders?active=true` data flow introduced in 017A.
2. **No duplicate expiry logic.** Do not implement a second client-side 120-second timer. A marker disappears when its order is absent from the next active-orders response (existing polling approximately every 2 s).
3. **Consistent visual language.** Use gray for pending, blue for assigned/in progress, green for delivered. Prefer existing SkyFleet design tokens when possible. Ensure contrast against light/dark map backgrounds.
4. **Stable marker identity.** Keep markers keyed by order ID so status changes update the same marker rather than producing duplicates or flashes.
5. **Interaction continuity.** Existing marker click/selection and order detail behavior should continue to work. When 017A removes an expired selected order, close or clear selection gracefully without errors.
6. **Legend and accessible text.** Provide a compact legend or update the existing legend. Status must be understandable without color alone, including in accessible names/tooltips/details. Preserve keyboard support where markers already provide it.
7. **Hub and drone visuals untouched.** Do not recolor hub icons, drone markers or mission paths as part of 017B.
8. **Performance.** Reuse existing marker rendering and polling; avoid extra network requests, animations, timers or dependencies.

## 5. Scope

### Included
- Status-to-marker-style mapping, ideally as a small pure helper.
- Delivery marker styling for all supported active order statuses.
- Delivered marker's green state during the 017A grace period.
- Removal from map when the active API stops returning the order.
- Compact legend and accessible status description.
- Unit/component/integration tests and desktop/mobile smoke checks.

### Excluded
- Backend migrations, new database fields, new endpoints or order status changes.
- New archival logic; this belongs to 017A.
- Changes to Management → Orders Active / All filtering.
- Changes to address generation, hub assignment, flight paths or nearest-hub return (017C).
- Exception event handling and detailed failure marker design (future feature).
- Large map redesign or new map library.

## 6. Technical approach — validate during Initialize

1. Inspect current delivery marker component/layer, Mapbox rendering, status enums, order selection, legend and 017A active-orders flow.
2. Build an explicit mapping from actual order statuses to semantic marker states (`pending`, `in_progress`, `delivered`, `other`). Keep styling separate from status mapping.
3. Apply the style to the existing diamond marker, preserving its position, hit area, z-order and click behavior.
4. Ensure a delivered order renders green while it is still present in the active response. After 120 seconds, 017A removes it; do not calculate expiry independently.
5. Update any existing legend/tooltip and tests. Keep the implementation frontend-only unless the audit reveals a genuine missing field.

**Dependency gate:** 017A must be committed and migration 0009 applied to the local development database before validating real delivered-marker expiry. If 017A is not yet finalized, complete it first rather than reimplementing its lifecycle inside 017B.

## 7. Acceptance criteria

- [x] Pending destination displays a gray diamond. (Unit and component tests; not seen in a browser.)
- [x] Assigned/in-progress destination displays a blue diamond. (`OUT_FOR_DELIVERY` only; an order with an assigned mission is still `READY_FOR_PICKUP` and stays gray until takeoff. Not seen in a browser.)
- [x] A newly delivered destination turns green without a page reload. (The same marker element is recoloured in place; component-tested, not seen in a browser.)
- [ ] The green diamond stays visible during the 120-second grace period and disappears on the next poll at/after expiry. (The backend window is tested at 0, 119 and 120 s over HTTP and marker removal is component-tested; the full 120 s sequence was not observed live.)
- [x] Refreshing the app does not resurrect previously expired delivered markers. (The server decides; repeated requests use the stored delivery time.)
- [x] The order remains accessible in Management → Orders → All after its marker disappears. (Feature 017A; an HTTP test shows the full list and the order detail keep it.)
- [x] Other active markers remain visible and interactive during updates.
- [x] Clicking a marker continues to open the correct order details.
- [x] Status is conveyed by text/accessibility metadata as well as color.
- [x] Hubs, drones and flight paths retain their existing appearance and behavior. (No hub, drone or flight code changed; not compared visually.)
- [x] No extra API calls, dependencies, backend changes or client-side expiry timers are introduced. (For 017B itself; the related 017A backend fix is described in section 12.)

## 8. Test plan

**Unit:** Every actual order status maps to the intended semantic marker state and label; unknown statuses use a safe fallback.

**Component/integration:** Marker changes from gray/blue to green on a polled status update; an order omitted from the next active response loses its marker; selection clears safely; unrelated markers remain; legend/accessible text reflect state.

**Browser smoke:** At desktop and narrow widths, observe a real or browser-injected order transition from pending → in progress → delivered → expired; verify no duplicate diamonds, console errors or broken clicks. For the real expiry test, use the 017A backend timestamp and wait through the 120-second window. Verify that expired orders remain in Management → Orders → All.

**Quality:** Frontend lint, typecheck, format check, unit tests and production build. Report tests not run.

## 9. Risks and edge cases

- **Status mismatch:** Actual order enum values may not correspond one-to-one with the three visual groups; document explicit mapping after audit.
- **Existing 017A filtering:** If the backend migration or active endpoint is not operational, map disappearance cannot be validated; fix 017A first.
- **Map style contrast:** Colors can be hard to see over streets or satellite tiles; use a subtle outline and test at multiple zoom levels.
- **Selected disappearing marker:** Avoid stale references and selection errors when the active order is filtered out.
- **Legacy delivered records:** Those without `delivered_at` should already be excluded by 017A; do not add special map-only behavior.

## 10. Definition of done

Feature is implemented, tested, visually reviewed, documented and committed only after explicit approval. Follow the existing SkyFleet workflow: **Initialize (audit/plan, no edits) → approval → Start Implementation (no commit) → live review → Finish (docs/commit)**.

## 11. Next feature

**017C — Natural Delivery Locations & Nearest-Hub Return:** remove visibly symmetric destination patterns and evaluate routing to the nearest reachable hub after delivery. This is intentionally separate because it affects simulation/worker logic.

## 12. Implementation notes (verified)

**What was built (frontend only)**

- `features/map/orderMarkerState.ts`, a pure helper: `CREATED`, `AWAITING_HANDOVER` and `READY_FOR_PICKUP` are *Waiting* (gray); `OUT_FOR_DELIVERY` is *In delivery* (blue); `DELIVERED` is *Delivered* (green); any unknown status is a neutral *Other*. Only the order status decides.
- A new design token `--color-status-active` (`#3b82f6`); gray and green reuse `status-neutral` and `status-ok`.
- The marker's accessible name now includes the state, for example `Order ORD-007 destination, Ready for pickup (Waiting), 1.5 kg`. A selected marker keeps its state colour and adds a ring.
- `MapView` reconciles order markers by id: a status change recolours the existing element in place (focus and click handler survive), a new order adds one marker, an order that leaves the active list removes only its own marker, and an edited destination moves its marker.
- `OrderMarkerLegend`: a compact legend at the bottom-left of the map, hidden on narrow screens while a details panel is open.
- No new requests, timers or dependencies.

**A 017A defect found while testing 017B (backend)**

- Symptom: the diamond turned blue, then vanished 1 to 2 seconds after delivery instead of turning green.
- Root cause: the simulation worker processes were still running pre-017A code (the worker has no auto-reload), so they set `DELIVERED` without writing `orders.delivered_at`, and the active filter hides a `DELIVERED` order that has no delivery time.
- Fixes: the engine now stamps `order.delivered_at` with the real UTC time of the transition (see the correction in the 017A spec), and `GET /api/orders?active=true` takes its "now" from `clock.utcnow()`. The development data was repaired twice, with the owner's approval, by a one-off backfill from the flights (44 and then 10 orders); nothing was deleted and no migration was needed.

**Verification**

- Backend: 484 tests passed (28 PostgreSQL-marked tests deselected), ruff and mypy clean. New tests cover the engine timestamp, a late worker, the 0 / 119 / 120 / 121 s boundaries over HTTP, repeated requests not extending the window, and history staying listed.
- Frontend: lint, typecheck and Prettier clean, 609 unit tests passed, production build succeeded.
- Live data: six deliveries recorded at 12:51 UTC all have `delivered_at`, set a fraction of a second after the flight's scheduled time, and no `DELIVERED` order has a null time.

**Not verified / known limitations**

- The full blue → green → disappears-after-120-s sequence was not observed in a browser by the implementer.
- Legend placement (desktop and narrow) and diamond contrast over the map were not checked visually. Real Mapbox rendering is covered only through a fake map in tests.
- No QA or code-review agent was run.
- A worker started at 00:44 local, running old code, was still running at the last check. Workers must be restarted after backend code changes; a README note about this was not written.

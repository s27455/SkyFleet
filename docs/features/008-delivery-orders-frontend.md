# Feature 008 — Delivery Orders Frontend Integration

**Status:** Implemented and approved by the operator; manual browser acceptance **NOT VERIFIED** (see section "Implementation and verification")  
**Area:** Frontend (React + TypeScript + Tailwind + Mapbox GL JS)  
**Depends on:** Feature 007 — Delivery Orders Backend  
**Goal:** Let the fleet operator browse real delivery orders from FastAPI and see their destinations on the existing Tricity map.

## Context

SkyFleet currently displays Hubs and drones from the backend. Feature 007 introduced delivery orders in PostgreSQL, exposed through `GET /api/orders` and `GET /api/orders/{id}`. This feature integrates those existing endpoints into the operator UI. Backend remains the source of truth.

## User story

As a fleet operator, I want to inspect pending delivery orders, see their destinations on the map, and understand which Hub each order originates from, so that I can prepare for mission assignment in a later feature.

## In scope

1. **Typed API integration**
   - Reuse the existing API client, `VITE_API_BASE_URL`, error conventions and request-cancellation patterns.
   - Fetch `GET /api/orders` using the *actual* Feature 007 response schema. Inspect backend Pydantic schemas before defining frontend types; do not invent fields.
   - Validate and map API data consistently with the Hubs and Drones integrations. Malformed responses must produce a clear error state rather than silently dropping orders.
   - No mock-data fallback at runtime.
2. **Orders list**
   - Add a compact, accessible operator-facing orders list showing at least order ID, status, package weight, originating Hub and destination information available from the API.
   - Support selecting an order; provide a clear selected state and a way to close its details.
   - Provide status filtering only if it can be implemented simply using the existing response fields, without changing backend API behavior. Default to showing all orders.
3. **Order details**
   - Show all relevant server-provided details, including destination address/coordinates and timestamps if present.
   - Resolve originating Hub names from the already loaded Hub data when available; handle missing Hub data gracefully.
   - Do not imply that a drone or mission is assigned unless the backend actually provides that information.
4. **Map integration**
   - Render small, distinguishable destination markers at the actual order coordinates, without modifying stored locations.
   - Selecting an order in the list highlights its destination marker; selecting a destination marker opens the corresponding order details.
   - Preserve Hub markers, Hub drone-count badges, flying drone markers, map navigation, Mapbox attribution, and existing selection/accessibility behavior.
   - Plan a simple, accessible treatment for multiple orders at the same or very close coordinates; do not silently hide them or falsify their positions.
5. **Loading and failure states**
   - Non-blocking loading, empty, error and Retry states, consistent with the existing frontend conventions.
   - If orders fail to load, the map and Hub/drone UI remain usable; no stale order markers are displayed as current data.
   - Handle abort/unmount and retry races.
6. **Tests and documentation**
   - API mapping/validation tests, loading/empty/error/retry tests, list/detail interactions, map marker selection and accessibility tests.
   - Update README instructions only where necessary. Do not access protected `.env` files.

## Out of scope

- Creating, editing or deleting orders; backend or database schema changes.
- Assigning drones, mission planning, route computation or ETA estimates.
- Flight simulation, animation, live order polling, WebSockets or AI decisions.
- New frontend dependencies without explicit approval.
- Changes to drone/Hubs business rules.

## UX principles

- Maintain the current dark operational dashboard aesthetic; avoid covering the map with a large permanent panel.
- Keep destination markers visually subordinate to Hubs and active drones, and distinguish them by icon/shape rather than color alone.
- Ensure usable keyboard navigation (Tab, Enter/Space where applicable, Escape), visible focus and readable labels.
- At approximately 375 px viewport width, preserve map controls and Mapbox attribution; panels and lists must be scrollable and usable.
- Do not present seeded sample orders as live commercial deliveries; use accurate neutral wording.

## Acceptance criteria

1. With the existing backend and seeded database running, the frontend loads the 10 sample orders from `GET /api/orders` without mock fallback.
2. The orders list displays API-derived information and can be filtered by status if that optional filter is implemented.
3. Selecting an order opens its details and identifies/highlights its destination on the map; selecting a marker opens the same order.
4. Existing Hub and drone map interactions still work; only one details context is active at a time.
5. Loading, empty, invalid-payload, network-error and Retry states behave predictably, without crashes or stale order markers.
6. Markers are keyboard accessible; the mobile layout preserves attribution and controls.
7. Frontend lint, typecheck, format check, tests and production build pass.
8. `qa-tester` and `code-reviewer` subagents are invoked and their findings reported; any unresolved issues are documented.
9. No backend modifications, commits or pushes without explicit approval.

## Planning decisions for Claude Code (ask before implementation)

- **Orders UI placement:** propose the smallest coherent layout (e.g., collapsible sidebar/drawer) that works on desktop and mobile without disrupting existing Hub/drone panels.
- **Dense/overlapping destinations:** propose a deterministic and accessible selection strategy, using true coordinates.
- **Shared data-fetching abstractions:** reuse existing hooks/components where sensible; avoid an unnecessary refactor.
- **Schema fidelity:** confirm the exact order status values and response fields against the implemented Feature 007 backend; do not assume names from this specification.

## Verification workflow

1. Review the actual backend contract and current frontend architecture.
2. Present an implementation plan with the decisions above, then **stop for user approval**.
3. After approval, implement in the existing frontend conventions.
4. Run frontend checks and both review subagents.
5. Report browser-only checks as **NOT VERIFIED** unless actually tested in a real browser.
6. After user acceptance, run `/feature-finalization` to update this spec and `context/progress-tracker.md`; inspect Git changes but do not commit/push.

## Known project constraints

- PostgreSQL 17 is in Docker Compose on host port `55432`; FastAPI runs separately on port `8000`; Vite usually runs on `5173`.
- On this machine `localhost:8000` may resolve to an unrelated IPv6 listener. Use the configured `VITE_API_BASE_URL` and do not inspect or overwrite protected environment files.
- Feature 007's sample orders are development fixtures; their presence depends on migrations and seed having run.

## Implementation and verification (recorded at finalization)

### Decisions applied (approved with the plan)

1. **Placement:** a collapsible "Orders (N)" list in the existing top-right column, closed by default. The order detail panel reuses the shared left/bottom panel slot (`DETAIL_PANEL_CLASS`). On narrow screens the list is hidden (kept mounted, so its open state survives) while any detail panel is open, so list and panel never cover most of a phone-sized map.
2. **Overlapping destinations:** every order stays reachable through the list. Markers at exactly the same coordinates are spread on a small screen-only ring (the panel states this and shows the real position). Nearby but different points are not spread (documented limitation).
3. **No status filter** (all seeded orders share one status).
4. **Strict status validation** (`CREATED`, `AWAITING_HANDOVER`, `READY_FOR_PICKUP`; one unknown status rejects the whole list) and timestamps shown in UTC with an explicit label. Timestamps without a time-zone designator are rejected, so a naive value is never shown as UTC.
5. **Minimal shared refactor:** the ring-offset math is a generic `computeRingOffsets` in `droneMarkers.ts`; `computeDroneOffsets` remains a thin wrapper with unchanged behavior.

### Delivered (frontend only; no backend change, no new dependency)

- `types/order.ts`, `api/orders.ts` (validation against the Feature 007 `OrderResponse`: id, origin Hub, non-blank address, coordinate ranges, positive weight, known status, parseable zoned timestamps, unique ids), `features/orders/{useOrders,orderStatus,OrdersList,OrderDetailPanel}`, `features/map/orderMarkers.ts`.
- `App.tsx`: third resource with its own banner and Retry; the `Selection` union gains `order`, so only one Hub, drone or order panel is open at a time.
- `MapView.tsx`: small diamond destination markers (24 px target, rotation on an inner span so Mapbox's marker transform is untouched), stacked below Hubs and drones, selected cue is a ring (not colour alone), selection restyled in place so focus is kept.
- Order panel: status, weight, origin Hub name (id if Hubs are unavailable), destination, stored position, created/updated (UTC), a simulation-data note. No drone assignment is shown.
- README: Feature 008 note.

### Verification

| Check | Result |
|---|---|
| `npm run lint`, `typecheck`, `format:check`, `build` | Passed (re-run at finalization) |
| `npm run test` (Vitest + RTL) | Passed: 191 tests in 13 files (138 before this feature) |
| `qa-tester` | Pass with gaps; no critical or high findings |
| `code-reviewer` | One Medium finding (list and panel overlap on short phones): fixed by hiding the list on narrow screens while a panel is open. Dangling `aria-controls` and naive timestamps: fixed. Other low findings below |
| Manual browser acceptance (diamond look, real marker highlight, list and panel at about 375 px with the Mapbox attribution visible, keyboard Tab/Enter/Escape, loading against the live seeded backend) | **NOT VERIFIED** (no Mapbox token access in the session); the operator must check it |

Acceptance criteria 1 to 5, 7 and 9: covered by automated tests or checks as described above (criterion 1 at unit level against the real response shape, not against a running backend). Criterion 6: code and unit level only; the mobile layout and real keyboard behavior are part of the unverified browser check. Criterion 8: both subagents were invoked and reported.

### Known limitations and follow-ups

- The ring spread groups only exactly equal coordinates; nearby destinations overlap visually, but the list reaches every order.
- If the backend adds an order status the frontend does not know, the whole list is rejected as invalid until the frontend is updated.
- Weights are shown as the raw number the backend sends.
- Selecting from the list does not pan the map to the marker (same as Hubs and drones).
- `MapView.tsx` now contains three near-identical marker effect blocks (Hubs, drones, orders); a fourth entity should trigger extracting a small hook.
- Test gaps: no standalone `OrdersList` test (covered through `App`), no orders-specific stale-retry race test (the generic hook is tested), and nothing checks that Tailwind generates `z-5`.
- No polling: reload the page to re-read the snapshot.

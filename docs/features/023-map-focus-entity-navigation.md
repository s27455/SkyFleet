# Feature 023 — Map Focus & Entity Navigation

**Project:** SkyFleet  
**Status:** Implemented and verified (2026-11-15): automated checks and the owner's browser QA (the individual steps were not recorded). Not committed.  
**Priority:** Final UI/UX polish before AI Copilot  
**Scope:** Frontend-first; no database or API changes unless justified by investigation

## 1. Problem

The operator can select an order, drone or hub from dashboard lists and inspect its details, but must manually search the map to locate the corresponding object. This is slow and frustrating when the fleet and order markers are dense.

## 2. Goal

Selecting an entity from its list should take the map camera to the relevant real-world location and clearly identify the selected marker, without disrupting the current detail view or normal map interactions.

## 3. Expected behavior

| Entity | Focus target | Notes |
|---|---|---|
| Drone | Latest known current drone coordinates | One-time camera move; do not continuously track a moving drone. |
| Hub | Hub coordinates | Highlight selected hub marker. |
| Order | Delivery destination coordinates | Focus the delivery point even if the order has an assigned drone or active flight. |

- Trigger focus when the operator explicitly selects/clicks an entity in the corresponding list. Preserve existing selection and details behavior.
- Animate camera smoothly using the existing Mapbox integration (`flyTo`/`easeTo` or established equivalent). Use a useful zoom that makes the target identifiable without excessive zoom or disorienting movement.
- Visually distinguish the target marker, ideally reusing existing selected-marker styling, popups or focus behavior rather than adding a second competing selection model.
- Keep the details panel open; do not switch to an unrelated page or clear current filters.
- On compact/mobile layouts, ensure the map becomes visible and the selected object can be seen, without breaking panel navigation.
- Focus is a one-time action. Following the focus, the operator can pan, zoom or select another object normally. Polling/position updates must not repeatedly reset the camera.
- Repeated deliberate clicks on the same list item should be able to refocus the map, even when selection state is unchanged.
- Rapid selections should resolve to the latest user intent; avoid stale animations moving the camera back to an earlier target.

## 4. Invalid and historical data

- Never focus on `(0, 0)`, `NaN`, non-finite or out-of-bounds coordinates.
- If the entity lacks a usable location, keep the current camera position and give a small, accessible indication that its location is unavailable. Do not crash.
- Use the destination coordinates already stored for an order; do not geocode addresses at click time.
- Historical orders may contain synthetic or inaccurate coordinates. Do not silently rewrite data or claim that historical locations are verified. Preserve existing map rendering and filters.
- If a selected marker is hidden by a filter or clustering, inspect existing behavior and propose the least disruptive way to make the target identifiable. Do not silently change global filters without a documented decision.

## 5. UX and accessibility

- List items should remain keyboard-accessible; Enter/Space should trigger the same focus when appropriate.
- Provide a clear accessible name for any explicit “Locate on map” action.
- Respect `prefers-reduced-motion` where supported; use an immediate or reduced camera transition.
- Avoid changing the operator's zoom unexpectedly on every data refresh.
- Avoid overlaying the target under side panels; use map padding/offset or the existing responsive layout strategy.
- Preserve hover behavior, row actions, list scrolling and existing selection state.

## 6. Technical design principles

- First inspect the current React selection flow, map component lifecycle, marker rendering, map refs, panel state and responsive behavior.
- Prefer a single small, explicit focus command or request with a unique sequence/token so repeated selection of the same entity works.
- Reuse existing entity coordinates and map selection mechanisms. Avoid duplicating map instances or introducing global event buses unnecessarily.
- Ensure map readiness and lifecycle safety: requests before the map is ready must be handled intentionally; no callbacks should fire against an unmounted map.
- Avoid backend, migrations, persistence, paid services and new dependencies unless a concrete blocker is demonstrated.
- No continuous follow mode, route planning changes, dispatch changes or order status changes.

## 7. Out of scope

- Reworking map styles, marker clustering, geocoding or historical destination data.
- New tracking/follow-camera mode.
- Changing drone routing, hub assignment, incident behavior or mission/order lifecycle.
- AI Copilot, refactoring unrelated modules, deployment.

## 8. Acceptance criteria

1. Clicking any drone in the drone list moves the camera to its current coordinates and highlights it.
2. Clicking a hub moves the camera to that hub and highlights it.
3. Clicking an order moves the camera to its delivery destination, not the assigned drone.
4. Details stay visible and list selection continues to work.
5. Clicking the same row twice can refocus after the operator pans away.
6. Selecting two entities quickly ends with the camera on the latest selected entity.
7. Normal live updates do not steal camera control after focus.
8. Invalid/missing coordinates do not move the map or crash the UI.
9. Keyboard access, reduced motion and narrow-screen layouts work.
10. Existing map markers, filters, popups, list actions and incident overlays do not regress.
11. Type checks, lint, relevant tests and production build pass.

**Result (2026-11-15):** all eleven criteria are met. 1-3 and 5-8 and 11 are covered by automated tests (`focusTarget`, `mapCamera`, `FocusNotice`, `MapView` and `App` tests, type checks, lint and the production build); 4 and 10 by the unchanged existing suites; 9 (keyboard access, reduced motion, narrow screens) by automated tests of the buttons, the reduced-motion path and the phone offset, and the layout by the owner's browser QA.

## 9. Suggested tests

- Unit tests for focus-target resolution for drone, hub and order.
- Component/integration tests for list-click focus, repeated click, stale focus cancellation and no camera movement on polling.
- Map camera adapter tests with a mocked Mapbox map for animation, padding, readiness, invalid coordinates and reduced motion.
- Regression tests for selected details, marker highlighting and list keyboard interactions.
- Browser QA on desktop and narrow viewport: drone in flight, idle drone at hub, hub, new order, historical order and missing coordinates.

## 10. Delivery gates

### Gate A — Read-only investigation

Inspect relevant code and report: current list click handlers, selection state, Mapbox camera API, marker selection, responsive layout, exact files, smallest implementation approach, risks and tests. **Do not modify code or database, restart services, install dependencies, commit or push.** Wait for approval.

### Gate B — Implementation and automated tests

Implement the approved frontend behavior with focused tests. Avoid unrelated refactors. Run frontend checks and build. Do not restart services or commit/push without approval. Report changes and known gaps.

### Gate C — Browser QA

Operator verifies focusing and highlighting for each entity, repeat clicks, moving drones, narrow layout and regressions. Fix only demonstrated issues.

### Gate D — Finalization

Update feature documentation and project tracker, review complete diff, run final checks and commit after explicit approval. No push unless separately authorized.

## 11. Open questions for Gate A

- Does SkyFleet already have a map focus/fly-to mechanism that can be reused?
- Which list actions currently select versus navigate to details, and can their behavior be preserved?
- Are order destinations rendered individually, clustered or fan-out offset on the map? Which coordinate should camera focus use?
- Does the current mobile UI require switching tabs/panels to expose the map?
- How is selection highlight currently represented, and does it survive polling?

**Definition of done:** The operator can locate any selected drone, hub or order on the map immediately, with a predictable one-time camera transition and no disruption to the rest of the dashboard.

## 12. Approved decisions and Gate B record (2026-11-15)

### Approved at Gate A

- Scope is limited to the three Operations lists (Drones, Hubs, Orders). The Management tables, the docked-drone buttons in the Hub details and the marker clicks keep their plain selection and never move the camera. No new detail-panel buttons.
- A docked drone is focused on its current coordinates (its Hub); no separate marker is added. The existing selection state and marker highlighting are reused; there is no second selection system.
- Minimum focus zoom 15; a closer zoom of the operator is kept.
- One camera move per list click (also when the same row is clicked again); polling and re-renders never move the camera; the latest click wins, also when the map is not ready yet.
- Reduced motion, a phone offset and unusable coordinates are handled. A historical order is focused on its stored destination without claiming it is verified.

### Implementation (frontend only)

- `features/map/focusTarget.ts`: `FocusRequest` (kind, id, position and a `seq` unique per click), `isUsableCoordinate` (two finite numbers in range, not `(0, 0)`) and `resolveFocusTarget` (a drone's latest known coordinates, a Hub's coordinates, an order's stored destination, never its drone and never a geocoded address).
- `features/map/mapCamera.ts`: `focusCamera` calls `flyTo` once with zoom `max(current, 15)` and a 900 ms duration; with reduced motion the duration is 0 and the move is `essential`, so it is immediate. On a phone (below the `sm` breakpoint) a stateless `offset` of -25 % of the map height shows the target above the bottom panel; on a wide screen the side panels flank the map evenly, so there is no offset (an `offset` rather than `padding`, because padding would stay in the map).
- `features/map/MapView.tsx`: an optional `focusRequest` prop and one effect keyed on `[focusRequest, status, reducedMotion]`. A ref remembers the last `seq` that was carried out, so a command moves the camera exactly once; a command that arrives before the map is ready waits, only the latest is kept, and it is carried out when the map is ready; an older `seq` is ignored.
- `App.tsx`: `focusHub`, `focusDrone` and `focusOrder` call the existing select function and then set a new request (a counter gives each click a new `seq`); only the three Operations lists get them. An entity that is unknown or has no usable location sets no request (the camera stays) and shows a small notice.
- `features/map/FocusNotice.tsx`: the notice ("The location of <id> is not available."), announced politely (`role="status"`), dismissible, and gone after 5 s; a new notice starts its own timer.
- Not changed: the three list components, the detail panels, the Management tables, the markers and their highlighting, the backend.

### Verification (2026-11-15)

- `tsc -b`, oxlint and prettier clean; production build succeeded; vitest 929 passed (69 files) in three consecutive full runs. In one earlier full run an existing test of Feature 022 (`LiveDataNotices.acknowledge.test.tsx`, "keeps the alert and shows a recoverable error when the request fails") failed once and then passed in six isolated runs and four full runs; it does not involve this feature and looks like a timing flake under load. It was not changed.
- New tests: `focusTarget.test.ts` (valid, invalid, (0, 0), NaN, out-of-range, unknown entity, drone, docked drone, Hub, order destination, unchanged historical coordinates), `mapCamera.test.ts` (zoom rule, phone offset, no negative-zero offset, reduced motion, breakpoint), `FocusNotice.test.tsx`, 11 `MapView` tests (waits for readiness, only the latest request before ready, once per request, no move on re-render, data refresh or selection change, repeated click, rapid requests and a late stale one, zoom, phone offset, reduced motion, closing before ready) and 10 `App` tests (a drone, a Hub and an order, with details and selection kept; repeated click; two quick clicks; no new command on an unrelated re-render; marker clicks and the Management table do not move the camera; an unusable location gives a notice and no move, then recovers; keyboard-operable rows).
- A mutation check (removing the sequence guard) makes two of the `MapView` tests fail.

### Limits

- A docked drone has no marker of its own, so the camera shows its Hub (already highlighted when selected) and the drone's details stay open.
- The camera target of an in-flight drone is its latest polled position; the animated marker can be a few metres ahead (a few pixels at zoom 15). There is no follow mode.
- Older orders (the seed `ORD-001` to `ORD-011` and the legacy `TC-` orders) keep their approximate stored coordinates, so focusing them goes to that stored point.
- The phone offset (-25 %) and the 900 ms duration are constants chosen without a device-specific tuning; layout and animation cannot be verified automatically (jsdom has no layout engine or WebGL). The owner confirmed the browser QA passed.
- A "Locate on map" button in the detail panels was deliberately not added; the list row is the action.

## 13. Final verification (2026-11-15)

- Frontend only: no backend, API, migration or dependency change.
- `tsc -b`, oxlint and prettier clean; vitest 929 passed (69 files); production build succeeded; about 59 new tests; a mutation check (removing the sequence guard) fails two `MapView` tests.
- One earlier full run showed a one-off failure of an unrelated Feature 022 test (`LiveDataNotices.acknowledge.test.tsx`, "keeps the alert and shows a recoverable error when the request fails"); it passed in the following runs, did not involve this feature and was not changed. It looks like a timing flake under load.
- Owner QA: the owner confirmed the browser QA (Gate C) passed; the individual steps were not recorded.

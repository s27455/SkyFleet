# Feature 016B — Drone Inspector Navigation & Layout

## Status
Implemented and verified by automated checks and a scripted real-browser smoke test; approved as complete by the user at Finish; not committed. No QA or code-review agent run. The smoke test used headless Chrome with software WebGL against the running dev server and backend; flying-drone data was injected into API responses inside the browser only (no database or backend change). Real GPU rendering, touch gestures, wheel-zoom gating in a browser, and the reduced-motion and exit animations were not observed by the implementer.

### Implementation summary
- Frontend only; no backend, database or API change. The "drone map popup" of the spec is the existing `DroneDetailPanel` side panel; it gained an optional `onInspect` prop and an **Inspect Drone** button directly below the Status, Battery, Hub and Position rows, plus a `closeOnEscape` prop (default true). Nothing else in the panel changed.
- `features/drones/DroneInspector.tsx`: a `role="dialog"` modal overlay above the map (the map stays mounted) with the lazily loaded `Drone3DViewer` (captioned as an illustrative model, not drawn from drone data) and sections Operational, Flight (reusing `FlightSection`), Mission, Payload (the weight and destination of the order of the drone's flight or open mission), Model specification, and an empty, labelled **Diagnostics** area reserved for 016C (no values). Enter/exit animation of 180/150 ms, disabled for reduced motion. Escape and a Close button close it; Tab is kept inside (`useDialogFocus.ts`), and focus returns to the Inspect Drone button.
- `features/drones/inspectorData.ts`: resolves flight, mission and payload from data `App` already polls (no new fetches) and distinguishes loading, failed and "not found" from a confirmed "none"; an unreadable resource is shown as unavailable, never as "no mission". A mission known only from its flight shows "—" for return Hub and route length.
- `App.tsx`: the inspected drone id is separate from the selection, so closing never changes the selected drone; the header is `inert` while the inspector is open; the inspector closes if its drone leaves the data. `Drone3DViewer` and `DroneCanvas` are memoized and use constant camera props so a re-render from polling does not reset the camera or remount the viewer.
- API model: `DroneModel` gained `airframeType`, `maxSpeedKmh`, `chargeTo80Minutes`, `maxWindMps`, `emptyWeightKg`, all already sent by `GET /api/drones`; they are validated strictly in `api/drones.ts`, so a response missing any of them is rejected.
- **Tests:** 35 new tests (inspector data, inspector component, panel button and Escape handling, App navigation, selection retention, unavailable data, polling without remount, and the new API fields). Checks passed after the last code change: `oxlint`, `tsc -b`, `prettier --check`, `vitest run` (451 tests), `vite build`.
- **Bundle:** main chunk 2,169.67 kB to 2,185.57 kB (616.98 kB gzip); the 3D chunk (`DroneCanvas`, 1,004.59 kB, 271.40 kB gzip) loads only when an inspector is first opened.
- **Smoke test (desktop 1440 px and narrow 390 px, no console errors):** idle drone DRN-001 and a flying DRN-002 (injected data); lazy 3D chunk loads; focus enters the dialog and the header is inert; drag, zoom buttons and arrow keys move the camera and it stays put across several polls; Escape closes only the inspector (panel and selection kept, focus restored), a second Escape closes the panel.

### Known issues and follow-ups
- The seeded model SF-1 is a six-rotor `hexacopter` in the backend, while the 016A model has four motors. The inspector shows the real airframe value and labels the 3D model illustrative; resolving the mismatch (model or seed) is open.
- At 390 px the existing app header clips the backend status and causes a horizontal scrollbar; this predates 016B and was not changed.
- A touch drag over the viewer orbits the model and does not scroll the page.

## Goal
Add an **Inspect Drone** button to the existing drone map popup, preserving its current appearance and functionality. Open a polished technical-inspector overlay containing the 016A 3D model and actual drone operational data.

## Scope
- Audit current map popup and drone selection state; preserve existing popup details.
- Add a clearly labeled Inspect Drone action beneath current popup information.
- Open a large, responsive overlay with a restrained enter/exit animation, close button and Escape support; restore map/selected-drone context on close.
- Display Drone3DViewer centrally; organize real existing API data around it (ID, status, battery, hub, position, mission, payload, etc. **only where available**). Show unavailable values explicitly rather than inventing them.
- Keep live data updates consistent with existing frontend polling and avoid duplicate fetches.
- Handle focus, keyboard, narrow screens, and scroll lock according to existing app patterns.
- Add tests for navigation, state retention, and data rendering.

## Out of scope
No new backend fields, simulated diagnostics, interactive component selection, or redesign of the existing popup.

## Acceptance criteria
Popup remains unchanged except for the new action; inspector opens and closes reliably; selection context survives; only actual available backend data is shown as real; checks pass.

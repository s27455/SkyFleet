# Feature 016A — Procedural Drone 3D Model

## Status
Implemented and verified by automated checks; approved as complete by the user at Finish; not committed. No QA or code-review agent run. The visuals were checked by the implementer only through headless-Chrome screenshots (software WebGL, 1100 px and 390 px wide); propeller animation, drag/wheel orbit and real-GPU behavior were not observed by the implementer.

### Implementation summary
- Frontend only, in `frontend/src/features/drone3d/`; no backend, database, API, map or popup change. `src/main.tsx` only mounts the dev preview.
- **Dependencies (approved, pinned exactly):** `three@0.187.0`, `@react-three/fiber@9.8.2`, `@react-three/drei@10.7.9`, dev `@types/three@0.187.0`. See `docs/decisions/0003-threejs-drone-viewer.md`.
- **`Drone3DViewer`** (`index.ts`): props `animate`, `onPartSelect`, `className`. Checks WebGL before loading the lazily imported `DroneCanvas` chunk; shows a text fallback without WebGL, on a render error or on context loss. Orbit with damping, bounded zoom distance and tilt, no pan; arrow keys, `+`/`-`, `Home`/`0`, and Zoom in / Zoom out / Reset view buttons; wheel zoom only while the viewer has focus; the canvas captures touch drags.
- **Rendering cost:** animation frames (`frameloop="always"`) run only while `animate` is true, reduced motion is not requested, the viewer is on screen and the tab is visible; otherwise it renders on demand. Geometries and materials are created once and disposed on unmount.
- **Model** (`DroneModel.tsx`, `droneLayout.ts`, `droneMaterials.ts`): lofted fuselage, four arms, named groups `motor-fl`, `motor-fr`, `motor-rl`, `motor-rr` (each with its own `propeller-*` group, counter-rotating pairs), `battery`, `cargo-bay` (frame, glass panels, parcel), `landing-gear`, `fuselage`. Procedural environment lighting, no downloaded assets. `onPartSelect` reports clicks on these groups; no highlighting yet.
- **Dev-only preview:** `/?preview=drone3d` (`DronePreviewPage.tsx`, excluded from production builds), with animation and 360 px-width toggles.
- **Bundle:** the main production chunk is unchanged (2,169.67 kB, 612.37 kB gzip) because nothing in the app imports the viewer yet. Measured with a temporary build, the viewer adds a separate lazy chunk of about 1,008 kB minified (273 kB gzip) once imported.
- **Tests:** 16 new tests (part ids and motor layout, camera maths, viewer fallback, lazy load, reduced motion, wheel gating, keyboard handling, error fallback, part selection) with a mocked canvas, since jsdom has no WebGL. Checks passed after the last code change: `oxlint`, `tsc -b`, `prettier --check`, `vitest run` (416 tests), `vite build`.
- **Known:** a `THREE.Clock` deprecation warning from inside React Three Fiber appears in the console. Disposal on unmount, orbit gestures and keyboard focus behavior in a real browser are not covered by automated tests.

## Goal
Build a polished, reusable, frontend-only 3D quadcopter viewer for SkyFleet. This is the visual foundation for a later Drone Technical Inspector opened from the existing drone map popup.

## Context and future workflow
Keep the current drone popup intact. In 016B, add an **Inspect Drone** action to that popup which opens an animated, large technical inspector overlay and returns to the selected drone on close. In 016C, add coherent simulated telemetry alongside real API data. In 016D, enable component selection and polish interactions.

## Scope (016A only)
- Audit frontend framework, versions, dependencies, styling, existing map/popup, tests, and build constraints.
- Implement an original procedural quadcopter using React Three Fiber / Three.js (if compatible): sleek industrial styling, shaped central fuselage, four arms, distinct motor housings and propellers, landing gear, battery and cargo area, small purposeful details.
- Avoid blocky/Minecraft-like appearance, excessive CAD complexity, external downloaded assets and photorealism requirements.
- Provide reusable `Drone3DViewer` with orbit, constrained zoom, attractive lighting, subtle optional propeller animation, responsive sizing, cleanup, and reasonable performance.
- Model four motors and battery as separately identifiable named groups to support later inspection.
- Provide a minimal isolated preview/test harness consistent with repo conventions, without changing production map selection or existing drone popup.
- Ensure accessibility: readable fallback when WebGL unavailable, reduced-motion preference, sensible keyboard/focus behavior around viewer controls where feasible.
- Add appropriate tests and verify lint, types, tests, build.

## Out of scope
No backend, DB, worker, missions, API changes, simulated telemetry, inspector overlay, map popup button, or new dispatch behavior. Do not create live orders or toggle modes.

## Acceptance criteria
1. Reusable viewer renders a recognizable, visually polished quadcopter with four distinct motors and a visible cargo area.
2. User can orbit and zoom without losing the model; controls are bounded and do not interfere with the surrounding page.
3. Viewer fits typical desktop and narrow layouts; handles loading/error/WebGL fallback gracefully.
4. Animation is subtle and respects reduced-motion; no runaway render loops or leaked resources on unmount.
5. Component structure permits future motor/battery selection without rebuilding geometry.
6. Existing SkyFleet functionality remains unchanged; frontend checks pass.

## Delivery workflow
Initialize: audit and propose a concise plan; do not edit. Start Implementation only after approval; no commit. Live visual review; then Finish with documentation, tracker and scoped commit.

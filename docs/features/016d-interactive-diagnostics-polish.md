# Feature 016D — Interactive Diagnostics & Polish

## Status
Implemented and verified by automated checks and scripted real-browser smoke tests; approved as complete by the user at Finish; not committed. Frontend only (no backend, database or dependency change).

### Delivered
- Telemetry health drawn on the 3D model: amber (attention) and red (critical) rings and washes and status LEDs on motors M1–M4 and the battery, from the same `assessHealth` thresholds and the same shown readings as the panel; a cyan selection outline.
- Labels on the model, as real buttons (a keyboard route), stating a non-nominal level in words. They are plain DOM positioned by a projector inside the canvas (drei `Html` was tried and rejected: it logged React unmount errors and lost its click handlers). Motor labels sit outside the propellers, rear ones lifted, and chips are smaller on narrow containers.
- One shared selection (model part, label, telemetry list row, battery heading) with a synchronized details panel (`ComponentDetail`): readings, level in words, each check and its threshold, all marked as estimates. Clicking empty space or Clear selection clears it; a drag that orbits does not select; Escape still closes only the inspector; selection survives live refreshes and resets for another drone. Only M1–M4 and the battery are selectable.
- The dev preview (`/?preview=drone3d`) can force each part to nominal, attention or critical.
- Telemetry variation (requested during 016D): RPM, temperatures, power, current and link quality now vary smoothly and deterministically with flight progress, with per-motor waves (RPM 2–5% peak to peak), warm-up from the standby temperature and a small cool-down in the descent; the health thresholds are unchanged. A display-only easing of the shown temperatures (`useSmoothedReadings`, `requestAnimationFrame`, immediate with reduced motion) avoids jumps when a drone lands or takes off; health, component statuses and 3D highlights are computed from the shown readings.

### Verification
- Frontend: lint, typecheck, format check, production build clean; 583 unit tests passed (44 files) after the last code change. One App test (Escape closes the inspector and restores focus) failed once under parallel load and passed in three isolated runs and a second full run, so it is timing-sensitive, not a regression.
- Backend untouched; its 461 tests last passed before this feature (28 Postgres-marked tests deselected).
- Scripted headless-Chrome smoke tests (software WebGL, desktop 1440 px and narrow 390 px; flying, low-battery and charging drones injected in API responses in the browser only, the database untouched): selection from labels, list and the 3D parts themselves, clearing, drag not selecting, selection stable across polls, Escape, forced amber/red states, no console errors. A further run followed a flying drone for 40 s (about 20 polls) and then six identical polls of a frozen state: no jumps, identical readings, health and labels Nominal. After the final temperature slowdown only the desktop live-flight run was repeated.
- Bundle: main chunk 2,196.00 kB before 016D, 2,205.52 kB after; lazy 3D chunk 1,004.59 kB before, 1,007.01 kB after.
- No QA or code-review agent run.

### Known limitations
- Not observed: real GPU rendering, touch gestures, colours on the user's screen, a real Tab-key walk through the labels (labels were only confirmed focusable).
- Narrow label chips are about 28 px tall, below the 40 px used for list buttons; the list is the touch route.
- A motor above 70 °C is rare by design, so amber motors are reviewed through the preview page.
- Temperatures have no thermal history; the shown ones lag their targets by a few seconds because of the easing.
- At 390 px the existing app header still clips "Backend connected" (predates 016B).

## Goal
Complete a polished technical-inspection experience centered on the 3D drone.

## Priority (decided before 016D starts)
Motor and battery health must be visualized **directly on the 3D model**, so the model becomes the primary diagnostic interface rather than decoration above a table:
- telemetry-driven amber (attention) and red (critical) highlighting of motors M1–M4 and the battery, using the same thresholds as the simulated telemetry (`assessHealth`);
- component labels on the model;
- clickable parts, with the component list kept as an equivalent keyboard/text route;
- detail panels synchronized with the selected part (`MODEL_PART_FOR_COMPONENT` already maps `motor-1`..`motor-4` and `battery` to model parts).
Colour must never be the only cue: warnings stay stated in words, as in 016C.

## Scope
- Select motor M1–M4 and battery via 3D model and corresponding diagnostic list; synchronize selection, highlighting and detail panel.
- Present component-specific telemetry, status and meaningful warning explanations.
- Refine animations, materials, layout, loading states, mobile behavior, reduced motion, accessibility, and WebGL fallback.
- Verify performance and disposal of 3D resources; avoid excessive rendering when inspector is hidden.
- Add integration and regression tests and perform a live demo review.

## Out of scope
No backend sensor simulation or flight-safety control logic.

## Acceptance criteria
Selection works from 3D and text UI, diagnostics match selected component, keyboard/fallback routes remain usable, visuals are coherent and performance acceptable.

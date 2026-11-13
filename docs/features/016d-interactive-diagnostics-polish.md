# Feature 016D — Interactive Diagnostics & Polish

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

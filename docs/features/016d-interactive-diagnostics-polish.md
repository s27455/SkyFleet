# Feature 016D — Interactive Diagnostics & Polish

## Goal
Complete a polished technical-inspection experience centered on the 3D drone.

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

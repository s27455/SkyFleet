# Feature 016B — Drone Inspector Navigation & Layout

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

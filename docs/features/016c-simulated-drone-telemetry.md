# Feature 016C — Simulated Drone Telemetry

## Goal
Make the technical inspector useful as a fleet-technician proof of concept, showing coherent demonstrative component diagnostics alongside genuine operational data.

## Scope
- Add a frontend-only, deterministic telemetry derivation based on available drone state (e.g. status, battery, payload, stable drone ID). Avoid random jumps on polling or re-render.
- Provide motor M1–M4 temperature and RPM, battery temperature, estimated voltage/current/power, connectivity quality, and a small meaningful health summary. Show units and sensible nominal ranges.
- Reflect basic operating modes: idle, flying, charging, maintenance. Simulated values should be internally consistent (e.g. power approximately voltage × current), not presented as certified engineering measurements.
- Clearly distinguish simulated diagnostics from real backend data via an unobtrusive **Simulated telemetry** label and optional explanatory tooltip/text.
- Keep thresholds and values in pure, testable functions; do not persist simulated data.
- Add unit and UI tests for stable output, state transitions, ranges and warning derivation.

## Out of scope
No physics-grade telemetry, sensor integration, backend or database changes, or component clicking (016D).

## Acceptance criteria
Values are stable, plausible for a demo, status-sensitive, correctly labeled and tested; no impact on real mission logic.

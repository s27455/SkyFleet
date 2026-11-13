# Feature 016C — Simulated Drone Telemetry

## Status
Implemented and verified by automated checks; approved as complete by the user at Finish; not committed. Backend: 461 pytest passed (28 Postgres-marked tests deselected), ruff and mypy clean. Frontend: lint, typecheck, format check, 511 tests and production build passed. A scripted headless-Chrome smoke test (software WebGL; idle, in-flight, charging, maintenance and low-battery states injected in the browser only) passed on desktop and narrow widths before the quadcopter-only correction and was not repeated afterwards. Migration `0008` was applied to the local database and the live API returns `quadcopter`. No QA or code-review agent run. Not observed: real GPU rendering, touch input. Known limits: temperatures have no thermal history; voltage and current are not health-checked; the main bundle grew by about 10.5 kB.

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

## Scope correction (MVP: quadcopters only)
The SkyFleet MVP fleet is quadcopters only (motors M1–M4). The telemetry derives motor readings only for the `quadcopter` airframe; any other airframe gets no motor telemetry and an explicit note. The earlier six-rotor support was removed. The backend seed now creates SF-1 as a `quadcopter`, and Alembic migration `0008` (data only, guarded to the SF-1 row while it still holds `hexacopter`, reversible) updates an existing database. Drone ids, fleet size, flight parameters and missions are unchanged.

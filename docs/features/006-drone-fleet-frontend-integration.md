# Feature 006 — Drone Fleet Frontend Integration

**Project:** SkyFleet  
**Status:** Implemented — automated checks and QA/code-review passed; manual browser acceptance **NOT VERIFIED** (see section 10)  
**Phase:** Drone fleet visualization  
**Depends on:** Feature 001 (Mapbox map), Feature 002 (Hub markers and panel), Feature 004 (frontend–backend Hubs integration), Feature 005 (Drone Fleet Backend)

## 1. Goal

Display the existing fleet of 12 SkyFleet SF-1 Courier drones on the Tricity Mapbox map using real data from the FastAPI backend and PostgreSQL. Operators must be able to identify a drone, select it, and inspect its current backend-provided details without any simulated movement or mock-data fallback.

## 2. Context

- The React/TypeScript frontend already renders the Mapbox map and four Hubs from `GET /api/hubs`.
- Feature 005 added `DroneModel` and `Drone` persistence, migrations, seed data (12 drones; three assigned to each Hub), and read-only drone endpoints (`GET /api/drones` and `GET /api/drones/{id}`).
- The MVP currently has exactly one model, **SkyFleet SF-1 Courier**, with **3 kg maximum payload**, 20 km nominal total range, 12–14 km conservative operational mission distance, 45 km/h cruise speed, 30–35 minutes nominal flight time, and 20% battery reserve. These are simulation assumptions, not certified performance guarantees.
- The backend is the source of truth. The frontend must not synthesize drone positions, battery levels, statuses, or model specifications.

## 3. Scope

### In scope

1. Add a typed frontend API adapter for the existing drone list endpoint, reusing the project's existing API client and environment configuration.
2. Inspect the **actual Feature 005 response schemas** before implementing types or mapping. Use the real response fields and nested model shape; do not assume field names from this specification.
3. Validate/map responses sufficiently to prevent malformed data from crashing the UI or producing invalid Mapbox coordinates.
4. Fetch drones on initial page load, using the existing data-fetching conventions and request cancellation/retry patterns.
5. Render a visually distinct, accessible map marker for each drone at the **coordinates returned by the API**. Drone markers must be distinguishable from Hub markers without relying on color alone.
6. Allow clicking or keyboard-activating a drone marker to open a drone detail panel with the available backend-provided data: identifier, status, battery percentage, assigned Hub, model name and selected model capabilities, where present in the real API response.
7. Preserve the existing Hub markers and Hub detail interactions. Define predictable behavior when selecting a Hub versus a drone: only one detail panel/selection active at a time.
8. Provide non-blocking loading, empty, error and retry states for the drone request. Hub data and the map should remain usable when the drone API fails.
9. Ensure appropriate keyboard interaction, visible focus, accessible names, and reasonable desktop/mobile layout. Preserve Mapbox attribution visibility.
10. Add unit/component tests and update the frontend README with a short explanation of the fleet display and local run requirements.

### Out of scope

- Simulated or live drone movement, polling, WebSockets, animation or periodic refresh.
- Dispatching drones, changing status/battery/Hub, manual controls or other write operations.
- Delivery orders, routes, mission assignment, charging logic, geofencing or battery consumption algorithms.
- New drone models or backend fields/endpoints unless an actual integration blocker is discovered and explicitly approved.
- New UI or data-fetching libraries without explicit approval.
- Fabricated live telemetry or status labels.

## 4. UX requirements

### Map

- Four existing Hub markers continue to behave as before.
- Up to 12 seeded drone markers appear at the exact backend-provided `[longitude, latitude]` coordinates. If multiple drones share a location (for example, at a Hub), they must remain **discoverable and selectable**. The implementation may use a simple offset, spiderfy, clustering, or a nearby-drone list, but **must not misrepresent a visually offset coordinate as the actual drone location**. Choose the smallest maintainable approach and explain it in the plan before implementation.
- The map remains usable while drones load or fail to load.
- Markers and panels should not imply that stationary seeded drone positions are live telemetry.

### Drone details

- Display actual backend-provided values, with readable status labels and battery percentage.
- Display the assigned Hub's name if it is available from the existing data; otherwise use an honest ID/unknown state, without inventing data.
- Include model name and the 3 kg payload capacity if present in the nested model response.
- Clearly label the data as the **current backend snapshot**, not a real-time flight feed.
- Provide a consistent close/Escape/focus interaction based on the existing Hub panel pattern.

### Data states

- **Loading:** an unobtrusive status message; no mock drone markers.
- **Empty:** explain that the API returned no drones.
- **Error:** an accessible error message and Retry control; no mock fallback.
- **Retry:** re-request the drone endpoint and recover cleanly, avoiding stale/aborted results.
- An error in one resource (Hubs or drones) must not suppress successful data from the other.

## 5. Data and architecture

- Backend API contract is authoritative; inspect the existing Pydantic schemas and API tests before writing frontend interfaces.
- Reuse the established `VITE_API_BASE_URL` and frontend API client.
- Keep API validation/mapping separate from presentation components.
- Keep drone selection consistent with the existing Hub selection mechanism; avoid introducing a parallel conflicting panel state.
- Do not edit or read protected environment files such as `frontend/.env.local` or `backend/.env`.
- Prefer existing components and styles; no broad redesign of the map.

## 6. Acceptance criteria

1. With the seeded PostgreSQL database and running FastAPI backend, the frontend loads **12 drones** from `GET /api/drones` and displays them on the Mapbox map.
2. Every drone is discoverable/selectable even if several share the same coordinates.
3. Clicking a drone opens details corresponding to the selected API record, including its battery/status and SF-1 model information where exposed by the endpoint.
4. Selecting a Hub and then a drone (and vice versa) does not leave overlapping or stale detail panels.
5. Existing Hub map behavior, click, Enter, Escape, focus handling and mobile usability are preserved.
6. Loading, empty, error and retry states work without fallback to mock drones; a drone API failure does not break the Hub map.
7. Invalid payloads and invalid coordinates do not crash the app or produce bogus map markers.
8. No new backend migrations, drone updates, simulated motion or background polling are introduced.
9. Frontend lint, typecheck, tests, format check and build pass.
10. QA and code-review subagents are actually invoked, and their findings and limitations are reported.

**Revision before finalization (approved by the operator):** criteria 1 and 2 were changed from "12 individual drone markers" to the Hub-count design in section 10. Docked drones are shown as a count badge on their Hub and are reached through the Hub panel; only `IN_FLIGHT` drones (and any non-flying drone away from every Hub) get individual markers.

## 7. Verification plan

- API mapping tests: valid list, empty list, malformed list/records, invalid coordinates, nested model values and status/battery mapping based on the actual API schema.
- Component tests: markers and detail panel, multiple drones at one location, Hub↔drone selection, loading/error/retry, aborted requests and stale responses, keyboard/focus behavior.
- Regression tests for the existing Hub experience.
- Run all established frontend checks.
- Local smoke test against the running FastAPI/PostgreSQL stack. Verify the API count and rendered data; if a browser or Mapbox token is unavailable, mark the visual check **NOT VERIFIED** and ask the operator to check it manually.
- Manual browser acceptance: 12 discoverable drones, four Hubs, correct panel data, keyboard interaction, API failure/retry, and approximately 375 px mobile viewport with Mapbox attribution visible.

## 8. Risks and decisions to surface in planning

1. **Overlapping markers:** three seeded drones may be located at each Hub. The implementation must make all drones selectable without falsifying their coordinates. Propose a minimal UX solution and request approval if it changes the interaction model.
2. **Response contract:** use the real Feature 005 response schema rather than guessing whether coordinates, Hub name or model attributes are nested or flattened.
3. **Status semantics:** display existing backend statuses; do not invent a real-time availability signal.
4. **Selection/focus:** prevent regressions in the existing Hub panel and keyboard navigation.
5. **Dev environment:** `localhost:8000` may resolve to an unrelated IPv6 listener on this machine. Use the already configured `VITE_API_BASE_URL` and do not change protected `.env.local` automatically.

## 9. Workflow

1. Add this specification to `docs/features/feature-006-drone-fleet-frontend-integration.md`.
2. In a new Claude Code session, run `/feature-start 006`.
3. `feature-start` must inspect project context and the real API contract, invoke `task-planning`, produce an implementation plan and **stop for explicit approval**.
4. After approval, run `/task-implementation`.
5. Run QA and code-review subagents, then operator browser acceptance.
6. Only after operator approval, run `/feature-finalization` to update spec/tracker/docs and inspect Git changes. **Do not commit or push without separate explicit approval.**

## 10. Implementation and verification (recorded at finalization)

### Delivered (frontend only; no backend, migration or dependency changes)

- `types/drone.ts`, `api/drones.ts` (strict validation: one invalid record rejects the whole list), shared `api/validation.ts`.
- `features/data/useApiResource.ts` (abort, retry, stale-response ignoring) with `useHubs`/`useDrones` on top, and `ResourceStatusBanner` (per-resource Retry). Hubs and drones load independently.
- Map: Hub markers keep their behavior and gain a drone-count badge (count also in the accessible name). Individual drone markers are small (24 px target, 12 px glyph) and exist only for `IN_FLIGHT` drones plus the flagged exception below.
- **Docked rule (MVP simplification, reversible; Q8 has since been answered by Feature 009, where this same rule defines physical Hub occupancy, `business-rules.md` §2):** a drone is docked at a Hub when its status is not `IN_FLIGHT` and its stored position is within 50 m of that Hub (nearest Hub wins; ties go to the lower Hub id). `hub_id` is only the assigned/home Hub and is not used. Implemented in `features/map/fleetPlacement.ts`.
- A non-flying drone away from every Hub keeps a small dashed-border marker labelled "not at a Hub", so no drone is hidden.
- Until Hubs are loaded (or if they failed) only `IN_FLIGHT` drones are drawn, so no drone is falsely flagged as away.
- Hub panel lists "Drones at this Hub"; selecting a row opens the drone panel. One Hub or drone selection at a time.
- Drone panel: status, battery, assigned Hub (name, else id), stored position, SF-1 capabilities, labelled as a backend snapshot, not a live feed. Real coordinates are never changed; markers that share an exact point are spread by a screen-pixel offset only, and the panel says so.

### Verification

| Check | Result |
|---|---|
| `npm run lint`, `typecheck`, `format:check`, `build` | Passed |
| `npm run test` (Vitest + RTL) | Passed: 138 tests in 10 files |
| `GET /api/drones` against the running backend and PostgreSQL | Returned all 12 drones (checked earlier in the session, before the UI revision; no backend change since) |
| `qa-tester` (revised UI) | Pass with gaps; no critical, high or medium findings |
| `code-reviewer` (revised UI) | One Medium finding (drones falsely flagged "not at a Hub" while Hubs load or fail): fixed and covered by tests. Low findings below |
| Manual browser acceptance (rendering, badge position, 12 px glyph legibility, ring spread, keyboard focus, error/retry with the backend stopped, ~375 px layout with Mapbox attribution) | **NOT VERIFIED** (no Mapbox token access in the session); the operator must check it |

Acceptance criteria 1 to 8: covered by automated tests as revised above; criteria involving real map rendering are part of the unverified browser check. Criterion 9 passed. Criterion 10: both subagents were invoked and reported.

### Known limitations and follow-ups

- Docking is a display grouping from stored position and status; it does not enforce Hub capacity or define occupancy (Q8 open). The simulation feature should define "docked".
- The ring spread groups only exactly equal coordinates; nearby in-flight drones are not clustered.
- A drone opened from the Hub list has no map marker to highlight, and its panel shows the assigned Hub, not where it is docked.
- The Hub badge can touch a ring-offset flying drone that sits exactly over a Hub (not reachable with the seeded data).
- The badge's `hidden` attribute relies on Tailwind v4 preflight overriding `flex`; confirm in a browser.
- The Hub panel list scrolls inside an already scrollable panel (touch scroll chaining); the exact 50 m boundary and Enter/Space on a Hub marker are not unit-tested; `HubDetailPanel` has no test file of its own.
- There is no movement, polling or refresh; reload the page to re-read the snapshot.

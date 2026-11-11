# Feature 004 — Connect Hub Map to Backend API

**Status:** Complete — approved by the project owner  
**Implementation:** Complete. Not committed.  
**Verification:** Frontend lint, typecheck, format check, production build and 44 tests pass (rerun after the last code change); backend untouched. Smoke test against real FastAPI (127.0.0.1:8000) with Docker PostgreSQL 17 (port 55432): `GET /api/hubs` returned the 4 seeded Hubs with correct longitude/latitude and capacity 50; CORS allowed `http://localhost:5173` and not `http://127.0.0.1:5173`; Vite served the app. `qa-tester` and `code-reviewer` were both run and reported no Critical or High findings (their reports predate two small review fixes; the frontend checks were rerun afterwards, the subagents were not). **NOT VERIFIED by Claude:** rendering in a real browser (markers on the Mapbox map, panel, keyboard focus, mobile layout and attribution, error/retry with the backend stopped); no Mapbox token or browser run was available.  
**Area:** Frontend integration  
**Depends on:** Feature 002 (Hub map UI), Feature 003 (Hubs Backend API)

## Goal

Replace the hardcoded Hub dataset used by the existing React + Mapbox interface with Hub data retrieved from the SkyFleet FastAPI backend. Preserve the current map-first user experience and Hub interactions.

## Context and business rules

- FastAPI is the source of truth for Hub records. The backend exposes `GET /api/hubs` and `GET /api/hubs/{id}`.
- A Hub is both a parcel handover point and a drone base. `drone_capacity` describes drone capacity, normally 50, **not** parcel capacity.
- There is no separate `DroneBase` entity and no fixed Partner-to-Hub assignment.
- Four initial Hubs: Galeria Bałtycka, Forum Gdańsk, Centrum Riviera, and Centrum Handlowe Osowa.
- The backend and database remain authoritative; frontend must not independently create or modify Hub records.

## In scope

1. Add a small, typed frontend API layer to fetch the Hub collection from `GET /api/hubs`.
2. Map backend Hub fields to the existing frontend marker and detail-panel presentation without changing the underlying business meaning. Pay particular attention to `longitude`, `latitude`, `drone_capacity`, and stable slug `id`.
3. Replace runtime usage of hardcoded mock Hub records with the API response. Remove obsolete mock runtime imports; retain test fixtures where appropriate.
4. Keep existing Hub markers, selection, panel behavior, keyboard accessibility, focus behavior, responsive layout, and Mapbox attribution intact.
5. Handle loading, empty responses, network/server errors, and malformed data gracefully. Provide a simple retry action for failed requests; do not silently fall back to mock Hub data.
6. Configure the frontend-to-backend connection for local development using existing project conventions (environment variable or dev proxy). If cross-origin requests are used, apply narrowly scoped development CORS settings in FastAPI as needed; avoid permissive production defaults.
7. Add or update tests covering successful fetching and rendering, empty/error/retry states, and preservation of existing Hub interactions. Run existing frontend checks and relevant backend checks if backend configuration changes.
8. Document local run instructions and any necessary frontend environment configuration, using non-secret example values only.

## Expected behavior

- With the backend and PostgreSQL running and seeded, the map displays the four Hubs returned by the API, including Centrum Handlowe Osowa instead of Galeria Metropolia.
- Selecting a marker shows the correct Hub details using server-provided values.
- Marker coordinates follow Mapbox `[longitude, latitude]` order.
- Keyboard users can focus a marker, activate it using Enter, and retain predictable focus after the detail panel opens.
- A narrow viewport keeps the panel usable without obscuring required Mapbox attribution.
- During loading, the UI communicates that Hub data is being fetched without displaying stale mock markers as if they were current.
- If the API is unavailable, the UI displays a clear, non-blocking error with a retry control; the map itself remains usable.
- If the API returns an empty array, show a meaningful empty state rather than fabricating Hub markers.

## API contract and implementation notes

- Existing backend routes are authoritative; inspect actual response schemas before implementation. Do not guess JSON property names or add unnecessary endpoints.
- Prefer the existing frontend stack and conventions. Keep the integration lightweight; do not add a new state-management or data-fetching library unless the current code demonstrably requires one and the user approves.
- The local Docker PostgreSQL development service is configured on **host port 55432**, forwarding to container port 5432. The backend runs locally on Windows. The frontend talks to **FastAPI**, not directly to PostgreSQL.
- Do not expose database credentials or other secrets to the browser. Never copy a backend `DATABASE_URL` into a `VITE_` variable.
- Avoid touching protected local `.env` files; use safe example files and documented configuration.

## Acceptance criteria

- [x] Hub markers and details are populated from `GET /api/hubs`, not runtime mock data. (verified by code review, component tests and the API smoke test)
- [ ] All four seeded Hubs appear in correct locations and details match the API response. NOT VERIFIED in a browser: the API returns the correct four Hubs and coordinate order is unit-tested, but marker placement on the real map was not observed.
- [ ] Existing map, marker selection, keyboard/focus behavior, mobile panel layout, and attribution remain functional. NOT VERIFIED in a browser: marker and panel code paths are covered by component tests, but keyboard focus, mobile layout and attribution were not observed.
- [x] Loading, empty, error, and retry behavior are verified. (component/integration tests with a stubbed map; not exercised in a browser)
- [x] Frontend connects to local FastAPI without unsafe CORS settings or browser-exposed database secrets.
- [x] Frontend lint, typecheck, tests, format check, and build pass; relevant backend checks pass if changed.
- [ ] At least one end-to-end manual smoke test is performed with Docker PostgreSQL, seeded FastAPI, and the frontend running together; if not possible, explicitly mark it NOT VERIFIED. PARTIAL: API, CORS and Vite dev server verified with Docker PostgreSQL; the in-browser part is NOT VERIFIED.
- [x] QA and code review subagents are actually invoked, findings are reported, and blockers resolved before user acceptance.

## Out of scope

- Hub CRUD, editing, deletion, or management screens.
- New Hub attributes or schema changes unless a genuine API contract mismatch requires explicit approval.
- Drone entities, telemetry, orders, missions, dispatch, simulation, WebSockets, and AI operations.
- Partner or customer portals.
- Production deployment or authentication/authorization.
- Redesigning the map or replacing Mapbox.

## Workflow and completion

Use the established SkyFleet workflow: `feature-start` (planning only; stop for approval) → explicit `task-implementation` → QA/code review → user acceptance → `feature-finalization` (documentation and Git review). No commit or push without explicit approval. Keep changes scoped to Feature 004. Update this spec and `context/progress-tracker.md` only during approved finalization.

## Implementation notes

- **Data flow:** `frontend/src/api/hubs.ts` (`getHubs`) calls `GET /api/hubs` through the shared `apiGet`, validates every item (types, coordinate ranges, positive integer `drone_capacity`, non-empty `id`/`name`, unique ids) and maps `longitude`/`latitude` to `[lng, lat]`. Any invalid item fails the whole list. `useHubs` exposes `loading | ready | error` plus `retry`; `App.tsx` passes an empty list to the map until data is ready.
- **UI states:** `HubsStatusBanner` shows loading, empty and error (with Retry) as a non-blocking overlay; the map stays usable. There is no fallback to mock data.
- **Approved contract decision:** the API provides no `city` or `status`, so both were removed from the UI (decision approved by the project owner). The detail panel and marker label show `address`; the mock status row and its "Mock data" notice are gone; the "illustrative mall, not a real SkyFleet facility" note remains.
- **Mock removal:** `mockHubs.ts` and its test were deleted. `frontend/src/test/hubFixtures.ts` holds an API-shaped fixture of the four seeded Hubs for tests.
- **`apiGet`:** a 200 response with an invalid JSON body now raises `ApiError` (previously a raw `SyntaxError`).
- **Configuration:** `VITE_API_BASE_URL` is the only frontend setting; no new dependency and no backend change. `frontend/.env.example` uses `http://127.0.0.1:8000` because of the port conflict below; the code default in `src/api/client.ts` is still `http://localhost:8000`.

## Known limitations

- **Port 8000 on the development machine:** `wslrelay.exe` held `[::1]:8000` and answered 404, so `localhost` can reach it over IPv6 instead of the backend. Use `127.0.0.1` as the API base URL while that conflict exists. CORS is unaffected because it concerns the page origin (`http://localhost:5173`).
- Not verified in a browser (see the acceptance criteria above). The mobile detail panel spans the bottom of the screen and may cover the Mapbox attribution; that layout predates this feature.
- Not addressed (Low review findings, not reachable today): focus is lost when Retry is clicked; two `role="alert"` regions can appear when the Mapbox token is missing; no tests for abort on unmount or a stale response after retry; a stale `selectedHubId` is not cleared if the Hub list changes (relevant only if refresh or polling is added).

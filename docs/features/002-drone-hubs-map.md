# Feature 002 — Drone Hubs on the Map

**Project:** SkyFleet — Autonomous Urban Drone Delivery & AI Operations Platform  
**Status:** Complete — approved by the project owner  
**Area:** Frontend / Map  
**Implementation:** Complete. Not committed.  
**Verification:** Typecheck, lint, format check, 23 frontend tests and production build pass; QA and code review found no defects (the one Medium review finding, marker focus loss on selection, was fixed). The manual map check passed on the earlier four-Hub version (Galeria Metropolia); no separate manual re-check after the Osowa swap and the focus fix is recorded.

## 1. Goal

Make the existing Mapbox-based Tricity operations map display the locations of SkyFleet's initial four fictional Drone Hubs. The result should be an understandable, interactive foundation for later integration with the backend Hub API and live fleet operations.

This feature is **frontend-only**. It uses local, explicitly mock operational data; the backend remains the future source of truth.

## 2. Business context

A SkyFleet Hub is both a parcel handover/pickup location for Partners and an operational base for drones (storage, charging, maintenance, and readiness for missions). Do not introduce a separate `DroneBase` concept.

Hub capacity refers to **drones**, not parcels or orders. The initial configured maximum is **50 drones per Hub**. Actual occupancy and capacity enforcement are outside this feature.

The shopping malls are illustrative locations for a fictional SkyFleet network, not actual SkyFleet facilities or commercial partnerships.

## 3. Locations to show

- Galeria Bałtycka — Gdańsk
- Forum Gdańsk — Gdańsk
- Centrum Riviera — Gdynia
- Centrum Handlowe Osowa — Gdańsk (Spacerowa 48, 80-299 Gdańsk)

*Revision notes:* the Gdynia mall is displayed as "Centrum Riviera" (the name found in sources; originally "Galeria Riviera"). Galeria Metropolia was replaced by Centrum Handlowe Osowa after the initial specification. Coordinates in `frontend/src/features/hubs/mockHubs.ts` were supplied by the project owner as sourced values (`[lng, lat]`).

Use appropriately verified map coordinates for these shopping mall locations; do not invent precise coordinates. Coordinates identify the mall for visualization, not a real drone launch pad or entrance.

## 4. User experience

### Map markers

- Display four visually consistent Hub markers on the existing dark Mapbox map.
- Make Hub markers clearly distinguishable from future drone markers and other map elements.
- Preserve the current map interaction, responsiveness, loading/error states, and cleanup behavior.
- Ensure markers remain correctly positioned while zooming and panning.

### Hub details

- Clicking or tapping a Hub selects it and opens a compact, readable contextual detail view.
- Show the Hub name, city/location, **illustrative operational status**, and **maximum drone capacity: 50**.
- Make it obvious that operational status is mock data, not a live measurement.
- Provide a clear way to dismiss the detail view or switch to another Hub.
- Keep the interaction usable on desktop and mobile, including keyboard access where practical.

### Visual direction

Follow `context/ui-context.md`: dark, technical, map-first, uncluttered, Tailwind CSS as the primary styling approach. Avoid a large dashboard redesign.

## 5. Data and integration boundary

- Use a small, typed Hub representation and a separate local mock-data source.
- Include only fields needed for this feature, such as stable ID, name, city/location, coordinates, mock status, and drone capacity.
- Keep map rendering separate from the data source so a future API integration can replace the mock source without redesigning the UI.
- Do not implement backend calls, a new persistence model, real-time updates, or domain calculations in this feature.

## 6. Acceptance criteria

1. The existing map shows all four specified Hub locations.
2. Each Hub is selectable by mouse/touch; its contextual details appear correctly.
3. The detail view shows the correct Hub identity and `50` as the **maximum drone capacity**.
4. Operational values are clearly mock/illustrative; no false live occupancy is presented.
5. Hub data is typed and separate from map UI code, allowing a future API source.
6. Existing Mapbox behavior (navigation, loading, error handling, and cleanup) still works.
7. The interface remains usable at desktop and mobile sizes.
8. Appropriate frontend tests cover rendering/selection/data behavior; existing checks are run and results reported.

## 7. Explicitly out of scope

- Hub CRUD, backend models, REST endpoints, database migrations, or API integration.
- Real occupancy, occupancy enforcement, capacity balancing, or fleet repositioning.
- Drones, flight animation, dispatch, missions, charging/maintenance workflows, or simulation state changes.
- Partner portals, parcel workflows, real airspace/weather integrations.
- A 3D drone model, which belongs to a later feature.
- New infrastructure or unnecessary dependencies.

## 8. Workflow for Claude Code

1. Read `CLAUDE.md`, this feature specification, and relevant context/rules; inspect current code and Git status.
2. Use the existing **task-planning** skill to propose the smallest suitable implementation plan, including affected files, tests, and acceptance criteria. **Stop for approval before coding.**
3. After approval, use **task-implementation** to implement the agreed scope.
4. Run relevant frontend checks and tests; use **qa-tester** and **code-reviewer** subagents for independent verification, supplying test output to QA if the agent cannot run commands.
5. Fix confirmed issues within the approved scope, then use **documentation-update** for verified documentation/progress changes only.
6. Report results and remaining limitations. Do not commit or push without explicit permission.

**Source-of-truth note:** `context/business-rules.md` governs detailed Hub business rules; this feature document defines the intended frontend behavior only.

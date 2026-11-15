# SkyFleet

**Autonomous Urban Drone Delivery & AI Operations Platform** — a simulated drone logistics network
operating across the Tricity area (Gdańsk, Sopot, Gdynia), with a map-first operations dashboard, a
backend-owned continuously running simulation, and an AI Fleet Operations Agent.

> Status: **MVP in progress.** The map, Hubs, drones, orders, missions, dispatch, the continuously running
> simulation worker, incidents and a read-only AI Copilot are implemented; testing, polish and deployment
> remain (Phases 9-10). Real-time updates use REST polling, not WebSocket
> ([ADR 0015](docs/decisions/0015-frontend-polling-instead-of-websocket.md)). See
> [`progress-tracker.md`](context/progress-tracker.md) for the detailed status.

## Architecture at a glance

| Part | Tech | Location |
|---|---|---|
| Frontend (operations dashboard) | React, TypeScript, Vite, Tailwind CSS v4, Mapbox GL JS, Three.js (drone 3D viewer) | `frontend/` |
| Backend API | Python 3.13, FastAPI, Pydantic | `backend/app/main.py` |
| Simulation Worker | Separate Python process sharing backend modules | `backend/app/worker.py` |
| Database | PostgreSQL 17 via Docker Compose (host port 55432) | `docker-compose.yml` |

The backend owns all operational state; the frontend only displays it. The worker runs independently
of any browser session. Details: [`architecture-context.md`](context/architecture-context.md) and
[`docs/decisions/`](docs/decisions/).

## Prerequisites

- **Node.js 24** (with npm)
- **Python 3.13**
- **[uv](https://docs.astral.sh/uv/)** — Python dependency manager (`winget install astral-sh.uv`)
- **Docker** — runs the PostgreSQL database (Docker Desktop on Windows)

## First-time setup

```bash
# Backend
cd backend
uv sync                      # creates .venv and installs locked dependencies
cp .env.example .env         # optional: defaults work for local development

# Frontend
cd ../frontend
npm install
cp .env.example .env.local   # then set VITE_MAPBOX_TOKEN (see below)
```

**Mapbox token (required for the map):** create a free account at mapbox.com, copy a **public**
token (`pk.…`) from the account's tokens page, optionally restrict it to `http://localhost:5173`,
and put it in `frontend/.env.local` as `VITE_MAPBOX_TOKEN=pk.…`. Restart `npm run dev` afterwards.
Without it the app still runs and shows a "Map unavailable" message.

## Running locally

Run each in its own terminal:

| Process | Command (from) | URL |
|---|---|---|
| API | `uv run uvicorn app.main:app --reload` (`backend/`) | http://localhost:8000 — OpenAPI docs at `/docs` |
| Simulation Worker | `uv run python -m app.worker` (`backend/`) | logs ticks to the console |
| Frontend | `npm run dev` (`frontend/`) | http://localhost:5173 |
| Database | `docker compose up -d db` (repo root) | localhost:55432 (PostgreSQL 17 in Docker) |

**Database and Hubs API (Feature 003):** start PostgreSQL, create the schema, and seed the four Hubs
(the seed can be run repeatedly), then start the API:

```bash
docker compose up -d db                  # repo root
cd backend
uv run alembic upgrade head              # create/upgrade the schema
uv run python -m app.hubs.seed           # idempotent
uv run uvicorn app.main:app --reload
# GET http://localhost:8000/api/hubs  and  /api/hubs/{id}  (e.g. hub-forum-gdansk)
```

**Standard development database:** PostgreSQL 17 runs in Docker Compose and is published on host
port **55432** (container port 5432), with data in the named volume `skyfleet-db`. The backend runs
natively on Windows and connects through `localhost:55432`. `DATABASE_URL` defaults to
`postgresql+psycopg://skyfleet:skyfleet@localhost:55432/skyfleet`; override it in `backend/.env` if
needed. Port 5432 is intentionally not used, so a PostgreSQL installed on Windows does not conflict
and must not be used by SkyFleet. `docker compose down` keeps the data; `docker compose down -v`
deletes it.

The seed only inserts missing Hubs; it never modifies existing rows.

**Drone fleet (Feature 005):** after the Hubs exist, seed the drone model and the fleet (also
repeatable), then read it from the API:

```bash
cd backend
uv run alembic upgrade head              # includes migration 0002 (drone_models, drones)
uv run python -m app.hubs.seed           # the drone seed fails clearly if the Hubs are missing
uv run python -m app.drones.seed         # SF-1 model + 12 drones (3 per Hub)
# GET http://127.0.0.1:8000/api/drones  and  /api/drones/{id}  (e.g. DRN-001)
```

The single drone model is **SkyFleet SF-1 Courier**: an electric quadcopter (four rotors) with 3.0 kg maximum
payload, 20 km maximum total flight distance (a conservative mission budget of 14 km is stored; both
cover the whole route including the return to a Hub, not a one-way delivery radius), 45 km/h cruise,
60 km/h maximum speed, about 32 min nominal flight time, 20% minimum battery reserve, about 45 min to
charge to 80%, 10 m/s maximum wind and 9 kg empty weight. The simulated 40–100 m operating altitude
is an assumption and is not stored. These are simulation assumptions, not certified performance and
not an authorization to fly in real airspace.

Limitations: seeded drones are `IDLE` snapshots at their Hub's coordinates; nothing moves, charges or
changes status yet. The drone seed only inserts missing rows and never resets existing drone state
(so changing SF-1 values later needs a migration). The seed checks each Hub's assigned drones against
its capacity; every seeded drone starts docked at its assigned Hub, so this bounds the initial
physical occupancy. At runtime a Hub's occupancy is the number of drones physically docked there (see
Mission planning below).

**Delivery orders (Feature 007):** after the Hubs exist, seed the illustrative orders (repeatable) and
read them from the API:

```bash
cd backend
uv run alembic upgrade head              # includes migration 0003 (orders)
uv run python -m app.hubs.seed
uv run python -m app.orders.seed         # ORD-001..011, insert-only (ORD-011: Bałtycka -> Forum)
# GET http://127.0.0.1:8000/api/orders  and  /api/orders/{id}  (e.g. ORD-001)
```

An order is one package handed over at an explicit origin Hub, with a destination address and
coordinates, a package weight (above 0 and at most 3.0 kg, the SF-1 payload; enforced by the
database), a status and created/updated timestamps. Seeded orders are all `READY_FOR_PICKUP`; only the
confirmed initial states `CREATED`, `AWAITING_HANDOVER` and `READY_FOR_PICKUP` exist so far. The
endpoints are read-only: there is no create/update/delete, no drone assignment (a future Mission
feature owns that), no Partner entity and no feasibility check, so an order whose destination is far
from its Hub is still stored. Addresses and coordinates are illustrative simulation data, not
verified customer addresses.

**Mission planning (Feature 009):** an operator can check whether a drone can serve an order, confirm
the assignment, and cancel it before takeoff. Nothing flies: confirming creates an `ASSIGNED`
mission only, and never changes the order, the drone, its battery or any Hub.

```bash
cd backend
uv run alembic upgrade head              # includes migration 0004 (missions)
# GET  http://127.0.0.1:8000/api/missions/plan?order_id=ORD-001&drone_id=DRN-010   (read-only preview)
# POST http://127.0.0.1:8000/api/missions          {"order_id": "ORD-001", "drone_id": "DRN-010"}
# POST http://127.0.0.1:8000/api/missions/{id}/cancel
# GET  http://127.0.0.1:8000/api/missions  and  /api/missions/{id}
```

Rules (MVP simulation assumptions, not certified aircraft performance):

- The order must be `READY_FOR_PICKUP` (parcel physically confirmed at its origin Hub). Assignment is
  derived from the mission, so the order status does not change.
- The drone must be `IDLE`, docked at the order's origin Hub (status not `IN_FLIGHT` and stored
  position within `HUB_DOCK_PROXIMITY_M`, default 50 m, of that Hub; `hub_id` is only the assigned
  Hub), carry no more than its model's payload, and have no active mission. At most one active
  (`ASSIGNED` or `IN_FLIGHT`) mission can exist per order and per drone, enforced by the database.
- Route: origin Hub, destination, then the nearest Hub to the destination that the drone can reach and
  that has a free **physical** place, by great-circle distance. The total must stay within the model's
  mission budget (14 km for the SF-1).
- Energy: an empty drone uses `100 / max_range_km` % of battery per km (5% for the SF-1); a loaded drone
  uses that rate × (1 + `MISSION_PAYLOAD_ENERGY_FACTOR` × weight / max payload). The outbound leg
  carries the parcel and the return leg does not (expected energy). The safety check assumes the parcel
  stays on board for the whole route, and requires that worst case plus the 20% reserve. Example (5 km
  out, 5 km back): a 0.3 kg parcel needs 72.5% battery, a 3 kg parcel needs 95%.
- Hub occupancy is the number of drones physically docked there (50 places); a drone in flight counts
  at no Hub, and assigning or cancelling a mission never changes occupancy. **Nothing is reserved**:
  the planned return Hub may fill before landing, so the flight simulation (Feature 010) must recheck
  capacity before landing and pick another reachable Hub if needed.
- Cancelling is allowed only while a mission is `ASSIGNED` (404 unknown, 409 otherwise); it frees the
  order and the drone. `IN_FLIGHT` is reserved for Feature 010 and is never set by this feature.

| Environment variable | Default | Purpose |
|---|---|---|
| `MISSION_PAYLOAD_ENERGY_FACTOR` | `0.5` | Extra energy per km at full payload (0.5 = +50%) |
| `HUB_DOCK_PROXIMITY_M` | `50` | Metres from a Hub within which a drone counts as docked |

Why a plan can be refused (`reasons` in the preview, and the 409 body of `POST /api/missions`; all that
apply are listed): `ORDER_NOT_READY`, `ORDER_ALREADY_ASSIGNED`, `DRONE_ALREADY_ASSIGNED`,
`DRONE_NOT_AVAILABLE`, `DRONE_NOT_AT_ORIGIN_HUB`, `OVERWEIGHT`, `ROUTE_TOO_LONG`,
`INSUFFICIENT_BATTERY`, `RETURN_HUBS_FULL`. Status codes: 404 unknown order, drone or mission; 409 not
eligible, lost a race, or `MISSION_NOT_CANCELLABLE`; 422 malformed input.

Migration `0004` creates the `missions` table and the two partial unique indexes
(`uq_missions_active_order`, `uq_missions_active_drone`). It only adds a table. Feature 009 versus
later features: this feature plans, confirms and cancels; takeoff, landing and the landing-time
capacity recheck are Feature 010; automatic dispatch is Feature 011; fleet rebalancing is Feature 012.

Out of scope here: automatic dispatch (Feature 011), flight simulation (Feature 010), fleet
rebalancing (Feature 012; target about 40 of 50 places occupied per Hub), airspace and weather checks.
The PostgreSQL concurrency tests are opt-in and use a temporary database: `uv run pytest -m postgres`.

**Flight simulation (Feature 010):** an `ASSIGNED` mission can be started and is then flown by the
Simulation Worker in accelerated time. The map shows the flight live (see "Frontend" below); assigning
a drone to an order is still done through the API (Swagger at `/docs`), because only a temporary
"Start mission" control exists in the UI.

```bash
cd backend
uv run alembic upgrade head              # includes migration 0005 (flights, worker heartbeat)
uv run python -m app.worker              # the simulation: required, or missions cannot start
# POST http://127.0.0.1:8000/api/missions/{id}/start   (takeoff; needs a running worker)
# GET  http://127.0.0.1:8000/api/flights               (active and emergency flights, for polling)
```

- **Starting** revalidates the full mission plan against the actual current state (order
  `READY_FOR_PICKUP`, drone `IDLE` and docked at the origin Hub, enough *actual* battery, a return Hub
  with a free place). It is refused with 503 `SIMULATION_WORKER_UNAVAILABLE` if the worker has no
  recent heartbeat (the worker records one every tick; the limit is `SIM_HEARTBEAT_STALE_SECONDS`),
  and with 409 if the mission is not `ASSIGNED` or no longer eligible. It happens exactly once. A
  started mission can no longer be cancelled.
- **Takeoff:** mission and drone become `IN_FLIGHT`, the order `OUT_FOR_DELIVERY`; the drone stops
  counting at its Hub immediately. **Delivery** (always successful in this feature) makes the order
  `DELIVERED` before the drone returns; **landing** makes the mission `COMPLETED` and the drone `IDLE`
  at the Hub with its remaining battery. There is no charging yet, so batteries only fall across missions.
- **Timing (simulation time, not flight physics; the SF-1 speeds are unchanged):** a complete mission
  takes `30 + 60 × min(route km / 14, 1)` seconds (about 36 s for the seeded routes), with a 3 s
  delivery stop, the rest split between the loaded outbound and the empty return leg by distance.
  Position and battery are a pure function of the stored schedule and the clock, so a restart or a late
  tick never resets or invents progress. The loaded and empty energy rates are those of Feature 009.
- **Landing without reservations:** about 60 m before the Hub the worker locks that one Hub, counts the
  drones physically docked there and, only if there is a free place, docks the drone in the same
  transaction. A full Hub makes it divert to the nearest other Hub that the battery can reach (it may
  use the 20% reserve but must arrive with at least `SIM_CRITICAL_BATTERY_PCT`) and that has a place.
  Concurrent landings cannot exceed a Hub's capacity.
- **Emergency (simulated, not a real landing site):** if no safe Hub landing is possible, the flight
  ends as mission `EMERGENCY`, the drone stays where it stopped in `MAINTENANCE`, and the order stays
  `DELIVERED`. `GET /api/flights` keeps listing the flight with its reason (`NO_HUB_WITH_CAPACITY`,
  `BATTERY_INSUFFICIENT` or `BATTERY_CRITICAL`). There is no recovery path yet (a later incident or
  maintenance feature), and no indefinite holding.
- **Occupancy rule:** a drone that is `IN_FLIGHT` or in `MAINTENANCE` is never counted as docked,
  whatever its coordinates.
- **Known limitations of this stage:**
  - Hub capacity is guaranteed because every path that docks a drone takes that Hub's row lock first; a
    landing does. A later charging, maintenance-release or repositioning feature must do the same.
  - A drone in `MAINTENANCE` is never counted as docked, even if it is parked at a Hub; a future
    maintenance feature will need its own handling of drones serviced at a Hub.
  - Emergency flights stay listed by `GET /api/flights` (there is no acknowledge step yet), and the
    drone stays in `MAINTENANCE` until a later incident or maintenance feature.
  - The heartbeat is written at the start of each tick; a tick that takes longer than
    `SIM_HEARTBEAT_STALE_SECONDS` would make the worker look stale.
  - If advancing one flight fails, the error is logged and the other flights continue; the failing
    flight is retried on the next tick.
  - `Drone.hub_id` is the Hub where the drone last docked successfully: the worker sets it on a
    landing (a diversion that lands included), never during a flight or after an emergency. It is
    not used for occupancy, which comes from status and position; missions and flights keep the Hub
    the drone departed from.
- `GET /api/flights` returns `{server_time, worker_heartbeat_at, worker_stale, flights}`; each flight has
  its phase, progress, position, battery, next target with seconds to reach it, and `updated_at`. If the
  worker stops after a start, `worker_stale` turns true and `updated_at` stops advancing.

**Frontend (Feature 010, stage 2):** the dashboard polls the backend: flights every 1 s, drones,
orders and missions every 2 s (paused while the tab is hidden, never overlapping, and a failed refresh
keeps the last data and says so). It never runs the mission: positions, battery, phases and landings
all come from the backend.

- **Flights on the map:** a flying drone is a small marker that glides between the backend's snapshots,
  toward the backend's own next point and never past it. Prefers-reduced-motion and a stopped worker
  make it jump between snapshots instead. The drone panel gains a **Flight** section: phase, progress,
  battery, seconds to the next point, the planned return Hub and, after a diversion, where it is heading.
- **Hub counts** follow takeoffs and landings through the polled drones. The docking rule in
  `fleetPlacement.ts` now matches the backend: `IN_FLIGHT` and `MAINTENANCE` drones are never counted
  at a Hub, whatever their coordinates; a drone in maintenance shows as its own marker.
- **Order statuses** `OUT_FOR_DELIVERY` and `DELIVERED` are shown; delivered orders keep their entry.
- **Start mission (temporary demonstration control):** the order panel and the drone panel show a
  **Start mission** button for an already `ASSIGNED` mission (docked drones with a mission are marked in
  the Hub's drone list). It calls the backend start, which validates and performs it; it does not pick a
  drone or assign an order. If the worker is not running, or the mission is no longer eligible, the
  panel says why. Feature 011 will start missions automatically through the same backend action.
- **Notices:** a simulated emergency is a persistent alert (drone, mission, reason, stop position; the
  parcel was already delivered; the drone is out of service). A worker that stopped updating flights,
  flight data that cannot be read (with Retry) and drone or order data that could not be refreshed each
  get a notice; nothing is shown while all is well.
- **Known limitations of the frontend:**
  - A takeoff or landing is shown from two polls (flights every second, drones every two), so a
    marker can step a short way at the very start or end of a flight; the flying set changing triggers
    an immediate re-read to keep this brief. It is cosmetic, not a data error.
  - When a drone changes between flying and not flying, all drone markers are rebuilt once, so
    keyboard focus on a drone marker is lost at that moment (position and status updates keep it).
  - A read that takes more than 10 s counts as failed and is flagged as stale instead of freezing
    silently. Emergency alerts persist (no acknowledge step yet); only the first three are listed in
    full, with a summary line for the rest.
  - The temporary Start mission control stays disabled after a successful start until the mission
    leaves `ASSIGNED`; automatic dispatch (Feature 011) will start missions without it.
- **Demo:** run the database, the API (`uvicorn`) and the worker (`uv run python -m app.worker`), open
  the dashboard, assign a mission in Swagger (`POST /api/missions`, for example order `ORD-001` with
  drone `DRN-010`), open that order or drone in the dashboard and press **Start mission**.

| Environment variable | Default | Purpose |
|---|---|---|
| `SIM_TICK_SECONDS` | `1.0` | Worker tick interval (also the snapshot update interval) |
| `SIM_FLIGHT_MIN_SECONDS` / `SIM_FLIGHT_MAX_SECONDS` | `30` / `90` | Duration of a complete mission at 0 km / at the distance budget |
| `SIM_DELIVERY_DWELL_SECONDS` | `3` | Delivery stop (part of the total) |
| `SIM_LANDING_APPROACH_M` | `60` | Distance before the Hub where the landing is decided (must exceed `HUB_DOCK_PROXIMITY_M`) |
| `SIM_CRITICAL_BATTERY_PCT` | `5` | Lowest battery a diversion may arrive with |
| `SIM_HEARTBEAT_STALE_SECONDS` | `10` | Maximum age of the worker heartbeat for a start |

Backend tests use SQLite (in-memory, plus temporary files for the migration test) and need neither
Docker nor PostgreSQL. Known limitation: they do not exercise PostgreSQL itself.

The dashboard header shows **Backend connected** / **Backend unreachable**, which also confirms CORS
is configured correctly.

**Hubs on the map (Feature 004):** the frontend loads Hubs from `GET /api/hubs` on page load; there is
no mock fallback. Start the database, migrate, seed, and run the API (above) before opening
http://localhost:5173. While loading, empty, or failed, a banner explains the state (failures offer
**Retry**) and the map stays usable. The browser calls the API directly, so the frontend origin must
be in the backend's `CORS_ORIGINS` (default `http://localhost:5173`; use `localhost`, not
`127.0.0.1`). `VITE_API_BASE_URL` (code default `http://localhost:8000`; `.env.example` uses `http://127.0.0.1:8000`
because on some Windows/WSL setups `localhost` can resolve to a different listener on IPv6 port 8000)
is the only frontend setting for this; never put database credentials in a `VITE_` variable.

**Drone fleet on the map (Feature 006):** the frontend also loads `GET /api/drones` once on page load.
Seed the drones first (`uv run python -m app.drones.seed`, see above). Drones that are *docked* are
not drawn individually: each Hub marker shows a small badge with its docked-drone count, and the Hub
panel lists them under "Drones at this Hub"; pick one to open its drone panel (status, battery,
assigned Hub, stored position and the SF-1 model capabilities, labelled as a *current backend
snapshot, not a live flight feed*). Only `IN_FLIGHT` drones get small individual markers, at their
real coordinates.

MVP rule for "docked" (a simplification until the simulation defines it, see business rules Q8): a
drone is docked at a Hub when its status is not `IN_FLIGHT` and its stored position is within 50 m of
that Hub. `hub_id` (the Hub of the last successful docking) is not used for this: a drone is counted
at the Hub it is physically at. A non-flying drone that is not at any Hub is a flagged exception: it still gets a small
marker with a dashed border (never hidden). With the seeded data (12 `IDLE` drones at their Hubs) the
map therefore shows four badges and no drone markers. Markers that share an exact point are spread on
a small ring around it **on screen only**; the panel always shows the real stored position. Only one
Hub or drone panel is open at a time. Hubs and drones load independently: if one request fails, the
other still appears and each has its own **Retry**. There is no movement, polling or refresh yet;
reload the page to re-read the snapshot.

**Delivery orders on the map (Feature 008):** the frontend also loads `GET /api/orders` once on page
load (seed them first with `uv run python -m app.orders.seed`, see above). Each order's destination
is a small diamond marker at its stored coordinates; the **Orders (N)** list in the top-right corner
is collapsed by default and lists every order, so any order stays reachable even where markers sit
close together. Selecting a list row or a marker opens the same order panel (status, weight, origin
Hub, destination, stored position, created/updated times in UTC) and highlights its marker; only one
Hub, drone or order panel is open at a time. Markers that share an exact point are spread on a small
ring **on screen only**. The orders are simulation data, read-only, with no drone assignment shown.
Orders load independently of Hubs and drones and have their own **Retry**; there is no polling, so
reload the page to re-read the snapshot. If the backend later adds an order status the frontend does
not know, the order list is rejected as invalid data until the frontend is updated.

## Quality checks

```bash
# backend/
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy app tests

# frontend/
npm run lint          # oxlint
npm run typecheck
npm run test          # Vitest + React Testing Library
npm run format:check  # Prettier
npm run build
```

## Configuration

Configuration comes from environment variables; each app has a committed `.env.example`.
Real `.env` / `.env.local` files are git-ignored and must never be committed.

| Variable | App | Purpose |
|---|---|---|
| `APP_ENV` | backend | `development` / `test` / `production` |
| `CORS_ORIGINS` | backend | Comma-separated allowed frontend origins |
| `SIM_TICK_SECONDS` | backend | Simulation Worker tick interval |
| `DATABASE_URL` | backend | SQLAlchemy URL; defaults to the Docker Compose PostgreSQL (`postgresql+psycopg://skyfleet:skyfleet@localhost:55432/skyfleet`) |
| `LOG_LEVEL` | backend | Python logging level |
| `VITE_API_BASE_URL` | frontend | Backend base URL |
| `VITE_MAPBOX_TOKEN` | frontend | **Public** Mapbox token (`pk.…`), URL-restricted |

Anything prefixed `VITE_` is bundled into the browser, so only public values belong there. The Mapbox
token is public by design and should be restricted to the app's URLs in the Mapbox dashboard.

## Where things live

Top level: `backend/` (Python API and worker), `frontend/` (React app), `context/` (the seven
source-of-truth documents), `docs/` (`decisions/` ADRs, `features/` per-feature specs with their
implementation records, `diagrams/` BPMN), `docker-compose.yml` (PostgreSQL).

### Backend (`backend/`)

| Path | Responsibility | More |
|---|---|---|
| `app/main.py` | FastAPI app; registers the routers under `/api` | |
| `app/api/routes/` | Thin HTTP handlers (hubs, drones, orders, missions, flights, dispatch, events, incidents, order simulation, copilot, health); no business logic | |
| `app/worker.py` | Entry point of the Simulation Worker (separate process, writes a heartbeat) | [Feature 010](docs/features/010-Flight%20Simulation.md) |
| `app/simulation/` | Worker logic: engine tick, flight, charging, failures and recovery, failed delivery, LPR helicopter, relocation, random incidents | [ADR 0004](docs/decisions/0004-incident-event-foundation.md)-[0009](docs/decisions/0009-manual-drone-relocation.md) |
| `app/hubs/`, `app/drones/`, `app/orders/` | Entities, repositories, services, seeds; `orders/` also holds the order generator, delivery destinations, feasibility and cancellation | [ADR 0005](docs/decisions/0005-order-cancellation-and-recall.md) |
| `app/missions/` | Mission planning, routing, energy, Hub capacity and presence, takeoff | [Feature 009](docs/features/009-mission-planning-assignment.md) |
| `app/dispatch/` | Deterministic dispatch recommendation and execution, automatic mode, fleet rebalancing | [ADR 0010](docs/decisions/0010-automatic-fleet-rebalancing.md) |
| `app/events/` | Append-only `operational_events` and `GET /api/events` | [ADR 0004](docs/decisions/0004-incident-event-foundation.md) |
| `app/weather/` | The global rain warning and the takeoff check | [ADR 0011](docs/decisions/0011-rain-warning-flight-grounding.md) |
| `app/ai/` | AI gateway, one provider transport, model and price allowlist, durable budget; no domain imports | [ADR 0012](docs/decisions/0012-ai-foundation-and-cost-guardrails.md) |
| `app/fleet_context/` | Read-only snapshot of the present fleet state, rendered as JSON for the model | [ADR 0013](docs/decisions/0013-fleet-context-read-only-intelligence.md) |
| `app/copilot/` | Access control and orchestration for the authenticated Copilot endpoint | [ADR 0014](docs/decisions/0014-ai-copilot-access-and-endpoint.md) |
| `app/db/`, `app/config.py` | Database session, settings from environment variables | [ADR 0001](docs/decisions/0001-postgresql-database.md) |
| `migrations/` | Alembic migrations (`alembic upgrade head`) | |
| `tests/` | Pytest, one folder per module, plus `unit/` and `integration/`; PostgreSQL tests are opt-in (`-m postgres`) | |

### Frontend (`frontend/src/`)

| Path | Responsibility |
|---|---|
| `api/` | Typed HTTP client and one module per backend resource (`client.ts`, `flights.ts`, `copilot.ts`, ...) |
| `features/data/` | Shared polling and request hooks; intervals in `polling.ts` ([ADR 0015](docs/decisions/0015-frontend-polling-instead-of-websocket.md)) |
| `features/map/`, `hubs/`, `drones/`, `orders/`, `flights/`, `missions/` | Map layers, markers and detail panels for each entity |
| `features/operations/` | The Operations panel and its tabs (lists, events, Copilot) |
| `features/copilot/` | Copilot chat tab; state lives above the tabs and the token is kept in memory only |
| `features/dispatch/`, `orderSimulation/`, `incidents/`, `weather/`, `lpr/` | Simulation controls, scenarios and incident displays |
| `features/management/` | Drone and order management tables |
| `features/drone3d/`, `telemetry/` | Three.js drone viewer ([ADR 0003](docs/decisions/0003-threejs-drone-viewer.md)) and simulated telemetry panel |
| `features/system-status/` | Backend and worker status display |
| `components/ui/`, `types/` | Shared UI pieces; API contract types |

### Data flow in one paragraph

The Simulation Worker changes state in PostgreSQL on its own; the API reads and validates through the
same modules; the browser polls REST endpoints and renders what it receives. The worker never needs an
open browser. The Copilot sends a read-only fleet snapshot to the model and has no tools, so it cannot
change any state.

### Finding the reasoning behind a behavior

1. [`business-rules.md`](context/business-rules.md) for what the business confirmed.
2. The ADR in `docs/decisions/` for why it was built that way.
3. The feature spec in `docs/features/` (numbered; each ends with an implementation record).
4. [`progress-tracker.md`](context/progress-tracker.md) for status and known limits.

## Project documentation

- [`business-rules.md`](context/business-rules.md) — confirmed business rules and open questions
- [`project-overview.md`](context/project-overview.md) — product vision and scope
- [`architecture-context.md`](context/architecture-context.md) — system architecture
- [`code-standards.md`](context/code-standards.md) — coding conventions
- [`ui-context.md`](context/ui-context.md) — UI/UX direction
- [`ai-workflow-rules.md`](context/ai-workflow-rules.md) — AI-assisted development workflow
- [`progress-tracker.md`](context/progress-tracker.md) — roadmap and status
- [`docs/decisions/`](docs/decisions/) — architecture decision records (0001-0015)
- [`docs/features/`](docs/features/) — per-feature specifications and implementation records
- [`CLAUDE.md`](CLAUDE.md) — Claude Code project instructions

# SkyFleet

**Autonomous Urban Drone Delivery & AI Operations Platform** — a simulated drone logistics network
operating across the Tricity area (Gdańsk, Sopot, Gdynia), with a map-first operations dashboard, a
backend-owned continuously running simulation, and an AI Fleet Operations Agent.

> Status: **Phase 1 — runnable skeleton.** See [`progress-tracker.md`](context/progress-tracker.md).

## Architecture at a glance

| Part | Tech | Location |
|---|---|---|
| Frontend (operations dashboard) | React, TypeScript, Vite, Tailwind CSS v4 (Mapbox GL JS in Phase 2) | `frontend/` |
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
- **Docker** — only needed from Phase 3 (database)

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

The single drone model is **SkyFleet SF-1 Courier**: an electric hexacopter with 3.0 kg maximum
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

**Delivery orders (Feature 007):** after the Hubs exist, seed ten illustrative orders (repeatable) and
read them from the API:

```bash
cd backend
uv run alembic upgrade head              # includes migration 0003 (orders)
uv run python -m app.hubs.seed
uv run python -m app.orders.seed         # ORD-001..010 across the four Hubs, insert-only
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
that Hub. `hub_id` is only the assigned/home Hub, so it is not used: a drone sitting at another Hub is
counted there. A non-flying drone that is not at any Hub is a flagged exception: it still gets a small
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
| `VITE_MAPBOX_TOKEN` | frontend | *(Phase 2)* **Public** Mapbox token (`pk.…`), URL-restricted |

Anything prefixed `VITE_` is bundled into the browser, so only public values belong there. The Mapbox
token is public by design and should be restricted to the app's URLs in the Mapbox dashboard.

## Repository layout

```
backend/    FastAPI app (app/), Simulation Worker (app/worker.py), tests/
frontend/   React app: src/api (HTTP client), src/types (API contracts),
            src/features (feature modules), src/components/ui (shared UI)
context/    Project context documents (business rules, overview, architecture, standards, UI, workflow, progress)
docs/       Architecture decision records (decisions/), task specs (tasks/), BPMN diagrams (diagrams/)
```

## Project documentation

- [`business-rules.md`](context/business-rules.md) — confirmed business rules and open questions
- [`project-overview.md`](context/project-overview.md) — product vision and scope
- [`architecture-context.md`](context/architecture-context.md) — system architecture
- [`code-standards.md`](context/code-standards.md) — coding conventions
- [`ui-context.md`](context/ui-context.md) — UI/UX direction
- [`ai-workflow-rules.md`](context/ai-workflow-rules.md) — AI-assisted development workflow
- [`progress-tracker.md`](context/progress-tracker.md) — roadmap and status
- [`CLAUDE.md`](CLAUDE.md) — Claude Code project instructions

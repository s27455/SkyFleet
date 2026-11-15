# SkyFleet — Development Guide

This guide covers running SkyFleet natively with hot reload, plus configuration, tests and a map of
the code. To simply run the application, use the Docker Compose quick start in the
[README](../README.md).

## Native setup

Native development runs the API, the worker and the frontend on the host. Docker is used only for
PostgreSQL. Stop the full Docker stack (`docker compose down`) first, because both setups use ports
8000 and 5173.

### Prerequisites

- Node.js 24 (with npm)
- Python 3.13
- [uv](https://docs.astral.sh/uv/) (`winget install astral-sh.uv`)
- Docker Desktop, for PostgreSQL

### First-time setup

```bash
# Backend
cd backend
uv sync                      # creates .venv and installs the locked dependencies
cp .env.example .env         # optional: the defaults work for local development

# Frontend
cd ../frontend
npm install
cp .env.example .env.local   # then set VITE_MAPBOX_TOKEN
```

The frontend reads its Mapbox token from `frontend/.env.local`, not from the root `.env` used by
Docker Compose. Put a public `pk.` token there as `VITE_MAPBOX_TOKEN=pk.…` and restart `npm run dev`.
Without a token the app still runs and shows "Map unavailable" instead of the map.

### Database and initial data

```bash
docker compose up -d db                  # repo root: PostgreSQL 17 only
cd backend
uv run alembic upgrade head              # create or upgrade the schema
uv run python -m app.hubs.seed           # 4 Mall Pickup Hubs
uv run python -m app.drones.seed         # SF-1 model and 12 drones (3 per Hub); needs the Hubs
uv run python -m app.orders.seed         # sample orders ORD-001..011; needs the Hubs
```

The seeds only insert missing rows and never modify existing ones, so all of them can be re-run
safely. These are the same steps the Compose `migrate` service runs.

PostgreSQL is published on host port **55432** (container port 5432), with its data in the named
volume `skyfleet-db`. Port 5432 is deliberately avoided, so a PostgreSQL installed on Windows does
not conflict with it. `DATABASE_URL` defaults to
`postgresql+psycopg://skyfleet:skyfleet@localhost:55432/skyfleet`. `docker compose down` keeps the
data; `docker compose down -v` deletes it.

### Running

Run each process in its own terminal:

```bash
cd backend && uv run uvicorn app.main:app --reload   # API: http://localhost:8000 (Swagger at /docs)
cd backend && uv run python -m app.worker            # Simulation Worker: logs each tick
cd frontend && npm run dev                           # dashboard: http://localhost:5173
```

The worker is required: a mission cannot start unless the worker's heartbeat is recent. On startup
the worker switches Auto Dispatch, Order Simulation and Random Incidents off; turn them on from the
dashboard.

## Configuration

Every app has a committed `.env.example`. The real `.env` and `.env.local` files are git-ignored.

| Variable | Used by | Purpose |
|---|---|---|
| `DATABASE_URL` | backend | SQLAlchemy URL (default: the Compose PostgreSQL on `localhost:55432`) |
| `CORS_ORIGINS` | backend | Comma-separated allowed frontend origins (default `http://localhost:5173`) |
| `APP_ENV`, `LOG_LEVEL` | backend | Environment name and Python logging level |
| `SKYFLEET_AI_ENABLED`, `ANTHROPIC_API_KEY`, `SKYFLEET_AI_ACCESS_TOKEN` | backend | Optional AI Copilot (off by default) |
| `VITE_API_BASE_URL` | frontend | Backend base URL (code default `http://localhost:8000`) |
| `VITE_MAPBOX_TOKEN` | frontend | Public Mapbox token (`pk.…`) |

Anything prefixed with `VITE_` is bundled into the browser, so only public values belong there.

- **CORS:** the browser calls the API directly, so the frontend's origin must be listed in
  `CORS_ORIGINS`. Open the dashboard via `localhost`, not `127.0.0.1`.
- **API address:** `frontend/.env.example` sets `VITE_API_BASE_URL` to `http://127.0.0.1:8000`. On some
  Windows/WSL setups, `localhost` can resolve to a different listener on IPv6 port 8000.
- **Docker Compose:** the Compose stack sets the database URL, CORS origin and API base URL itself.
  Only the variables in the root `.env.example` are read there.

Simulation timing and behaviour can be tuned with further environment variables. All of them have
defaults and are documented next to their definitions in `backend/app/config.py`. The most relevant:

| Variable | Default | Meaning |
|---|---|---|
| `SIM_TICK_SECONDS` | 1.0 | Worker tick interval |
| `SIM_FLIGHT_MIN_SECONDS` / `SIM_FLIGHT_MAX_SECONDS` | 30 / 90 | Duration of a complete mission at 0 km and at the distance budget |
| `SIM_CHARGE_RATE_PCT_PER_MINUTE` | 20 | Charging speed of a docked drone |
| `SIM_HEARTBEAT_STALE_SECONDS` | 10 | Maximum heartbeat age for a mission to start |
| `DISPATCH_AUTO_INTERVAL_SECONDS` | 3 | Interval between automatic dispatch passes |
| `ORDER_SIM_MIN_INTERVAL_SECONDS` / `ORDER_SIM_MAX_INTERVAL_SECONDS` | 15 / 30 | Random pause between generated orders |
| `INCIDENT_SIM_MIN_INTERVAL_SECONDS` / `INCIDENT_SIM_MAX_INTERVAL_SECONDS` | 180 / 300 | Random pause between random incident attempts |
| `DRONE_RECOVERY_DELAY_SECONDS` | 120 | Delay before a drone grounded by a failure is recovered to a Hub |

## Simulation reference

These are simulation assumptions, not certified aircraft performance.

- **Drone model:** there is a single model, the SkyFleet SF-1 Courier, an electric quadcopter:
  - 3.0 kg maximum payload
  - 20 km maximum range, with a 14 km mission budget for the whole route including the return
  - 45 km/h cruise speed
  - 20% minimum battery reserve
- **Energy:** an empty drone uses `100 / max_range_km` % of battery per km. A loaded drone uses that
  rate × (1 + `MISSION_PAYLOAD_ENERGY_FACTOR` × weight / max payload); the factor defaults to 0.5. The
  eligibility check assumes the worst case, where the parcel stays on board for the whole route, and
  requires that worst case plus the reserve.
- **Flight time:** `min + (max − min) × min(route km / budget km, 1)` seconds. Position and battery are
  computed from the stored schedule and the clock.
- **Docking and capacity:** a drone counts as docked when it is not `IN_FLIGHT` or `MAINTENANCE` and is
  within `HUB_DOCK_PROXIMITY_M` (50 m) of a Hub. About 60 m before landing, the worker locks the Hub
  row and counts the docked drones. If the Hub is full, the drone diverts to the nearest reachable Hub
  with a free place. If no Hub can be reached safely, the flight ends as a simulated emergency.

Each feature's detailed rules, error codes and limitations are in its specification in
[`docs/features/`](features/), and the confirmed business behaviour is in
[`context/business-rules.md`](../context/business-rules.md).

## Tests and quality checks

```bash
# backend/
uv run pytest                 # SQLite; needs neither Docker nor PostgreSQL
uv run pytest -m postgres     # opt-in tests against a temporary PostgreSQL database
uv run ruff check .
uv run ruff format --check .
uv run mypy app tests

# frontend/
npm run lint                  # oxlint
npm run typecheck
npm run test                  # Vitest + React Testing Library
npm run format:check          # Prettier
npm run build
```

The default backend suite runs on SQLite, so it does not exercise PostgreSQL-specific behaviour such
as row locking. The opt-in `postgres` tests cover that.

## Code map

### Backend (`backend/`)

| Path | Responsibility |
|---|---|
| `app/main.py` | FastAPI app; registers the routers under `/api` |
| `app/worker.py` | Simulation Worker entry point (separate process; writes a heartbeat) |
| `app/api/routes/` | Thin HTTP handlers; no business logic |
| `app/hubs/`, `app/drones/`, `app/orders/` | Entities, repositories, services and seeds; `orders/` also has the generator, delivery destinations, feasibility and cancellation |
| `app/missions/` | Mission planning, routing, energy, Hub capacity and presence, takeoff |
| `app/dispatch/` | Deterministic dispatch, automatic mode, fleet rebalancing |
| `app/simulation/` | Worker logic: flights, charging, failures and recovery, failed delivery, LPR helicopter, relocation, random incidents |
| `app/events/` | Append-only operational event log |
| `app/weather/` | Rain warning and the pre-takeoff check |
| `app/ai/`, `app/fleet_context/`, `app/copilot/` | AI gateway and budget, the read-only fleet snapshot, the Copilot endpoint and its access control |
| `app/db/`, `app/config.py` | Database session; settings from environment variables |
| `migrations/` | Alembic migrations |
| `tests/` | Pytest suite |

### Frontend (`frontend/src/`)

| Path | Responsibility |
|---|---|
| `api/` | Typed HTTP client and one module per backend resource |
| `features/data/` | Shared polling and request hooks; intervals in `polling.ts` |
| `features/map/`, `hubs/`, `drones/`, `orders/`, `flights/`, `missions/` | Map layers, markers and detail panels |
| `features/operations/` | Operations panel and its tabs (lists, events, Copilot) |
| `features/dispatch/`, `orderSimulation/`, `incidents/`, `weather/`, `lpr/` | Simulation controls and incident displays |
| `features/management/` | Drone and order management |
| `features/drone3d/`, `telemetry/` | Three.js drone viewer and simulated telemetry |
| `features/copilot/` | Copilot chat; the access token is kept in memory only |
| `features/system-status/` | Backend and worker status |

### Finding the reasoning behind a behaviour

1. [`context/business-rules.md`](../context/business-rules.md): what the business confirmed.
2. [`docs/decisions/`](decisions/): why it was built that way (ADRs).
3. [`docs/features/`](features/): the numbered feature specification and its implementation record.
4. [`context/progress-tracker.md`](../context/progress-tracker.md): status and known limitations.

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
(so changing SF-1 values later needs a migration). Hub capacity means the number of drones
*assigned* to a Hub regardless of flight status, and it is enforced **only while seeding**; no
runtime check exists yet.

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

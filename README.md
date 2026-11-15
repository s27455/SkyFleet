# SkyFleet

SkyFleet is an operations platform for a fictional autonomous drone delivery company in the Tricity
area (Gdańsk, Sopot, Gdynia). Parcels are handed over at Mall Pickup Hubs and flown to customer
addresses by a simulated drone fleet. Operators watch the fleet on a live map, manage orders and
drones, respond to incidents, and can ask a read-only AI Copilot about the current fleet state.

It was built as a full-stack recruitment project. The emphasis is on a clear architecture: the
backend owns all operational state, a separate worker process runs the simulation, and dispatch and
safety rules are deterministic and tested. The frontend only displays what the backend reports.

## What it does

- **Live operations map** (Mapbox GL JS): Hubs with docked-drone counts, drones in flight that move
  smoothly between snapshots, and delivery destinations with their status.
- **Mission lifecycle:** each order gets an eligibility check (payload, route length, battery with a
  20% reserve, free place at the return Hub). The drone then takes off, delivers and returns to the
  nearest Hub with a free place. If the planned Hub fills up during the flight, the drone diverts to
  another one.
- **Automation the operator can switch on:** order generation, automatic dispatch with fleet
  rebalancing between Hubs, and random incidents. Docked drones charge automatically.
- **Incidents:** drone failure with a simulated emergency landing and later ground recovery,
  recipient unavailable (the parcel is returned to a Hub), an LPR medical helicopter with a moving
  no-fly zone, a rain warning that grounds takeoffs, and order cancellation that recalls the drone.
- **Operator tools:** drone and order management, manual drone relocation, an operational event log,
  a Three.js drone viewer with simulated telemetry.
- **AI Copilot (optional, off by default):** answers questions using a read-only snapshot of the
  fleet. It has no tools and cannot change state. Access requires a server-side token, and request
  rate and budget limits apply.

## Tech stack

- **Frontend:** React, TypeScript, Vite, Tailwind CSS v4, Mapbox GL JS, Three.js
- **Backend:** Python 3.13, FastAPI, Pydantic, SQLAlchemy 2, Alembic
- **Simulation Worker:** a separate Python process that shares the backend's domain modules
- **Database:** PostgreSQL 17
- **AI:** Anthropic API through a single backend gateway
- **Tooling:** uv, npm, Pytest, Vitest, Ruff, mypy (strict), oxlint, Prettier, Docker Compose

## Quick start (Docker Compose)

Requires only **Git** and **Docker Desktop** (start it first). No Python, Node.js or PostgreSQL is
needed on the host. The commands are for Windows PowerShell.

```powershell
git clone https://github.com/s27455/SkyFleet.git
cd SkyFleet
Copy-Item .env.example .env      # Compose reads .env, not .env.example
docker compose up --build
```

The first build downloads base images and dependencies and can take several minutes. Compose then
starts PostgreSQL and runs a one-shot `migrate` service: Alembic migrations, then the Hubs, 12 drones
and 11 sample orders. Rows that already exist are never changed. After that it starts the API, the
worker and the frontend.

- Dashboard: **http://localhost:5173**
- API documentation (Swagger): **http://localhost:8000/docs**

Order Simulation, Auto Dispatch and Random Incidents start **off**. Switch them on in the dashboard
to see the fleet operate on its own.

**Mapbox token.** `.env.example` includes a public demo Mapbox token, so the map works as soon as
`.env` is copied. You can replace `VITE_MAPBOX_TOKEN` in `.env` with your own **public** (`pk.`)
token from a free [Mapbox](https://account.mapbox.com) account. Never use a secret `sk.` token there.
The token is built into the frontend, so run `docker compose up --build` after changing it.

**Stopping.** Press `Ctrl+C` or run `docker compose down`. Data stays in the PostgreSQL volume
`skyfleet-db`, and `docker compose up` starts again where you left off (add `--build` after pulling
code changes). Only `docker compose down -v` deletes the data.

**Troubleshooting**

- *Port already allocated (5173, 8000 or 55432):* stop the program using it, for example a natively
  running SkyFleet. Alternatively, set `FRONTEND_PORT`, `API_PORT` or `DB_PORT` in `.env` and run
  `docker compose up --build`.
- *"Map unavailable" or a blank map:* `.env` is missing, or `VITE_MAPBOX_TOKEN` in it is empty or
  invalid. Fix it, then run `docker compose up --build`.
- *Backend unreachable, or the API and worker did not start:* `docker compose ps` shows each service's
  state. `docker compose logs migrate`, `docker compose logs api` and `docker compose logs worker` show
  the cause.
- *"The simulation worker is not running…":* check `docker compose logs worker`. In Docker the worker
  starts automatically, so ignore the native `uv run` hint in that message.

## Architecture

```
Browser (React)  --REST polling-->  FastAPI API  --+
                                                   +-->  PostgreSQL
                  Simulation Worker (own process) -+
```

- **The backend is the source of truth.** Orders, drones, missions, Hub capacity, charging,
  incidents and simulation state live in PostgreSQL. The API validates and changes them through
  domain services; route handlers stay thin.
- **The Simulation Worker runs independently.** It is a separate process that ticks every second. On
  each tick it advances flights, charges drones, runs automatic dispatch and order generation,
  triggers random incidents, and recovers failed drones. It does not need an open browser. Flight
  progress is computed from stored schedules and the clock, so restarting the worker neither resets
  nor invents progress.
- **The backend layout is a modular monolith.** Each domain module (`hubs`, `drones`, `orders`,
  `missions`, `dispatch`, `simulation`, `events`, `weather`, `ai`, `copilot`) has its own models,
  repository and services. There are no microservices or message brokers.
- **Deterministic rules, not AI, decide operations.** Eligibility, dispatch, landing capacity (checked
  under a row lock on the Hub) and state transitions are plain, tested code. The LLM only explains
  and summarises.
- **The browser polls for real-time updates** (flights every 1 s, the rest every 2 s) instead of using
  WebSocket, a deliberate MVP trade-off
  ([ADR 0015](docs/decisions/0015-frontend-polling-instead-of-websocket.md)).

The full design is in [`context/architecture-context.md`](context/architecture-context.md). The
reasons behind individual decisions are recorded as ADRs in [`docs/decisions/`](docs/decisions/).

## AI Copilot (optional)

The Copilot is **disabled by default**, and the rest of the application works fully without it. The
repository contains no Anthropic API key or other private credentials. To enable it, add these
values to `.env`, then run `docker compose up -d api`:

```
SKYFLEET_AI_ENABLED=true
ANTHROPIC_API_KEY=<your key>
SKYFLEET_AI_ACCESS_TOKEN=<at least 32 characters; typed into the Copilot panel>
```

These values are passed to the API container only, never to the frontend. The backend enforces a
request rate limit and a spending ceiling
([ADR 0012](docs/decisions/0012-ai-foundation-and-cost-guardrails.md),
[ADR 0014](docs/decisions/0014-ai-copilot-access-and-endpoint.md)).

## Documentation

- [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md): native setup with hot reload, configuration, tests
  and quality checks, a code map, and simulation reference values
- [`context/project-overview.md`](context/project-overview.md): product vision and scope
- [`context/business-rules.md`](context/business-rules.md): confirmed business rules and open
  questions
- [`context/architecture-context.md`](context/architecture-context.md): system architecture
- [`context/progress-tracker.md`](context/progress-tracker.md): roadmap, status and known limitations
- [`docs/decisions/`](docs/decisions/): architecture decision records
- [`docs/features/`](docs/features/): numbered feature specifications, each with its implementation
  record
- [`docs/diagrams/skyfleet-main-process.svg`](docs/diagrams/skyfleet-main-process.svg): the main
  delivery process (BPMN)

SkyFleet was developed with Claude Code. [`CLAUDE.md`](CLAUDE.md),
[`context/ai-workflow-rules.md`](context/ai-workflow-rules.md),
[`context/code-standards.md`](context/code-standards.md) and
[`context/ui-context.md`](context/ui-context.md) are the instructions and standards used during
development.

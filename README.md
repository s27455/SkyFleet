# SkyFleet

SkyFleet is a control center for a fictional drone delivery company operating in the Tricity area
of Poland (Gdańsk, Sopot and Gdynia). Partner parcels are handed over at Mall Pickup Hubs and flown
to customer addresses by a fleet of autonomous drones. The fleet runs in a continuous simulation.

The application shows the whole operation on a live map: orders arriving, drones taking off and
landing, batteries charging and incidents unfolding. The operator decides how much runs on its own.
Everything happens in the backend, so the simulation keeps running whether or not anyone has the
dashboard open.

SkyFleet is a full-stack recruitment project. It is built to show a clean, testable architecture
behind a polished, map-first interface.

## Features

**A live operations map.** The dark Mapbox map shows the four Hubs with their docked-drone counts,
drones in flight moving along their routes, and delivery destinations coloured by status. Selecting
any Hub, drone or order opens a detail panel. A drone's panel includes a Three.js model and simulated
telemetry.

**Orders and fleet management.** You can create, edit, cancel and delete orders, add or remove
drones, and move a docked drone to another Hub. Cancelling an order whose drone is already airborne
recalls the drone.

**Dispatch and missions.** With Auto Dispatch on, the backend matches ready orders with suitable
docked drones. A drone is suitable when it can carry the parcel, the route is within range, the
battery covers the trip plus a 20% reserve, and the return Hub has a free place. Each drone then
takes off, delivers and returns to the nearest Hub with room. If that Hub fills up during the
flight, the drone diverts to another one. The same pass rebalances idle drones between Hubs.
Missions can also be assigned manually through the REST API and started from the dashboard.

**A simulation you can switch on and off.** Order Simulation generates a steady stream of new
orders. Docked drones charge automatically. Each automation has its own switch, so you can watch
one mission in detail or let the whole network run.

**Incidents and operational status.** From the Scenarios menu, or automatically with Random
Incidents on, you can trigger:
- a drone failure with a simulated emergency landing (a ground crew later recovers the drone)
- an unavailable recipient (the parcel goes back to a Hub)
- an LPR medical helicopter whose no-fly zone moves across the city and holds nearby drones
- a rain warning that grounds every takeoff

Alerts, an event timeline and backend and worker status indicators show what needs attention.

**An optional AI Copilot.** Ask questions in plain English, such as "Which drones are low on
battery?" or "Which Hub has the most drones ready to fly?". The answers are based on a read-only
snapshot of the fleet's current state. The Copilot has no tools and cannot change anything.

## Tech stack

- **Frontend:** React, TypeScript, Vite, Tailwind CSS v4, Mapbox GL JS, Three.js
- **Backend:** Python 3.13, FastAPI, Pydantic, SQLAlchemy 2, Alembic
- **Simulation Worker:** a separate Python process that shares the backend's domain modules
- **Database:** PostgreSQL 17
- **AI:** Anthropic Claude, called only from the backend
- **Quality and tooling:** Pytest, Vitest, Ruff, mypy (strict), oxlint, Prettier, uv, Docker Compose

## Quick start

All you need is **Git** and **Docker Desktop**. Python, Node.js and PostgreSQL run inside the
containers.

```powershell
git clone https://github.com/s27455/SkyFleet.git
cd SkyFleet
Copy-Item .env.example .env      # macOS/Linux: cp .env.example .env
docker compose up --build
```

The included configuration is ready for a local demo, including the map. The first build takes a
few minutes. After that, Compose creates the database schema, loads the Hubs, 12 drones and 11
sample orders, and starts the API, the simulation worker and the frontend.

- Dashboard: **http://localhost:5173**
- API documentation: **http://localhost:8000/docs**

The automations start switched off. Turn on **Order Simulation** and **Auto Dispatch** in the
dashboard to see the fleet go to work, and add **Random Incidents** when you want something to go
wrong.

To stop, press `Ctrl+C` or run `docker compose down`. The data is kept in a Docker volume, so the
next `docker compose up` continues where you left off. `docker compose down -v` starts from scratch.

If something does not start:
- *A port is already in use (5173, 8000 or 55432):* stop the program using it, or set
  `FRONTEND_PORT`, `API_PORT` or `DB_PORT` in `.env` and run `docker compose up --build`.
- *The map does not appear:* make sure `.env` was created from `.env.example`, then rebuild with
  `docker compose up --build`.
- *The dashboard cannot reach the backend:* `docker compose ps` shows each service's state, and
  `docker compose logs migrate`, `docker compose logs api` and `docker compose logs worker` show the
  reason.

## Architecture

```
React frontend  --REST polling-->  FastAPI API  ----------+
                                     |                    +--> PostgreSQL
                                     +--> AI Copilot      |
                                          (optional)      |
                 Simulation Worker (separate process) ----+
```

The **frontend** displays state and sends operator commands. It holds no business logic and polls
the API: flights every second, everything else every two seconds.

The **FastAPI backend** owns the operational state. Route handlers stay thin. Each domain module
(Hubs, drones, orders, missions, dispatch, simulation, events, weather, AI) has its own models and
services, which makes the codebase a modular monolith rather than a set of services.

The **Simulation Worker** runs in a separate process, independent of the API. Every second it
advances flights, charges drones, and runs dispatch, order generation, random incidents and drone
recovery. API requests never wait on the simulation, and the simulation never waits on a browser.
Flight progress is calculated from stored schedules and the clock, so a restart neither loses nor
invents progress.

**PostgreSQL** is the single source of truth shared by both processes. Rules that must hold under
concurrency are enforced there. For example, Hub capacity is checked under a row lock at landing,
so two drones cannot take the last free place.

**Operational decisions are deterministic.** Eligibility, dispatch, routing, energy and state
transitions are ordinary, tested code. The **AI Copilot** sits alongside them: it receives a
read-only snapshot and can only explain.

The full design is in [`context/architecture-context.md`](context/architecture-context.md), and the
reasons behind each decision are recorded as ADRs in [`docs/decisions/`](docs/decisions/).

## AI Copilot (optional)

The Copilot is turned off in the Docker demo, and the rest of the application works fully without
it. The repository does not include an Anthropic API key, so you need your own key to use it. Set
`SKYFLEET_AI_ENABLED=true`, `ANTHROPIC_API_KEY` and `SKYFLEET_AI_ACCESS_TOKEN` in `.env`, then run
`docker compose up -d api`. The access token must be at least 32 characters; you type it into the
Copilot panel. These values reach the API container only, never the browser. The backend enforces a
request rate limit and a spending ceiling. See
[ADR 0012](docs/decisions/0012-ai-foundation-and-cost-guardrails.md) and
[ADR 0014](docs/decisions/0014-ai-copilot-access-and-endpoint.md) for details.

## Documentation

- [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md): native setup with hot reload, configuration, tests,
  a code map and simulation reference values
- [`context/project-overview.md`](context/project-overview.md): product vision and scope
- [`context/business-rules.md`](context/business-rules.md): business rules behind the simulation
- [`context/architecture-context.md`](context/architecture-context.md): system architecture
- [`docs/decisions/`](docs/decisions/): architecture decision records
- [`docs/features/`](docs/features/): feature specifications, each with its implementation record
- [`docs/diagrams/skyfleet-main-process.svg`](docs/diagrams/skyfleet-main-process.svg): the main
  delivery process as a BPMN diagram
- [`context/progress-tracker.md`](context/progress-tracker.md): project history and known
  limitations

SkyFleet was built with Claude Code as a development partner. [`CLAUDE.md`](CLAUDE.md) and the
other files in [`context/`](context/) are the instructions and standards that guided that work.

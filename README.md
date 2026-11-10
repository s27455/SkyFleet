# SkyFleet

**Autonomous Urban Drone Delivery & AI Operations Platform** — a simulated drone logistics network
operating across the Tricity area (Gdańsk, Sopot, Gdynia), with a map-first operations dashboard, a
backend-owned continuously running simulation, and an AI Fleet Operations Agent.

> Status: **Phase 1 — runnable skeleton.** See [`progress-tracker.md`](progress-tracker.md).

## Architecture at a glance

| Part | Tech | Location |
|---|---|---|
| Frontend (operations dashboard) | React, TypeScript, Vite, Tailwind CSS v4 (Mapbox GL JS in Phase 2) | `frontend/` |
| Backend API | Python 3.13, FastAPI, Pydantic | `backend/app/main.py` |
| Simulation Worker | Separate Python process sharing backend modules | `backend/app/worker.py` |
| Database (from Phase 3) | PostgreSQL via Docker Compose | `docker-compose.yml` |

The backend owns all operational state; the frontend only displays it. The worker runs independently
of any browser session. Details: [`architecture-context.md`](architecture-context.md) and
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
cp .env.example .env.local   # optional: defaults work for local development
```

## Running locally

Run each in its own terminal:

| Process | Command (from) | URL |
|---|---|---|
| API | `uv run uvicorn app.main:app --reload` (`backend/`) | http://localhost:8000 — OpenAPI docs at `/docs` |
| Simulation Worker | `uv run python -m app.worker` (`backend/`) | logs ticks to the console |
| Frontend | `npm run dev` (`frontend/`) | http://localhost:5173 |
| Database *(Phase 3+)* | `docker compose up -d db` (repo root) | localhost:5432 |

The dashboard header shows **Backend connected** / **Backend unreachable**, which also confirms CORS
is configured correctly.

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
docs/       Architecture decision records (decisions/) and feature specs (features/)
*.md        Project context documents (overview, architecture, standards, UI, workflow, progress)
```

## Project documentation

- [`project-overview.md`](project-overview.md) — product vision and scope
- [`architecture-context.md`](architecture-context.md) — system architecture
- [`code-standards.md`](code-standards.md) — coding conventions
- [`ui-context.md`](ui-context.md) — UI/UX direction
- [`ai-workflow-rules.md`](ai-workflow-rules.md) — AI-assisted development workflow
- [`progress-tracker.md`](progress-tracker.md) — roadmap and status
- [`CLAUDE.md`](CLAUDE.md) — Claude Code project instructions

# Feature 003 — Hubs Backend API

**Project:** SkyFleet — Autonomous Urban Drone Delivery & AI Operations Platform  
**Status:** Complete — approved by the project owner  
**Scope:** Backend only  
**Implementation:** Complete. Not committed.  
**Verification:** 21 backend tests, `ruff check`, `ruff format --check` and strict `mypy` pass; the existing frontend lint, typecheck, tests, format check and build pass (no frontend files changed). Manual check against PostgreSQL 17 in Docker Compose (host port 55432): migration, seed run twice (4 inserted, then 0), both endpoints including the 404, CHECK constraints, a downgrade/upgrade cycle, and data persistence across `docker compose restart` and `down`/`up`. `qa-tester` and `code-reviewer` subagents were run twice; the final passes reported no blockers.

## Goal

Introduce the first working FastAPI backend slice: a persistent, read-only API exposing the four SkyFleet drone Hubs. This establishes a reliable source of truth for Hub data without changing the existing map UI.

## Business context

A Hub is both a partner parcel handover location and a drone base for storage, charging, and service. There is no separate `DroneBase` entity. Hub capacity represents **maximum drone count**, not parcel count. The default capacity is **50 drones**. Partners are not permanently assigned to Hubs.

## User value

The platform gains a stable API for discovering Hub locations and properties, ready for later frontend integration and fleet operations.

## Functional requirements

1. Establish a minimal modular-monolith FastAPI application consistent with `CLAUDE.md`, `context/architecture-context.md`, and `context/code-standards.md`. Reuse existing backend scaffolding if present; do not duplicate it.
2. Define a persisted `Hub` model and appropriate Pydantic response schema with at least: stable ID, name, address, longitude, latitude, and drone capacity (default 50). Additional fields only if justified by existing conventions. Avoid derived live operational values (e.g. occupied slots, online drones) until drone state exists.
3. Persist and seed the following four Hubs, idempotently, without duplicates:

   | Hub | Address | Longitude | Latitude |
   | --- | --- | ---: | ---: |
   | Galeria Bałtycka | al. Grunwaldzka 141, Gdańsk | 18.6006944 | 54.3826244 |
   | Forum Gdańsk | Targ Sienny 7, Gdańsk | 18.643527 | 54.349346 |
   | Centrum Riviera | Kazimierza Górskiego 2, Gdynia | 18.5317863 | 54.5046621 |
   | Centrum Handlowe Osowa | Spacerowa 48, 80-299 Gdańsk | 18.49097 | 54.42569 |

   Use longitude/latitude consistently; never silently swap them. Keep names and coordinates consistent with the finalized Feature 002 implementation, resolving any discrepancy during planning.
4. Implement `GET /api/hubs` returning a deterministic list of all Hubs and `GET /api/hubs/{id}` returning one Hub or a proper 404 response.
5. Provide a documented local development workflow for starting the API, preparing the database, and seeding Hubs. Choose a lightweight local persistence solution appropriate to the current repository; discuss the choice in the plan before implementation. Do not introduce production infrastructure.
6. Include appropriate CORS configuration only if needed for future local frontend access, using narrowly scoped development origins rather than unrestricted production defaults.

## Non-functional requirements

- Python, FastAPI, Pydantic, SQLAlchemy; follow existing project conventions and dependency management.
- Separate HTTP routing, domain/data model, persistence, and seed logic in a simple, understandable structure. Avoid premature abstraction.
- API response contracts are typed and predictable.
- No secrets or local database files committed to Git.
- Tests run locally without external services.

## Acceptance criteria

- [x] Backend can be started using documented commands.
- [x] Database schema can be created reproducibly using the chosen local setup.
- [x] Seed operation can be run twice without duplicate Hub records.
- [x] `GET /api/hubs` returns exactly the four specified Hubs in a stable order, with correct coordinates and capacity 50.
- [x] `GET /api/hubs/{id}` returns the correct Hub for a valid ID.
- [x] Unknown Hub ID returns HTTP 404 with a useful error response.
- [x] Automated tests cover list, detail, missing ID, seed idempotency, and core Hub field validation.
- [x] Existing frontend behavior remains unchanged and its checks continue to pass if applicable.
- [x] QA and code review are completed using the project's actual subagents when available; any invocation failure is reported explicitly.
- [x] Documentation and progress tracker are updated only after implementation and verification.

## Explicitly out of scope

- Connecting frontend map markers to the API or deleting frontend mock data.
- Hub CRUD, authentication, partner-facing APIs, or admin editing.
- Drones, drone assignments, occupied capacity, charging, maintenance, telemetry, or repositioning.
- Orders, parcel handover, delivery, dispatch, simulation worker, WebSockets, incidents, AI agent.
- External mapping, weather, aviation APIs, deployment, Docker orchestration, microservices.

## Implementation workflow

1. Read `CLAUDE.md`, this specification, and only the relevant context and repository files.
2. Invoke `task-planning`; inspect the actual repository and propose a small implementation plan, including database choice and testing strategy. **Wait for user approval.**
3. After approval, invoke `task-implementation` and implement only this feature.
4. Run backend tests and applicable lint/type checks; explicitly launch `qa-tester` and `code-reviewer` subagents using their corresponding skills if available. Report actual invocations, not just intended use.
5. Address valid in-scope findings, rerun checks, and use `documentation-update` only when the feature is verified and approved for finalization.
6. Do not commit, push, or begin the next feature without explicit user instruction.

## Open decisions for the planning stage

- Whether existing backend scaffolding and database tooling are already present.
- Lightweight local database selection (SQLite is acceptable for the MVP unless repository context suggests otherwise).
- Exact API schema field names and ID representation, consistent with the project code standards.

## Implementation notes (resolved decisions)

- **Database:** PostgreSQL 17 (ADR 0001), not SQLite. Dev instance in Docker Compose on host port 55432, named volume `skyfleet-db`. Backend tests use SQLite (in-memory, plus temp files for the migration test) and need no Docker; they do not exercise PostgreSQL itself.
- **IDs:** stable string slugs (e.g. `hub-forum-gdansk`), identical to the Feature 002 mock-data IDs.
- **Fields:** `id`, `name` (unique), `address`, `longitude`, `latitude`, `drone_capacity` (default 50), with CHECK constraints on coordinate ranges and positive capacity. The mock `city` and `status` fields are not provided by the API.
- **Structure:** flat `backend/app/hubs/` package (model, schema, repository, seed), `backend/app/db/session.py`, route in `backend/app/api/routes/hubs.py`, Alembic migration `0001` in `backend/migrations/`.
- **Seed:** `uv run python -m app.hubs.seed` inserts only missing Hubs and never modifies existing rows.
- **CORS:** unchanged; the Phase 1 allow-list already covers local frontend access.
- **Known limitations:** CORS `allow_methods` still lists write methods (Phase 1 scaffolding); overlapping concurrent seed runs could hit a primary-key conflict; no automated test runs against PostgreSQL.

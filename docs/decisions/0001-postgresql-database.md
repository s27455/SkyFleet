# ADR 0001 — PostgreSQL as the database

**Status:** Accepted (2026-11-11)

## Context

The API and the Simulation Worker are separate processes that both read and write operational
state. In deployment they will most likely run as separate services. `architecture-context.md` §13
left SQLite vs PostgreSQL open.

## Decision

Use **PostgreSQL** in both development and production. Locally it runs via `docker-compose.yml`
(database service only; the apps run natively for fast reloads). Access goes through SQLAlchemy,
with Alembic migrations introduced in Phase 3.

## Development setup (decided 2026-11-11)

- PostgreSQL 17 (`postgres:17-alpine`) runs in Docker Compose, service `db`.
- Host port **55432** maps to container port 5432. The default port 5432 is not used because a
  PostgreSQL installed on Windows already occupies it; that instance is never modified, stopped,
  or used by SkyFleet.
- Data persists in the named volume `skyfleet-db` (kept by `docker compose down`, removed by
  `docker compose down -v`).
- The FastAPI backend runs locally on Windows and connects via
  `postgresql+psycopg://skyfleet:skyfleet@localhost:55432/skyfleet` (`DATABASE_URL`).

## Consequences

- API and worker can share one database on any hosting provider (a SQLite file cannot be shared
  between separate PaaS services) and write concurrently without file locking issues.
- Same database engine in dev and prod — no dialect surprises at deployment time.
- Requires Docker locally from Phase 3 onwards, and a managed Postgres at deployment.

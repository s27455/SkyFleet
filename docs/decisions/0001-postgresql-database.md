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

## Consequences

- API and worker can share one database on any hosting provider (a SQLite file cannot be shared
  between separate PaaS services) and write concurrently without file locking issues.
- Same database engine in dev and prod — no dialect surprises at deployment time.
- Requires Docker locally from Phase 3 onwards, and a managed Postgres at deployment.

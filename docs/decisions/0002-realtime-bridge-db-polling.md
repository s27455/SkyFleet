# ADR 0002 — Worker-to-frontend real-time updates via DB polling

**Status:** Accepted in principle (2026-11-11); partly superseded by [ADR 0015](0015-frontend-polling-instead-of-websocket.md) (2026-11-15)

> **Superseded part:** the API-side broadcaster and the WebSocket push to the browser (second bullet
> of the Decision) were never built; the frontend polls REST endpoints instead (ADR 0015). **Still
> valid:** the worker persists state and events to the database and communicates with the API only
> through it; simulation control is stored in database state read by the worker. The text below is
> kept unchanged as historical context.

## Context

The Simulation Worker changes operational state, but WebSocket connections are held by the API
process. The architecture forbids introducing a message broker without a concrete need.

## Decision

- The worker persists state changes and `SystemEvent` records to the database.
- The API runs a lightweight background broadcaster that polls for new events / changed state
  (~1 s interval) and pushes them to connected WebSocket clients.
- Simulation control (pause/resume, including operator-approved AI actions) is written by the API to
  a `simulation_state` record that the worker reads every tick.

## Consequences

- No broker, no direct coupling between processes; the database is the single source of truth.
- Works the same locally and in deployment.
- Up to ~1 s extra latency — acceptable for an operations dashboard.
- PostgreSQL `LISTEN/NOTIFY` remains an optional later optimisation.

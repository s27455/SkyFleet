# ADR 0002 — Worker-to-frontend real-time updates via DB polling

**Status:** Accepted in principle (2026-11-11); implemented in Phase 7

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

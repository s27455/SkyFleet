# ADR 0015 — Frontend REST polling instead of WebSocket (MVP)

**Status:** Accepted (2026-11-15). Supersedes the WebSocket part of
[ADR 0002](0002-realtime-bridge-db-polling.md).

## Context

ADR 0002 planned that the worker persists state, and that the API process runs a broadcaster that
polls the database (about 1 s) and pushes changes to WebSocket clients. The original documents
(`CLAUDE.md`, `architecture-context.md`, `code-standards.md`) assumed WebSocket as the real-time
channel.

What was built: the browser re-reads REST resources on a timer. No WebSocket endpoint exists in the
backend and no WebSocket client exists in the frontend. The intervals live in
`frontend/src/features/data/polling.ts` (`POLL_INTERVALS_MS`): flights every 1000 ms (the worker
writes flight snapshots about once a second) and the fleet (drones, orders, missions) every 2000 ms;
one read times out after 10 s (`REQUEST_TIMEOUT_MS`). The shared hook is `usePolledResource`.
Until now this choice was not recorded as a decision.

## Decision

- For the MVP the frontend receives operational updates by **polling REST endpoints**. WebSocket is
  **not implemented** and is not planned before the delivery deadline.
- The worker still communicates with the API only through the database (the part of ADR 0002 that
  stays valid); there is no broker and no direct process coupling.
- The simulation never depends on an open browser; polling is a read-only view of persisted state.
- The backend remains the source of truth. Polling does not move any operational logic to the
  frontend.

## Consequences

Benefits:
- No connection management, reconnection logic or broadcaster process to build, test and keep alive.
- Every response is a complete, consistent snapshot, so a missed message cannot leave the UI wrong.
- Works unchanged through proxies and in local development; each endpoint stays testable by plain
  HTTP.
- Polling can be switched off in tests (`POLL_INTERVALS_MS`).

Costs and limits:
- Latency is up to one polling interval (about 1-2 s), acceptable for an operations dashboard.
- Constant request load while the dashboard is open, even when nothing changes.
- Bandwidth grows with the size of the polled snapshots (for example `GET /api/flights`
  accumulates emergency alerts, see Feature 022 limits).
- No server-initiated notification: events are shown when the next poll reads them.

## Revisit when

Update this ADR (or add a new one) if latency or load becomes a real problem, if more than one
operator must see changes in under a second, or if a feature needs server push. Options then: a
WebSocket or Server-Sent Events stream fed as ADR 0002 described (a lightweight API-side poller of
the database), or PostgreSQL `LISTEN/NOTIFY`. Add neither without a concrete requirement.

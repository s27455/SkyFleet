# Feature 015B — Automatic Order Generation

**Status:** Implemented and verified by automated tests; not committed. Acceptance criterion 9 (live demo of orders arriving) was not observed by the implementer. No QA or code-review agent run.  
**Project:** SkyFleet  
**Depends on:** Feature 015A — Order Generator Core

## Goal

Make SkyFleet continuously receive simulated customer orders without manual API calls. Extend the existing Simulation Worker to periodically invoke the 015A single-order generator. Keep the system small, safe, observable, and independent of Automatic Dispatch.

## Context

- 015A provides a curated, prevalidated route catalog and a service that creates exactly one `READY_FOR_PICKUP` order using the existing order creation flow.
- 014C provides an Automatic Dispatch ON/OFF mechanism and worker lifecycle/heartbeat conventions. 014D adds charging to the same worker.
- Orders are already consumed by the dispatch recommendation/execution pipeline; no change to mission planning or flight behavior is needed.
- The user will operate the generator through a frontend panel in **015C**, not in 015B.

## Required behavior

1. **Independent control:** Order Simulation has its own persisted ON/OFF state, separate from Automatic Dispatch. Default is OFF. Turning dispatch OFF does not stop order generation; turning order generation OFF does not stop flights, charging, or dispatch.
2. **Control API:** Provide minimal endpoints for current generator status and enable/disable actions. Follow existing 014C patterns where practical, but do not conflate the two modes.
3. **Worker-owned loop:** The existing Simulation Worker periodically checks the generator state and, when enabled, creates orders through the **015A generator service**. Do not duplicate order-creation logic or create a separate worker/service.
4. **Variable arrival times:** Generate at configurable, randomized intervals; suggested default **15–30 seconds** between successful generation opportunities. Do not generate a burst of backlogged orders after worker downtime, restart, or a long tick stall.
5. **Backpressure:** Pause generation when the number of outstanding simulated/ready orders reaches a configurable safe limit (suggested default **20**). Define and document the precise counting rule. Do not delete or cancel existing orders automatically. Avoid blocking manually created orders or changing dispatch FIFO behavior.
6. **Restart behavior:** The worker resets Order Simulation to OFF on startup, mirroring the safety behavior of 014C. API restart alone must not silently enable or disable it. Handle missing state as OFF. Do not create orders during startup or while disabled.
7. **Worker health:** Reject enable requests when the worker heartbeat is stale, using the existing worker-health mechanism if possible. The status response should make the mode and worker availability clear.
8. **Failures:** An order-generation error must not crash the worker, affect charging or flights, or create duplicate/partial orders. Log actionable errors without flooding logs; retry only on a later scheduled opportunity.
9. **Concurrency:** Do not generate duplicate orders because of overlapping ticks or concurrent enable/disable requests. Follow the project's single-worker assumption; no multi-worker scheduling framework is required. Respect OFF before creating an order.
10. **No changes to delivery semantics:** Generated orders remain ordinary `READY_FOR_PICKUP` orders, with the same validation, route catalog, IDs, persistence and dispatch eligibility as 015A.

## Suggested API contract (finalize during Initialize)

- `GET /api/orders/simulation/status` — `enabled`, `worker_running`, and minimal useful generation state (e.g. last generated timestamp / outcome), if straightforward.
- `POST /api/orders/simulation/enable` — enable order simulation; reject if worker unavailable.
- `POST /api/orders/simulation/disable` — disable order simulation.

These are suggestions, not a requirement to use these exact paths. Keep API shape consistent with the existing codebase. No frontend work in 015B.

## Implementation guidance

- **Initialize first:** audit 015A generator, 014C dispatch auto-state and worker reset, worker heartbeat, config, Alembic migrations, order statuses and existing test fixtures. Propose the smallest safe implementation and stop for approval.
- Prefer existing worker scheduling patterns, configuration and database-session conventions. A small state migration is acceptable if needed for durable ON/OFF; do not add a new queue, scheduler, broker or microservice.
- Decide whether interval configuration is environment-based in 015B, leaving UI rate controls for 015C. Make tests deterministic by injecting time/randomness where reasonable.
- Define whether the outstanding-order cap counts all `READY_FOR_PICKUP` orders or only simulation-created ones. **Prefer counting all READY_FOR_PICKUP orders for the MVP** unless the schema provides a reliable source distinction without a migration. State the consequence clearly.
- Prevent first-tick generation immediately after enabling unless explicitly justified. Do not retroactively catch up missed intervals.
- Recheck state close to the generation transaction to minimize a race with disabling. Avoid promising hard guarantees that require extra infrastructure.
- Minimize writes and logs when the generator is OFF or waiting.

## In scope

- Backend-only generator state and control endpoints.
- Integration into existing Simulation Worker.
- Configurable generation interval and outstanding-order limit.
- Focused unit, integration and PostgreSQL tests where appropriate.
- Concise documentation and progress tracker updates at Finish.

## Out of scope

- Frontend ON/OFF switch, frequency sliders and Generate Now button (**015C**).
- Advanced simulation scenarios and delivery exceptions (**016**).
- Changes to 015A catalog, mission planning, dispatch, charging or flight simulation unless a narrowly necessary bug fix is approved.
- New customer checkout UI, customer accounts, demand prediction, external event brokers, multi-worker orchestration, automatic cleanup of completed orders, or artificial demand optimization.

## Acceptance criteria

1. With Order Simulation OFF, no orders are generated automatically.
2. With Order Simulation ON and capacity available, the worker creates new ordinary orders over time using 015A; they appear through existing orders API/Management.
3. Intervals vary within configured bounds, and no catch-up burst occurs after a restart or stall.
4. Automatic Dispatch ON/OFF and Order Simulation ON/OFF operate independently; flights and charging continue as before.
5. When the outstanding-order cap is reached, generation pauses without deleting or modifying existing orders; generation resumes after the backlog drops.
6. Worker restart returns Order Simulation to OFF and does not create an unexpected order. Stale worker prevents enabling.
7. A generator error does not stop the worker or corrupt order data.
8. Tests cover state transitions, scheduling, cap behavior, restart, disabled behavior, worker health and integration with 015A. Existing backend tests, PostgreSQL tests, Ruff and mypy pass.
9. Live demo, with operator approval: enable via Swagger/API, observe several orders arriving in Management, disable and confirm arrivals stop. Optionally turn on Automatic Dispatch to observe consumption of the queue.

## Workflow

**Initialize → plan review/approval → Start Implementation → code review and live test → Finish.**

At **Initialize**, audit and propose the implementation, especially migration necessity, exact API paths, scheduling strategy, restart semantics and backlog counting. **Do not change code or the database, generate demo orders, or commit before approval.**

## Implementation summary

- **Mode:** migration `0007` creates `order_simulation_state` (single row `order-simulation`; a missing row means OFF); model `OrderSimulationState` in `backend/app/orders/models.py`. It is separate from `dispatch_auto_state`, so the two modes cannot affect each other.
- **Service:** `backend/app/orders/simulation.py` — `get_status`, `enable` (refused with `WorkerUnavailableError` on a stale heartbeat), `disable`, `reset_to_off`, `GenerationSchedule` and `run_generation_step`. The step re-reads the mode just before creating, calls the 015A `generate_one_order`, records a short outcome, and never raises for a generation error (the next scheduled opportunity retries; the error is logged once per change).
- **Scheduling:** only the next due time is kept, in worker memory; each pause is random within the configured bounds and counted from now. Enabling schedules the first order after a pause (none immediately), and a restart or long stall yields at most one order.
- **Worker:** `backend/app/worker.py` has its own startup reset to OFF, its own flag and its own `try/except`, independent of flights, charging and dispatch.
- **Backpressure:** the step pauses while the number of `READY_FOR_PICKUP` orders is at the limit (`count_ready_orders`). All such orders count, including seed and manual ones, and orders with an `ASSIGNED` mission count until takeoff. Nothing is deleted or changed.
- **Config:** `ORDER_SIM_MIN_INTERVAL_SECONDS` (15), `ORDER_SIM_MAX_INTERVAL_SECONDS` (30), `ORDER_SIM_MAX_OUTSTANDING_ORDERS` (20); the maximum must not be below the minimum.
- **API** (`backend/app/api/routes/order_simulation.py`): `GET /api/orders/simulation/status` (`enabled`, `worker_running`, `last_check_at`, `last_outcome`, `outstanding_orders`, `max_outstanding_orders`), `POST /api/orders/simulation/enable` (503 `SIMULATION_WORKER_UNAVAILABLE` while the worker is stale) and `POST /api/orders/simulation/disable`. `_worker_unavailable` moved from `routes/dispatch.py` to `backend/app/api/errors.py` without a behaviour change.

## Verification

- Backend: ruff and mypy pass; full suite 458 passed; PostgreSQL suite (`-m postgres`) 28 passed, including 8 simultaneous first-ever enables leaving exactly one row and distinct orders from repeated steps.
- Tests cover settings, OFF by default, idempotent toggles, stale-heartbeat refusal, worker reset, schedule bounds and the no-burst rule, the cap (pause and resume), a mode switched off mid-step, generator failure, the real worker loop (reset, schedule, then one order), API behaviour, independence from Automatic Dispatch, and migration `0007`.
- Live attempt: the first `POST /enable` returned 500 because the development database was still at revision 0006 (table missing) — an environment issue, not a code defect. After `uv run alembic upgrade head` (now 0007), `GET /api/orders/simulation/status` returned 200 with the mode OFF. The demo of several orders arriving and stopping after disable has not been observed by the implementer.

## Known limitations

- Run `uv run alembic upgrade head` before using the endpoints; while the table is missing the worker logs a traceback on every tick and `POST /enable` returns 500.
- A disable can lose to an order already being created; that order is an ordinary valid order.

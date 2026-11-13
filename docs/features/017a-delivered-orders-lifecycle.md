# Feature 017A — Delivered Orders Lifecycle

**Project:** SkyFleet  
**Status:** Implemented and approved by the owner (2026-11-13); committed in `59d4d74`. See section 11 for what was built and what was not verified.  
**Priority:** High  
**Scope:** Order visibility and lifecycle in operational views  
**Dependencies:** Existing order API, persisted order status/timestamps, frontend polling  
**Follow-up:** 017B — Delivery Marker States

## 1. Problem

Completed deliveries remain indefinitely visible in the operational UI. After many simulation cycles, the interface accumulates large numbers of `DELIVERED` orders, making active work difficult to monitor. Delivery-address markers also accumulate on the map; marker appearance and removal will be handled in Feature 017B.

## 2. Goal

After an order becomes `DELIVERED`, keep it visible in the active operational interface for **120 seconds** from the **actual delivery time**. Once that window expires, automatically remove it from active operational views while retaining the order and its relationships in PostgreSQL for history and future analytics.

This is **logical archiving by visibility**, not a new archive database, archive table, or physical deletion.

## 3. User experience

1. An order is pending or being delivered and remains visible in the operational UI.
2. The backend records successful delivery; the order status becomes `DELIVERED`.
3. For 120 seconds after delivery, the order remains visible with an explicit `DELIVERED` label.
4. After 120 seconds, the order disappears from active operational lists automatically, without requiring a page reload.
5. Refreshing or reopening the application does not bring back orders whose visibility window has expired.
6. Historical order records remain stored and available for future analytics; this feature does **not** require a new archive screen.

## 4. Functional requirements

### FR-01 — Persisted delivery time

- Determine whether the existing backend already persists a reliable delivery-completion timestamp (e.g., `delivered_at` or a suitable terminal-status event timestamp).
- Use that persisted timestamp as the sole reference for the 120-second window.
- Do **not** start the countdown when the frontend first observes `DELIVERED`.
- If no suitable timestamp exists, propose the smallest safe backend/schema change to persist it; inspect the existing order and mission state transitions before implementation.

### FR-02 — Visibility rule

An order is visible in active operational views when:

- Its status is not `DELIVERED`; or
- Its status is `DELIVERED` and the delivery-completion timestamp is within the past 120 seconds.

An order is excluded from active operational views when it is `DELIVERED` and the 120-second window has elapsed.

Other terminal states (cancelled, failed, etc.), if present, retain their existing behavior unless explicitly agreed in a later feature.

### FR-03 — Consistent filtering

- Apply the rule consistently to the active orders list and any active-order counts or summaries that are intended to represent the operational queue.
- Prefer a shared selector/filter or a clearly defined API query contract over duplicated UI-specific conditions.
- Ensure order visibility changes as time advances, even if the underlying API response remains unchanged; reuse existing polling or an appropriate lightweight scheduling mechanism, without adding high-frequency polling.
- Do not remove an order from backend storage.

### FR-04 — History integrity

- Preserve order IDs, delivery statuses, timestamps, mission/flight relationships and other historical data.
- Do not delete or reseed records to clean up the UI.
- If the API is filtered server-side, retain a way for existing consumers or future analytics to access complete historical records. Avoid silently changing an endpoint's semantics if other consumers depend on it.

### FR-05 — Preparation for 017B

- Expose or document a reusable visibility rule so Feature 017B can remove delivery-address diamonds on the same 120-second schedule.
- Actual marker recoloring, marker removal and map legend changes are **out of scope for 017A**.

## 5. Non-functional requirements

- No new dependencies unless clearly justified.
- No new archive table, separate archive database, physical deletion or background cleanup job.
- Existing dispatch, charging, mission and order-generation behavior must remain unchanged.
- Handle backend timestamps and client clock differences consistently; prefer server-side filtering if clock skew would materially affect correctness.
- Keep changes small and testable.

## 6. Edge cases

- **Refresh/restart:** an already-expired delivered order stays hidden.
- **Delayed polling:** an order first observed after its 120-second window is already expired and must not appear briefly.
- **Missing delivery timestamp:** do not invent a timestamp from first render; establish explicit safe behavior and cover it with tests.
- **Timestamp boundary:** define the cutoff precisely (`now >= delivered_at + 120s` means hidden).
- **Active order updates:** filtering must not break currently selected orders, live mission tracking or unrelated UI.
- **Clock skew/time zones:** use timezone-aware timestamps and a consistent reference clock.
- **Large history:** hundreds of completed orders should not clutter active views or cause avoidable frontend work.

## 7. Implementation approach — to validate during Initialize

1. Audit order schema, statuses, terminal transitions, existing timestamps, API response shapes and frontend data flow.
2. Select the minimal safe source of truth for delivery time.
3. Implement one shared active-order visibility policy, ideally reusable by the map in 017B.
4. Update active order views and operational counts without altering historical persistence.
5. Add unit, API/integration and UI regression tests as appropriate.
6. Confirm behavior with real local data, including older delivered orders; avoid resetting the database.

**Architectural decision is intentionally open:** Claude Code should determine whether server-side filtering, client-side filtering, or a compatible combination best fits the existing implementation. Do not introduce an unnecessary migration or change API contracts without auditing consumers.

## 8. Acceptance criteria

- [x] A newly delivered order remains visibly marked `DELIVERED` for 120 seconds after its persisted delivery time. (Rule and API tested at 119 s; the full live 120 s flow was not observed by the implementer.)
- [x] The order disappears automatically from active operational views at or after the cutoff. (Tested at 120 s and 121 s; a frontend test shows an order dropping out on the next poll.)
- [x] Previously delivered orders older than 120 seconds are hidden immediately after loading the app. (Server-side filter; the 84 older delivered orders in the dev database were backfilled with a delivery time.)
- [x] Orders still pending or in progress remain visible.
- [x] Historical rows and related missions/flights remain intact in PostgreSQL. (Nothing deleted; the unfiltered endpoint and Management → All return full history.)
- [x] Existing dispatch, delivery simulation and charging workflows are unaffected. (Full backend suite passes; dispatch regression test added.)
- [x] Active counters and lists remain internally consistent. (All use the one active answer.)
- [x] The 120-second visibility rule is reusable by 017B.
- [x] Automated tests cover timing boundaries, refresh, missing timestamps and mixed-status datasets.
- [ ] Frontend checks and relevant backend tests pass; manual smoke test confirms the behavior. (Checks pass; the owner confirmed the app works after restarting a stale dev server, but the delivery-to-disappearance flow over about 120 s was not observed by the implementer.)

## 9. Out of scope

- Changing delivery-address marker colors or removing diamonds from the map (**017B**).
- Changing generated delivery coordinates or nearest-hub return routing (**017C**).
- Building a history/archive screen, analytics dashboard or export.
- Deleting historical orders or implementing retention policies.
- New exception-handling scenarios.

## 10. Definition of done

Implementation is reviewed in the running application, acceptance criteria pass, documentation/progress tracker are updated, and the change is committed only after explicit approval through the existing Feature Initialize → Start Implementation → visual review → Finish workflow.

## 11. Implementation notes (verified)

**Backend**

- `orders.delivered_at`: nullable, timezone-aware. Migration `0009` adds it and backfills `DELIVERED` orders from `mission_flights.delivered_at`; a delivered order with no flight row stays `NULL`. The downgrade drops the column.
- The flight engine sets `order.delivered_at` to the real UTC time at which it commits the `DELIVERED` transition (the tick's `now`). `flight.delivered_at` keeps its meaning as the flight's scheduled timeline instant and is not the visibility reference. Rows backfilled by migration `0009` and the later one-off repairs use the flight's time, the best value available for them. A first version copied the flight's instant; it was changed after a worker running old code, and the case of a late worker, showed that a scheduled time can already be past the window when the transition is committed.
- The rule is in `app/orders/visibility.py`: a `DELIVERED` order is visible while `now < delivered_at + window`; at `now >= delivered_at + window` it is hidden; a `DELIVERED` order with no delivery time is hidden. Other statuses are always visible.
- The window is `ORDER_DELIVERED_VISIBILITY_SECONDS` (default 120).
- `repository.list_active_orders` applies the rule in SQL.
- `GET /api/orders` is unchanged (full history). `GET /api/orders?active=true` returns the active view. `OrderResponse` gained `delivered_at` (nullable).
- Dispatch still reads the full order list.

**Frontend**

- `getActiveOrders` (`?active=true`) feeds the map markers, the orders list, the counters and the drone inspector through `useOrders`. The existing 2 s poll removes an expired order; the client clock is not used. `getOrders` still means full history.
- Management → Orders defaults to Active and has an Active / All toggle; the history is read (`useAllOrders`) only while All is chosen.
- A selected order that leaves the active list is deselected and its panel closes.
- For 017B: delivery-address markers already come from the active list, so they follow the same 120 s rule with no extra logic.

**Verification**

- Backend: 478 tests passed (28 PostgreSQL-marked tests deselected, so migration `0009` was tested on SQLite only), ruff and mypy clean.
- Frontend: lint, typecheck and Prettier clean, 588 unit tests passed, production build succeeded.
- Migration `0009` was applied to the development PostgreSQL database on the owner's approval (84 `DELIVERED` orders got a delivery time; the 50 `READY_FOR_PICKUP` orders were untouched).

**Known limitations**

- No QA or code-review agent was run.
- `frontend/src/test/backendContract.json` was not regenerated; the parser treats a missing `delivered_at` as null.
- Unrecoverable legacy delivered orders (no flight row) stay hidden from the active view and are visible only under All.

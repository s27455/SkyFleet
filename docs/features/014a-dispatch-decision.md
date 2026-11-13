# Feature 014A — Dispatch Decision (read-only)

**Status:** Implemented (backend only) and verified by automated tests; QA and code-review agents not run. Committed in `7bc8ad7` (together with Feature 013).

## Implementation notes (verified)
- Endpoint `GET /api/dispatch/recommendations`; response `recommendations` (`order_id`, `drone_id`, `origin_hub_id`, `return_hub_id`) and `pending` (`order_id`, `origin_hub_id`, `reason`, `planner_reasons`). Code: `backend/app/dispatch/{schemas,service}.py`, `backend/app/api/routes/dispatch.py` (router registered in `app/main.py`); tests: `backend/tests/dispatch/test_dispatch_recommendations.py`. No migration, no writes.
- The pure `recommend` function calls `missions/planning.evaluate_plan` unchanged, with preloaded data. Orders per origin Hub are taken in `created_at`, then id order; drones in id order; hubs in id order. A drone must be `IDLE`, at exactly 100% battery, docked at the origin Hub, with no active mission and not already recommended in the pass. Only `READY_FOR_PICKUP` orders without an active mission are considered.
- Pending reasons: `NO_ELIGIBLE_DRONE_AT_HUB`, or `PLANNER_REJECTED` with the planner's distinct reason codes.
- Decision (confirmed by the product owner): return-Hub capacity is not reserved or tracked across a pass; the planner's existing checks against current physical occupancy are the only capacity check. Rebalancing is a later feature.

## Verification
- Passed: full backend suite 343 passed (13 PostgreSQL-marked tests deselected by default), of which 18 are new dispatch tests; `ruff` and `mypy` clean. Tests cover the acceptance criteria below, including a statement log showing no INSERT, UPDATE or DELETE during a call and identical results on repeated calls.
- Live check against the development database: 3 recommendations and 5 pending orders returned, and the mission count was unchanged by the call.
- Not run: QA and code-review agents (skipped by request); PostgreSQL tests (not applicable: no locks or writes).
- Known limitations: nothing recharges a drone yet (see 014D), so a drone left below 100% after a flight is never recommended; the "below 100% after a flight" test sets the battery directly instead of flying a mission; recommendations within one pass do not reserve return-Hub landing places.

## Goal
Implement a deterministic, read-only backend recommender that proposes order–drone assignments for SkyFleet. **Do not create, assign, or start missions; do not change persistent state.** Later features will execute recommendations and schedule dispatch.

## Existing code to reuse (verify exact paths/signatures in repository)
- `missions/planning.evaluate_plan`: existing route, payload, energy, availability, return-Hub capacity and active-assignment validation.
- `missions/service.plan_for` / `preview_plan`: existing planning/data-loading wrappers.
- `missions/presence.docked_hub` and `hub_occupancy`: physical Hub presence and occupancy.
- `orders/repository.list_orders`: existing `created_at`, then `id` ordering.
- Relevant Hub/drone repositories and mission checks. Do not duplicate planner calculations.

## Product rules
1. Each origin Hub has an **independent FIFO queue**, ordered by order creation time and stable ID tie-breaker. A blocked order or Hub must not stop other feasible orders/Hubs.
2. Consider only orders still awaiting pickup and not already assigned to an active mission; use existing status definitions.
3. A candidate drone must be **physically docked at the order's origin Hub**, `IDLE`, at **exactly 100% battery**, not in maintenance, and without an active mission. The 100% rule is an **additional dispatch eligibility filter**, not a replacement for planner energy/range checks.
4. Evaluate candidate order–drone pairs with the **existing mission planner**. Accept only planner-eligible pairs. Respect its selected nearest eligible return Hub and capacity rules.
5. Selection is deterministic: orders by `created_at, id`; eligible drones by stable `id` (unless existing conventions provide an equivalent stable order).
6. Within one recommendation pass, **never recommend the same drone twice or the same order twice**. Keep an in-memory claimed set; no database reservations in 014A.
7. When an order has no suitable drone, leave it pending, report a concise reason, and continue to later orders. Other Hubs remain unaffected.
8. Do not relocate drones to fulfill orders. No global queue, automatic execution, charging, scheduler, or UI in this feature.

## Scope and interface
- Add a minimal backend read-only recommendation service and a read-only preview endpoint following the project's existing API patterns. Confirm route naming and response shape against existing conventions before implementing.
- Response should identify proposed `order_id`, `drone_id`, `origin_hub_id`, and planner-selected `return_hub_id`, plus pending/skipped orders with useful reason codes. Keep output deterministic and simple.
- Ensure the endpoint makes **zero database writes** and never triggers mission creation or worker activity.
- Prefer a small, easily testable service function; avoid new architecture, dependencies, and broad refactors.

## Acceptance criteria / tests
- Two ready orders in one Hub and two 100%-battery idle drones yield two distinct deterministic assignments.
- One eligible drone and multiple ready orders: oldest feasible order is recommended; no drone reuse.
- An unserviceable oldest order does not block a feasible newer order in the same Hub.
- A Hub with no eligible drones does not block recommendations in another Hub.
- 99% battery, MAINTENANCE, IN_FLIGHT, active mission, wrong Hub, and planner-ineligible route each exclude a drone.
- A completed flight leaving a drone below 100% makes it ineligible until a later charging feature restores 100%.
- Repeated preview calls produce identical results for unchanged state and do not create missions or modify orders/drones.
- Add focused backend tests consistent with the existing test suite; do not require a running worker for pure decision tests.

## Out of scope / next steps
- **014B:** safe transactional assignment and mission execution (existing service locks/revalidation).
- **014C:** operator-controlled automatic scheduling and UI; default OFF.
- **014D:** automatic charging after landing; maintenance remains a separate manual/incident-related block.
- **014E:** fleet rebalancing for Hub capacity, not demand-based relocation.

## Implementation workflow
Use the repository's existing **Initialize → Start Implementation → Finish** feature workflow. Implement **only 014A**. Pause at existing approval checkpoints. Verify actual code interfaces before changes; keep changes minimal and report test results and any deviations.

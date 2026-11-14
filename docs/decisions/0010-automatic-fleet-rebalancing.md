# 0010 — Automatic fleet rebalancing (Feature 019B)

**Status:** Accepted for the MVP (deterministic rules, not AI or forecasting).

## Decisions

- **Part of Auto Dispatch.** No separate toggle, state, endpoints or migration. The Auto Dispatch mode, its OFF default and its reset to OFF when the worker starts (014C) govern both dispatching and rebalancing. OFF starts nothing new; flights already started continue; manual relocation (019A) is independent.
- **Same pass, after dispatch.** `run_dispatch_pass` dispatches first, then `run_rebalancing` (`dispatch/rebalancing.py`) may start one relocation per pass through `start_relocation(origin=AUTOMATIC, reason=...)`. The mode is read again right before the start. The plan reserves nothing: `start_relocation` revalidates under row locks, so a stale plan cannot bypass the 019A rules.
- **Shared definitions.** `available_drones_by_hub` was extracted from dispatch, so "available drone" (IDLE, 100%, docked, no active mission) means the same for both. Demand is what the dispatch recommendation leaves as `NO_ELIGIBLE_DRONE_AT_HUB`; planner-rejected orders are not demand. 019A does not require 100% itself; 019B applies it as a selection filter.
- **Policy.** Open demand is unmet orders minus relocations already flying to the Hub (manual or automatic). A donor has at least two available drones and more than its own queue needs. The Hub with the most open demand is served first (then Hub id) by the shortest feasible transfer (then drone id).
- **Cooldown without a table.** A Hub pair (either direction) is skipped for `REBALANCE_PAIR_COOLDOWN_SECONDS` (default 300) after a `RELOCATION` flight started, read from `mission_flights.started_at`, so it survives restarts. Manual relocation is never limited.
- **Quiet.** No safe transfer means no event. An automatic start writes the 019A `DRONE_RELOCATION` event with origin `AUTOMATIC` and the reason.

## MVP assumptions (not approved business rules)

- The cooldown is real time; the project has no simulated clock.
- One worker process is assumed; the per-drone unique index still prevents double assignment if two ran.
- The business-rules target of about 40 of 50 drones per Hub is not used; the policy is demand-driven only.

## Consequences

- A future change to what dispatch counts as available changes rebalancing too.
- The header control still reads only "Auto dispatch"; it does not say that it also moves drones.

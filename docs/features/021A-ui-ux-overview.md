# Feature 021A — UI/UX Overview & Roadmap

**Project:** SkyFleet drone-delivery simulator MVP  
**Status:** Specification; implementation requires explicit approval  
**Deadline context:** Recruiter-ready MVP; minimize regressions and scope creep.

## Objective

Improve operational clarity, interaction design, and dashboard layout without redesigning SkyFleet or changing established simulation behavior unnecessarily.

## Source of truth

This feature records ten user-reported issues. The current repository has **not** been inspected as part of writing this specification. Claude Code must verify actual implementation, file paths, and dependencies before proposing changes.

## Scope and mapping

| # | Requirement | Batch |
|---|---|---|
| 1 | Investigate why Random Scenarios is disabled and shows “Available when incident scenarios are enabled.” | 021D |
| 2 | Remove manual hub selection from order creation; determine origin hub through existing rules. | 021D |
| 3 | Drone creation: backend-generated unique ID, operator chooses only initial hub, battery always 100%. | 021D |
| 4 | Show meaningful human-readable destination address instead of “Delivery point TC-1287”. | 021D |
| 5 | Show the geographically nearest hub to a drone's live position; do not conflate it with assigned/home hub. | 021D |
| 6 | Display only the three newest drone activity records without deleting history. | 021B |
| 7 | Keep orders list inside a scrollable panel so desktop dashboard does not grow beyond viewport height. | 021B |
| 8 | Make incident/failure notifications compact and mobile-friendly without losing important information. | 021B |
| 9 | Put Auto Dispatch and automatic order generation controls in the navbar/toolbar; group manual scenarios behind one control. | 021C |
| 10 | Add Drones / Hubs / Orders / Events tabs to the main operational panel while preserving the map as centerpiece. | 021C |

## Execution order

0. **021A — Overview & Roadmap**: read first; specification only, not an implementation batch.

## Recommended implementation order

1. **021B — Layout & Notifications**: contained visual/UX improvements.
2. **021C — Dashboard Navigation**: reorganize existing controls and panels.
3. **021D — Functional UX Fixes**: potentially affects backend contracts and simulation semantics; inspect carefully.

Each batch is independently reviewable and testable. Do not start another batch until the current one is accepted.

## Non-negotiable constraints

- Preserve existing branding, layout identity, Mapbox interactions, and simulation behavior.
- Reuse existing components, hooks, and state where practical; avoid new dependencies.
- No unrelated refactor, broad MVC migration, or speculative features.
- Backend validation remains authoritative; do not trust frontend-only restrictions.
- Preserve Auto Dispatch, order lifecycle, manual dispatch, drone creation, Rain Warning flight grounding, incident scenarios, relocation, and return-to-hub behavior.
- No paid external API calls or fabricated address data.
- Before editing, inspect only relevant code and provide a concise plan with actual file paths, risks, and tests; **wait for approval**.
- Do not stop/restart services, install dependencies, run migrations, modify persistent database data, commit, or push without explicit permission.
- After approved changes, run appropriate non-destructive checks and report actual results, untested areas, and any required manual QA.

## Definition of done

All approved items behave as specified, desktop and mobile layouts remain usable, no known regression in core simulation flows, and each batch has an explicit QA report. Unapproved or deferred items are documented, not silently implemented.

## Working with Claude Code

Read this overview and the individual batch file. Start with `021B-layout-notifications.md`, then `021C-dashboard-navigation.md`, then `021D-functional-ux-fixes.md`. On each batch, **audit and plan first; do not implement until approval**.

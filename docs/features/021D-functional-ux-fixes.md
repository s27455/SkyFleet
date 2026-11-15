# Feature 021D — Functional UX Fixes

**Execution order:** 3 of 3  
**Requirements:** #1–#5  
**Risk:** Medium to high; may involve backend API contracts and simulation semantics.  
**Status:** 021D-1 (D2, D3, D4, D5) implemented, verified and manually QA'd by the owner. D1 (Random Scenarios scheduler) is deferred to 021D-2 and not started.

## Goal

Resolve five concrete UX problems without changing established mission, dispatch, safety, or relocation rules accidentally.

## D1 — Random Scenarios disabled (#1)

**Observed UI:** “Available when incident scenarios are enabled.”

- Trace the parent incident-scenarios setting, frontend disable conditions, API configuration, and persistence.
- Determine whether the dependency is intentional, a bug, or confusing UI.
- Make the intended enablement workflow discoverable and functional.
- Do not merely remove the disabled attribute or bypass backend restrictions.

**Acceptance:** Operator can enable Random Scenarios through a clear, supported workflow; setting reflects actual backend state.

## D2 — No hub selection when creating an order (#2)

- Remove the manual origin-hub selector from the order creation UX.
- Inspect existing order creation, dispatch, origin-hub selection, and mission assignment rules.
- Prefer reusing existing automatic hub selection rather than inventing a second algorithm.
- Clarify whether an order should receive a hub at creation time or remain unassigned until dispatch; preserve existing business semantics where possible.
- Validate behavior when no hub/drone can serve an order; avoid silently selecting an invalid origin.
- Preserve Auto Dispatch, manual dispatch, order lifecycle, and API compatibility where possible.

**Acceptance:** Operator can create an order without choosing a hub; backend determines/defers assignment according to documented existing rules.

## D3 — Drone creation defaults (#3)

- Form exposes **only initial hub** as operator input.
- Backend generates a unique drone ID following the existing convention, safe under concurrent requests.
- Backend sets initial battery to **100%**, regardless of omitted or manipulated frontend values.
- Validate hub existence and eligibility on the backend.
- Preserve any other required backend defaults and schema invariants; inspect before changing.

**Acceptance:** New drone appears with unique ID, selected hub, and 100% battery; concurrent creation does not collide.

## D4 — Human-readable order destination (#4)

**Observed UI:** “Delivery point TC-1287” instead of an address.

- Trace destination data generation, persistence, API serialization, and frontend display.
- If a real address already exists, show it.
- If only coordinates/synthetic identifiers exist, propose the smallest reliable approach to obtain a meaningful address, including fallback behavior.
- Do not invent street addresses, imply a synthetic ID is a verified address, or introduce paid geocoding without approval.
- Preserve coordinates, delivery point identifiers, and routing.

**Acceptance:** Where reliable address data exists, order details show a readable address; where it does not, a transparent, useful fallback is displayed and the limitation is documented.

## D5 — Dynamic nearest hub for flying drones (#5)

**Example:** A drone departs Galeria Bałtycka and flies toward Łąkowa Street. When Forum Gdańsk becomes geographically closer to its current coordinates, the displayed **Nearest Hub** changes to Forum.

- Calculate nearest hub from **current drone latitude/longitude** and known hub coordinates; reuse existing geographic helpers or Haversine distance.
- Update the displayed value as live drone position changes.
- Clearly distinguish **Assigned/Home Hub** (operational assignment) from **Nearest Hub** (geographic proximity).
- Preserve assigned hub, mission, return target, relocation state, and flight route; **never mutate them merely because nearest hub changes**.
- Inspect existing return-to-hub and emergency procedures and report whether they currently use assigned hub, nearest hub, or another policy. Do not change routing or safety behavior without separate explicit approval.
- Define sensible behavior for missing coordinates or hubs.

**Acceptance:** Nearest Hub updates correctly during flight and can differ from Assigned/Home Hub; no unintended mission/assignment change occurs.

## Required pre-implementation response from Claude Code

For each of D1–D5, report: actual root cause/current implementation; exact affected files; proposed minimal solution; frontend/backend impact; dependencies; test plan; regression risks. Explicitly flag any required API or migration change. **Stop and wait for approval.**

## Implementation boundaries

Prefer small, separately testable changes within 021D. No broad refactor, no new paid APIs, no fabricated data, no changes to Rain Warning takeoff restrictions, simulation worker or mission logic without explicit justification and approval. No migrations, restarts, persistent DB modifications, dependency installs, commits, or pushes without explicit permission.

## Suggested manual QA

- Random Scenarios enable/disable and persistence.
- Create orders with and without Auto Dispatch; verify assignment and mission lifecycle.
- Create multiple drones; check IDs, hub, 100% battery.
- Inspect destinations for existing and newly generated orders.
- Follow a drone in flight as the nearest hub changes; verify its mission and assigned hub remain unchanged.
- Recheck Rain Warning, dispatch, relocation, and return behavior after changes.

## Claude Code kickoff prompt

> Read `docs/features/021A-ui-ux-overview.md` and `docs/features/021D-functional-ux-fixes.md`. Focus **only** on Feature 021D (#1–#5). Audit actual code paths and existing rules first. Provide a per-item root-cause analysis, exact files, minimal solutions, API/DB impact, risks, and tests. Do not implement until I approve. Do not restart services, change DB state, install dependencies, commit, or push.

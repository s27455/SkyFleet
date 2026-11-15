# Feature 021C — Dashboard Navigation

**Execution order:** 2 of 3  
**Requirements:** #9, #10  
**Dependency:** Prefer after 021B is reviewed and stable.  
**Status:** Implemented (frontend only); automated checks passed (799 tests, typecheck, lint, format, build); manual browser QA pending; not committed.

**Approved decisions:** the Events tab is frontend-only (current alerts plus the selected drone's or order's activity, not labelled a full history, no new endpoint); a selection switches the tab but never opens a closed panel; the scenario menu is a compact bounded list that cannot be dismissed while a confirmation or request is pending; Random incidents stays disabled (021D).

## Goal

Make simulation controls and operational views easier to find while keeping the map central and avoiding a full dashboard redesign.

## C1 — Group simulation controls (#9)

- Move **Auto Dispatch** and **Automatic Order Generation** switches to a clearly labeled, compact navbar or simulation toolbar area.
- Group manually triggered random/incident scenarios behind **one recognizable icon/button**, opening a compact popover/dropdown.
- Reuse existing scenario actions, enabled/disabled states, confirmation and feedback flows.
- Preserve distinction between automatic/random scenario generation settings and manual scenario triggers; do not merge different backend behaviors just because names are similar.
- Do not silently bypass the existing “incident scenarios enabled” dependency; functional root-cause fix belongs to 021D.
- Ensure keyboard and mobile usability; avoid overflowing top navigation.

**Acceptance:** Controls are easy to find and usable, retain current behavior, and remain accessible on narrow screens.

## C2 — Tabbed operational panel (#10)

- Introduce four tabs in the main map-adjacent operational panel: **Drones**, **Hubs**, **Orders**, **Events**.
- Reuse existing lists and detail components, selection state, data fetching, and actions.
- Do not create parallel sources of truth or duplicate backend requests unnecessarily.
- Preserve map selection interactions (e.g. selecting a drone on the map should reveal its details even when another tab is active; define exact behavior after inspecting code).
- Ensure critical alerts remain visible or discoverable when Events is not the selected tab.
- Preserve the map's prominence, including desktop viewport height and mobile usability.
- Coordinate panel scrolling with the improvements made in 021B.

**Acceptance:** Each tab exposes the expected existing content and actions; map-to-panel interactions work; tab switching does not reset or corrupt operational state.

## Required pre-implementation response from Claude Code

1. Identify current navbar/toolbar, scenario controls, map panel, lists, and shared state.
2. Explain current behavior and proposed component composition.
3. Specify what happens when selecting a map object while another tab is active.
4. Identify exact paths, expected complexity, regression risks, and tests.
5. **Stop and wait for approval.**

## Implementation boundaries

Do not redesign the visual system, alter scenario or dispatch backend semantics, modify worker/database, or start 021D fixes. No new dependencies without approval. Do not restart services, modify persistent DB data, commit, or push without explicit permission.

## Suggested manual QA

- Toggle Auto Dispatch and order generation; verify actual status changes.
- Open/close scenario menu and activate an existing manual scenario.
- Switch all four tabs and operate list actions.
- Select a drone or hub on the map while a different tab is active.
- Trigger Rain Warning and incidents; verify warnings remain visible.
- Test small desktop and mobile widths; check navbar overflow and panel scrolling.

## Claude Code kickoff prompt

> Read `docs/features/021A-ui-ux-overview.md` and `docs/features/021C-dashboard-navigation.md`. Focus **only** on Feature 021C (#9–#10). First inspect current components and state flows, then propose a minimal plan with exact files, map-selection behavior, risks, and tests. Do not edit until I approve. Do not restart services, change DB state, install dependencies, commit, or push.

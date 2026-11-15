# Feature 021B — Layout & Notifications

**Execution order:** 1 of 3  
**Requirements:** #6, #7, #8  
**Priority:** First implementation batch; targeted frontend polish.  
**Status:** Implemented (frontend only); automated checks passed (768 tests, typecheck, lint, format, build); manual browser QA pending; not committed.

**Approved decisions:** B1 drone Activity only (3 newest, newest first, no "showing N" message, order timelines unchanged); B2 the Orders overlay on the main map (Management Orders tab untouched); B3 compact expandable emergency rows (3 on desktop, 2 on mobile, then a count row; no auto-dismiss).

## Goal

Improve dashboard usability and map visibility without changing backend business logic or simulation state.

## B1 — Drone activity: show last three actions (#6)

- In drone details, show only the **three most recent** activity records, newest first.
- Verify which timestamp/sequence field defines recency; handle ties consistently.
- Do not delete, truncate, or alter persisted activity history.
- Avoid fetching excessive history solely to show three items if an existing bounded API/query can be reused; do not add a new endpoint unless justified.
- Optional full-history access only if a suitable existing UI is available; no new large modal required.

**Acceptance:** 0, 1, 3, and >3 activity records display correctly; full historical data remains intact.

## B2 — Orders list stays inside dashboard (#7)

- On desktop, the dashboard should stay within available viewport height, with the map usable and visible.
- Orders list scrolls **inside its allocated panel**, rather than stretching the entire page.
- Inspect CSS grid/flex sizing, `min-height: 0`, overflow behavior, fixed/sticky headers, and viewport sizing.
- Preserve access to order actions, selection, and details.
- On mobile, avoid nested scroll traps and ensure the list can be reached and scrolled naturally.

**Acceptance:** A large number of orders does not create an unintended page-level vertical scrollbar on desktop; map and controls remain accessible; mobile scrolling is usable.

## B3 — Compact incident/failure notifications (#8)

- Reduce notification size and map obstruction, especially on mobile.
- Use a compact toast/stack/banner approach consistent with existing design.
- Keep critical warnings accessible until acknowledged or via an existing event/history view.
- Noncritical notifications may auto-dismiss only if that fits existing behavior; do not silently hide actionable incidents.
- Support readable text, accessible close/expand controls, sensible z-index, and safe mobile positioning.
- Do not change incident creation, event persistence, or flight-grounding logic.

**Acceptance:** Alerts do not cover a substantial portion of the map; critical incidents remain discoverable; multiple alerts do not overwhelm the viewport.

## Required pre-implementation response from Claude Code

1. Identify actual components and current behavior for #6–#8.
2. Propose the smallest changes with exact paths.
3. Identify CSS/layout and state-related regression risks.
4. Describe desktop/mobile QA and any existing automated checks.
5. **Stop and wait for approval.**

## Implementation boundaries

Frontend-focused. No database migrations, no simulation worker changes, no new dependencies without permission. Do not implement 021C or 021D in this batch. Do not restart services, modify persistent DB data, commit, or push without explicit permission.

## Suggested manual QA

- Drone activity list with more than three events.
- Orders list with many orders and browser window at typical desktop size.
- Narrow mobile viewport with notifications and an open operational panel.
- Multiple incident notifications; verify important information is still accessible.
- Confirm map pan/zoom and existing panel actions still work.

## Claude Code kickoff prompt

> Read `docs/features/021A-ui-ux-overview.md` and `docs/features/021B-layout-notifications.md`. Focus **only** on Feature 021B (#6–#8). Inspect relevant files, report current behavior, exact proposed changes, risks, and tests. This is a planning-only step: do not edit files until I approve. Do not restart services, change DB state, install dependencies, commit, or push.

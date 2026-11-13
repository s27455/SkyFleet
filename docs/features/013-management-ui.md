# Feature 013 — Management UI (Orders & Drones)

## Goal
Provide a small, usable administrative interface in SkyFleet for managing orders and drones through the existing backend APIs delivered in Features 011 and 012. Enable manual creation of realistic demo orders without Swagger or direct database edits.

## Scope
**Frontend only.** Reuse existing React, TypeScript, Tailwind, API client, components, navigation, and UI conventions. No backend changes unless a genuine API contract blocker is found; report blockers rather than silently expanding scope.

### Orders management
- Show an accessible list/table of orders with ID, origin Hub, delivery address, weight, status, and relevant actions.
- Create an order using a compact form: origin Hub (from existing hubs API), customer delivery address, longitude, latitude, and package weight. Do not assume address geocoding is available; allow explicit coordinate input.
- Edit only fields and states supported by Feature 012's API; disable or hide edit actions for ineligible orders.
- Expose the backend-supported cancellation/deletion operation with clear confirmation and consequences. Do not imply that an active mission can be deleted.
- Display meaningful validation and API errors; refresh data after successful mutations.

### Drones management
- Show drones with ID, assigned Hub, battery, status, and relevant actions.
- Create a drone using the fields actually supported by Feature 011, including selecting an existing Hub.
- Edit only backend-supported administrative fields, respecting active-mission restrictions.
- Provide a clear maintenance/retirement action where supported by the API. Offer deletion only when allowed, with confirmation; never delete mission history from the UI.
- Display Hub capacity and other backend validation errors without guessing.

### Integration and UX
- Add one modest **Management** area with **Orders** and **Drones** sections/tabs, consistent with the current dashboard.
- Reuse existing API types, error handling, and UI components where practical; avoid new UI libraries or large redesigns.
- Keep existing map, live flight simulation, mission planning, and worker behavior intact.
- Make the UI usable at the existing desktop viewport; basic responsive behavior is sufficient.
- Prevent duplicate submissions while a request is in flight; show loading, empty, and error states.
- Preserve backend as source of truth: do not allow unsafe edits by manipulating local state only.

## Out of scope
- Backend endpoints, database migrations, schema redesign, authentication/roles, Hub CRUD, mission CRUD.
- Automatic Dispatch, Intelligence Center, incident simulation, battery charging, geocoding/address autocomplete.
- Broad navigation redesign, advanced filtering/pagination, bulk actions, complex dashboards.

## Acceptance criteria
1. An admin can create an order from the application, then see it in the order list and existing dashboard data after refresh/polling.
2. The new order can specify a delivery point distinct from both origin and return Hub, supporting a future three-point flight test.
3. An admin can edit and cancel/delete an eligible order using the exact operations exposed by Feature 012; invalid/active cases show backend errors safely.
4. An admin can create and edit an eligible drone and manage maintenance/retirement/deletion only as allowed by Feature 011.
5. API validation failures are visible; destructive operations require confirmation; repeated clicks do not cause duplicate submissions.
6. Existing live map, flights, mission controls, and polling still work.
7. Relevant frontend tests pass; manual smoke test covers create, edit, safe removal/cancellation, and one rejected unsafe action for each resource where supported.

## Dependencies and implementation notes
- Verify Features 011 and 012 are finished and their actual API contracts before implementation. Do not invent endpoint paths, field names, or statuses.
- Inspect the existing feature workflow/skills/agents and follow **Initialize → Start Implementation → Finish** with the established approval checkpoints.
- Feature 010 may still have unfinished manual cross-Hub verification; do not silently finalize or alter it.
- Prefer small, targeted changes and tests; avoid broad repo exploration and verbose reports to conserve Claude Code tokens.
- Never reset the database, modify existing demo data destructively, or commit/push/finalize without the workflow's explicit authorization.

## Suggested implementation checkpoints
1. Inspect existing UI architecture and verified API contracts; present a concise plan.
2. Implement Orders management UI and targeted tests.
3. Implement Drones management UI and targeted tests.
4. Run relevant checks and manual smoke test; await approval before Finish.

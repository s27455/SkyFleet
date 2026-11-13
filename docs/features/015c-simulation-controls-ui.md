# Feature 015C — Order Simulation Controls UI

**Status:** Implemented and verified by automated tests; not committed. Acceptance criterion 9 (live smoke test) was not observed by the implementer. No QA or code-review agent run.  
**Area:** Frontend integration / operations controls  
**Depends on:** 015A Order Generator Core; 015B Automatic Order Generation  
**Scope:** Small UI feature; reuse existing backend APIs

## Goal

Operators can control and observe automatic order generation from the SkyFleet frontend without opening Swagger. The existing Management view continues to display generated orders.

## Existing backend contracts (verify during Initialize)

- `GET /api/orders/simulation/status` — mode status, worker availability, last check/outcome, outstanding READY_FOR_PICKUP orders and configured cap.
- `POST /api/orders/simulation/enable` — enable periodic generation; may return HTTP 503 if the worker is unavailable.
- `POST /api/orders/simulation/disable` — disable periodic generation.
- `POST /api/orders/generate` — generate exactly one order, returns the created order (201).

Do not assume an endpoint to change the generation interval exists. The 15–30 second range remains backend-configured in 015C.

## User stories

1. As an operator, I can see whether Order Simulation is ON or OFF and whether its worker is available.
2. I can turn automatic order generation ON or OFF with clear feedback.
3. I can see the current READY_FOR_PICKUP backlog relative to the configured cap and the latest generator outcome.
4. I can create one order on demand without enabling automatic generation.
5. I can distinguish Order Simulation from the existing Automatic Dispatch controls.

## Functional requirements

### UI placement

- Add a compact **Order Simulation** control section to the existing operations/Management interface, following its design system and interaction conventions.
- Keep **Automatic Dispatch** and **Order Simulation** visually and functionally separate. Do not redesign the overall dashboard.
- Responsive layout for existing supported viewport sizes.

### Status display

- Show `ON` / `OFF`, worker `Available` / `Unavailable`, and `Waiting orders: N / M` based on the API response.
- Show the last outcome as short readable text; show `last_check_at` if useful within the existing UI convention. Handle null/never-run values gracefully.
- Refresh status while the panel is mounted, using existing frontend polling/data-fetching conventions; suggested interval 3–5 seconds. Clean up polling on unmount and avoid overlapping requests.
- On initial load, show a loading state; on failure, show a non-blocking error and allow retry.

### Enable / disable

- Use the existing enable/disable endpoints; do not invent a combined toggle endpoint.
- Disable repeated clicks while a mutation is pending. Update the displayed state from the server response or by refetching status; do not permanently assume optimistic success.
- If enabling returns 503, explain that the Simulation Worker is unavailable and generation cannot be enabled. Do not silently change Automatic Dispatch.
- Display other API errors clearly without breaking the rest of the dashboard.

### Generate one order

- Add a **Generate One Order** button invoking `POST /api/orders/generate` with no request body.
- The button is independent of the automatic mode: it works whether Order Simulation is ON or OFF, subject to the existing API's rules.
- Show success/error feedback, prevent duplicate submissions while pending, and refresh/invalidate the existing order list and relevant status after success.
- Do not add new order validation or route selection to the frontend.
- The 015B automatic backlog cap applies to periodic generation; do not imply that the 015A manual endpoint is subject to the same cap unless the backend actually enforces it.

## Out of scope

- Changing generation frequency from the UI, new settings API, or database migration.
- Changes to the 015A generator catalog or 015B worker scheduling and cap.
- New order workflows, delivery exceptions, cancellations, or simulation scenarios (later feature 016).
- Changes to Automatic Dispatch behavior, drone charging, flight simulation, or mission planning.
- Large dashboard redesign, analytics, charts, or historical event log.

## Implementation guidance

- During Initialize, inspect existing frontend components, API client, data-fetching/polling conventions, error patterns and tests. Prefer reusing the Automatic Dispatch control's established UX where appropriate, without coupling the two modes.
- Add typed API functions and response types consistent with the project structure.
- Keep status polling lightweight and ensure errors do not produce repeated toast spam.
- Prefer existing refresh/invalidation mechanisms for Management orders; avoid a full-page reload.
- Do not modify backend contracts unless a genuine integration defect is discovered and separately explained.

## Acceptance criteria

1. **Initial state:** The panel loads the actual server state and displays ON/OFF, worker availability, last outcome and backlog `N / M`.
2. **Enable:** With a live worker, enabling succeeds and subsequent status reflects ON; existing automatic order generation continues as implemented in 015B.
3. **Disable:** Disabling succeeds and subsequent status reflects OFF; no change is made to Automatic Dispatch or active flights.
4. **Unavailable worker:** Enabling with a stale/missing worker produces a clear, recoverable message for HTTP 503.
5. **Manual order:** Clicking Generate One Order calls the existing 015A endpoint exactly once, gives feedback and updates the Management order list without a page refresh.
6. **Independence:** Manual generation works with automatic generation OFF; the Order Simulation controls do not change Automatic Dispatch.
7. **Reliability:** Loading, null status fields, network errors, repeated clicks, polling cleanup and narrow screens are handled sensibly.
8. **Verification:** Relevant frontend unit/component tests, lint, type checks and build pass. Existing backend tests remain unaffected.
9. **Live smoke test:** With the user observing the running app, verify ON → new orders appear → OFF → no further automatic orders; verify one manual order and worker-unavailable feedback where practical. Do not create live orders or toggle modes without explicit approval.

## Suggested implementation phases

1. **Initialize:** Audit current UI and APIs; propose minimal component placement, types, polling and refresh strategy. Stop for approval without edits.
2. **Start Implementation:** Build and test the UI integration. No commit.
3. **Live verification:** Restart frontend if necessary and validate controls against the local backend/worker with the user's approval.
4. **Finish:** Update feature documentation and progress tracker, run final checks, and commit only 015C changes.

## Definition of done

Operators can monitor, enable/disable and manually trigger order generation entirely from SkyFleet's frontend. Automatic Dispatch remains independent. No Swagger interaction is needed for the normal 015C demo.

## Implementation summary

- **Frontend only.** No backend, migration or contract change; the existing `GET /api/orders/simulation/status`, `POST .../enable`, `POST .../disable` and `POST /api/orders/generate` are used as they are.
- `frontend/src/types/orderSimulation.ts` and `frontend/src/api/orderSimulation.ts`: typed, validated status/enable/disable calls (bad data is rejected with `ApiError`). `generateOrder()` in `frontend/src/api/orders.ts` posts with no body and reuses `toOrder`.
- `frontend/src/features/orderSimulation/useOrderSimulation.ts`: `usePolledResource` with the existing 2 s fleet interval (no overlapping requests, paused while the tab is hidden, aborted on unmount, last good data kept as stale).
- `frontend/src/features/orderSimulation/OrderSimulationPanel.tsx`: the **Order simulation** section: ON/OFF switch, `Worker: Available/Unavailable`, `Waiting orders: N / M`, last automatic outcome with its time (or "No automatic orders yet."), and a separate **Generate One Order** button. It never assumes success: after each action it re-reads the status. Repeated clicks are ignored while a request is pending; errors are shown inline (the backend's message for the 503), with no toasts; loading, error with Retry and "Status may be out of date" are handled. The switch is disabled while the worker is unavailable and the mode is OFF; manual generation stays available. It makes no Automatic Dispatch call.
- Placement (deviation from the plan): mounted in `frontend/src/App.tsx` above `OrdersManager` in the Management **Orders** tab, not inside `OrdersManager`, so the existing `OrdersManager` tests are unchanged. A manual order refreshes the polled orders list at once.

## Verification

- Frontend: typecheck, lint and format check pass; vitest 400 passed (including new tests for the validator and calls, `generateOrder`, the panel, and an `App` test that clicks Generate One Order and checks the orders are re-read); production build passes (it still prints the chunk-size warning that existed before).
- Backend: not touched, so its suites were not re-run for this feature.
- Not run: the live smoke test (ON, orders arriving, OFF, one manual order, worker-unavailable message) against the running app.

## Known limitations

- The status is only read while the Management panel is open, because the section is part of that panel.
- Waiting orders counts every `READY_FOR_PICKUP` order, as in 015B; the limit pauses automatic generation only, and the manual button is not limited by it (the section says so).
- The generation interval and limit stay backend configuration (`ORDER_SIM_*`); there is no setting in the UI.

# Feature 018A — Incident Foundation & Simulation Controls

**Project:** SkyFleet — Drone Delivery Simulation MVP  
**Status:** Implemented and verified (browser QA passed per the owner); not yet committed  
**Dependencies:** Existing order/mission/flight/worker simulation; Features 017A–017C  
**Next features:** 018B Cancellation & Recall; 018C Drone Failure & Emergency Landing; 018D Failed Delivery & Parcel Return; 018E LPR Helicopter & Dynamic Safety Zone

## 1. Goal

Establish a small, reliable, backend-authoritative foundation for operational incidents and a compact demo control area. Future features will implement the four actual incident scenarios independently. **018A must not implement cancellation, failure, failed handover, LPR flights, emergency landings, or changes to drone routing.**

The finished 018A should provide a usable, persisted event timeline, a clear shared incident contract, and UI controls that are honest about which scenarios are available. Avoid a generic event platform or speculative flight-engine refactoring.

## 2. Scope and deliverables

### A. Audit and minimal incident/event contract

Before implementation, inspect existing status enums, event/history tables, order/mission/flight relationships, simulation settings and control endpoints. Reuse any existing event mechanism if suitable; do not introduce a parallel log unnecessarily.

Define a small typed incident catalog, with stable identifiers:
- `ORDER_CANCELLED` (018B)
- `DRONE_FAILURE` (018C)
- `RECIPIENT_UNAVAILABLE` (018D)
- `LPR_TRANSIT` (018E)

These are **incident categories**, not necessarily new order/drone statuses. Actual status transitions belong to later features.

For persisted operational events, prefer the smallest additive schema supporting:
- Stable event ID and type/code; UTC event occurrence timestamp (real transition time, not calculated simulated flight time).
- Optional order, mission, flight and drone references, as supported by the existing model; do not force all four for every event.
- Origin: `SYSTEM`, `AUTOMATIC` or `MANUAL` (or equivalent established naming).
- Concise reason/phase and bounded structured metadata for later incident-specific details.
- Deterministic ordering (timestamp + ID), sensible indexes and referential integrity.

Choose a pragmatic append-only write pattern. Events must be persisted in the same transaction as the corresponding domain transition when a later feature adds one; design an idempotency mechanism for retries/restarts without inventing event history. Do not claim exactly-once guarantees unless supported by the implementation.

If an additive migration is necessary, propose its exact shape during Initialize and **wait for approval before applying it**. Existing orders/flights do not require a historical backfill. An empty timeline for pre-018A orders is valid.

### B. Minimal read API and event timeline

Expose read-only event retrieval using existing API conventions (e.g. by order, mission or drone as justified by the audit). Avoid fetching the full event history every 2 seconds. Use bounded queries, stable chronological ordering and pagination/limit if needed. Historical records must remain accessible.

Show a compact, accessible chronological **Activity / Events** section in the most relevant existing order/mission detail UI. Display time, event description, source and associated entity where useful. Show an honest empty state for records with no events. Reuse current polling or refresh conventions rather than adding a separate client-side simulation.

018A may record a narrowly scoped **real operational event** at an already existing transition (e.g. a newly created order), only if the audit identifies a low-risk, transactional hook and the event provides immediate end-to-end verification. Do not rewrite existing state transitions just to populate a demo timeline, and never backfill fabricated events.

### C. Compact Simulation Events controls

Add a visually secondary **Simulation Events** cluster alongside existing automatic dispatch and order-generation controls, following SkyFleet styling and responsive layout.

Four recognizable, accessible icons with tooltips and labels:
- Cancel order — `package-x` (enabled in 018B)
- Drone failure — `triangle-alert` (enabled in 018C)
- Recipient unavailable — `package-return` (enabled in 018D)
- LPR transit — `helicopter` (enabled in 018E)

**In 018A these four triggers are visible but disabled, marked “Coming in 018B/018C/018D/018E” as appropriate.** Do not implement fake click success, random target selection or placeholder backend mutations. When each later feature ships, its own work enables only its button after the real backend handler and visual behavior are complete.

Include a small **Random incidents** toggle in the cluster only if its state can be persisted/reused through existing simulation-settings infrastructure without unnecessary schema changes. Otherwise plan its addition during Initialize. The intended product default is **enabled in demo mode, moderate frequency**, but **018A must not schedule or generate incidents** because none of the four incident handlers exists yet. Display a clear “Available when incident scenarios are enabled” explanation. Do not imply that the toggle is producing incidents before 018B.

Document a future shared trigger contract: one request → backend chooses an eligible target → real domain transition + persisted event → response with actual affected entities or a clear `NO_ELIGIBLE_TARGET` result. Automatic and manual triggers must eventually call the same service. Do not implement endpoints that accept triggers but silently do nothing.

### D. Shared architecture for later features (design only)

Write a concise extension guide describing:
- How a future incident handler validates eligibility, acquires existing locks/transaction boundaries, changes domain state and appends an event atomically.
- How to prevent duplicate/conflicting incidents on the same active mission, and how retries/restarts should behave.
- How manual trigger results and moderate automatic scheduling will be added incrementally, without introducing a second worker or separate client-side state machine.
- How a later feature exposes an **active incident state** for map badges; **event history alone must not be used to infer whether an incident is still active**.
- That future incidents need explicit parcel custody, battery/route feasibility and state-machine decisions before implementation.

Keep this a small contract, not a generalized plugin framework, new message broker, notification service or speculative LPR engine.

## 3. Invariants and compatibility

- Backend/DB is authoritative; frontend only displays persisted results.
- Existing dispatch, order generation, charging, mission timing and drone movement must not change in 018A.
- Preserve 017A/017B: delivered diamonds remain green for 120 seconds and then disappear from active map; history remains stored.
- Preserve 017C: organic delivery points, nearest feasible return hub, and `drone.hub_id` updates only after successful hub docking.
- No fake failures, fabricated events, arbitrary drone recoloring, simulated helicopter, or map warning badge without a real active incident.
- No resets, reseeding, destructive migrations or modifications to existing historical rows.
- No new runtime dependencies unless justified and approved.
- API, UI and docs should clearly identify these controls as MVP/demo-only.

## 4. Tests / acceptance criteria

**Backend**
- Event create/read round-trip with correct UTC timestamp, optional relations and deterministic ordering.
- Transaction rollback does not leave orphan events; duplicate worker retry/idempotency behavior is covered for the selected mechanism.
- Filtering/limits prevent unrelated or unbounded timeline reads.
- Existing order/mission/flight flows and 017A–017C regression tests remain green.
- If no new operational event is emitted in 018A, tests use isolated fixtures and the UI correctly shows empty state.

**Frontend**
- Timeline displays real API events in chronological order and handles loading, empty and error states.
- All four icon controls have visible/accessible names and are **disabled** until their respective feature is implemented.
- Random-incidents setting, if included, accurately reflects its effective backend state and clearly indicates no scenarios are active yet.
- Controls are compact on desktop and usable on mobile; no regression to existing simulation controls or map.

**Manual QA**
1. Existing automatic dispatch and order simulation still work.
2. Simulation Events area displays four distinct, clearly disabled scenario icons and honest status messaging.
3. Event timeline loads; new real events appear if emission was included, while historical orders without events show an empty state.
4. Reload does not invent/duplicate events or falsely enable unavailable scenarios.
5. Delivered marker lifecycle and cross-hub operations remain unchanged.

## 5. Initialize audit questions (decisions requiring approval)

1. What event/audit history already exists, and what is the smallest needed database/API addition?
2. Where should the timeline live (order details, mission details, or a reusable component), given current UI architecture?
3. Which existing real transition, if any, is safest to instrument in 018A to demonstrate end-to-end persistence?
4. How do existing simulation settings persist across worker restarts? Can the future random-incidents toggle be added now without an extra migration? If not, defer the toggle's functionality rather than storing a fake local state.
5. What idempotency/transaction approach fits the current worker and DB locking model?
6. Which test suites require PostgreSQL, and how will those be validated without touching development data?
7. Recommend future moderate incident rates and cooldowns for 018B–018E, **but do not activate scheduling in 018A**.

## 6. Explicitly out of scope

- Actual cancellation/recall logic (018B).
- Actual failure/emergency landing logic (018C).
- Failed handover/parcel return (018D).
- LPR entity, flight route, moving safety radius, landing/resumption (018E).
- Automatic incident scheduler, manual target selection and enabled trigger endpoints until real scenario handlers are implemented.
- Complex alert dashboard, customer notifications, real-world aviation integrations, billing, automated retry scheduling.

## 7. Workflow

**Initialize:** audit, report exact minimal design, schema/migration implications, UI placement, risks and decisions. No code edits, DB changes or commit.  
**Start Implementation:** only after plan approval; implement 018A, tests and manual QA support; no commit.  
**Finish:** after visual review; update spec/docs, final checks and commit only approved 018A changes.

**Definition of done:** a tested, honest event-history foundation and compact demo-control shell, with no fake incident behavior and no regression to existing simulation features.

## 8. Implementation result

Delivered as planned: migration `0010` (`operational_events`), `app/events/` with `append_event` (`INSERT ... ON CONFLICT DO NOTHING ... RETURNING`), read-only `GET /api/events`, `ORDER_CREATED` in `create_order` (`MANUAL` via the API, `AUTOMATIC` via the generator), explicit event removal inside `delete_order`, an Activity timeline in the order detail panel, and the disabled Simulation Events cluster with inline SVG icons and a disabled Random incidents switch. Decisions and the extension guide: `docs/decisions/0004-incident-event-foundation.md`.

Audit answers (section 5): no event mechanism existed, so one table was added; the timeline lives in the order detail panel (there is no mission detail panel); `ORDER_CREATED` was the instrumented transition; the existing settings tables are mode-specific, so the Random incidents toggle is a disabled placeholder with no new table; idempotency uses `dedupe_key` with `ON CONFLICT DO NOTHING`; PostgreSQL tests are opt-in (`pytest -m postgres`) and use a temporary database. Recommended future rates (proposal, not active): at most one random incident per 3 to 5 minutes, a 2 to 3 minute cooldown per incident type, one active incident per mission.

Verification: backend pytest 533 passed (30 PostgreSQL-marked deselected); events tests including PostgreSQL-marked ones on a temporary database 19 passed; ruff, ruff format, mypy clean; frontend lint, typecheck, format check, 617 unit tests and a production build pass; migration applied to the development database with approval and a live API smoke test passed. Not run: QA or code-review agents, the full PostgreSQL suite. Known limitations: no single-instance guard for the worker; events are recorded for new orders only.

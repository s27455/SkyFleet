# Feature 017C — Natural Delivery Locations & Nearest-Hub Return

**Project:** SkyFleet MVP  
**Status:** Implemented and tested; finalized by the owner (2026-11-13). Not yet observed live by the implementer (organic points on the map, a real cross-hub return). See section 12.  
**Depends on:** 017A Delivered Orders Lifecycle and 017B Delivery Marker States  
**Scope:** Backend order-location generation, simulation worker routing and hub assignment; minimal frontend compatibility only if required.

## 1. Problem

Generated delivery destinations currently form visually obvious, repeated geometric patterns around the hubs. Delivery routes therefore look artificial. Separately, a drone returns to its departure hub even when it delivers closer to another operational hub. This makes cross-city delivery operations less realistic and limits the simulation's network behavior.

## 2. Goal

1. Generate organic, irregular delivery locations within the supported operating area, without fixed rings, octagons or repeated angular spacing.
2. Include a sensible mix of short, medium and occasional longer deliveries, including destinations near a different hub.
3. After delivery, route a drone to the **nearest feasible operational hub**, which may differ from its origin.
4. Preserve safe dispatch, battery constraints, consistent drone ownership/location and existing 017A/017B behavior.

**Important:** This is a simulation feature, not production-grade geocoding, airspace authorization or real-world flight planning.

## 3. User-visible behavior

- New order diamonds appear at varied, plausible positions, rather than in symmetric patterns around each hub.
- Most deliveries are local or medium-distance; a minority extend across hub catchment areas. Exact distribution is a design decision to propose during Initialize, not an arbitrary hard-coded requirement.
- A drone may launch from Hub A, deliver near Hub B, return to Hub B and become available there for later orders.
- Existing flights continue normally; delivered markers still turn green for 120 seconds and then disappear under 017A/017B.
- The drone's hub displayed by API/UI reflects its **actual assigned/parked hub after landing**, not the hub it originally departed from.

## 4. Functional requirements

### FR-01 — Audit current geography and generation

Identify every order-generation path (manual, one-shot generator, automatic simulation, seed/demo data), the existing location-generation function(s), hub coordinates, geographic constraints, distance calculations, and any assumptions about an order's originating hub. Prefer one shared location-generation policy across automatic generators; do not silently change user-supplied manual coordinates.

### FR-02 — Organic destination sampling

- Replace deterministic ring/spoke/octagon patterns with irregular two-dimensional geographic sampling (e.g., distance/angle jitter or area-aware sampling) that does not produce repeated visible geometry.
- Avoid exact duplicate points and destinations exactly on hub coordinates; use bounded retries with a safe fallback.
- Constrain destinations to the supported simulation operating area. Do not place orders offshore, outside the map's intended coverage, or in obviously implausible positions if existing geographic masks/bounds allow prevention.
- Do not add external geocoding, routing APIs, or heavy geospatial dependencies for the MVP. If a polygon/land mask is not already available, document the limits of the chosen lightweight approximation instead of claiming all points are valid street addresses.
- Use the project's existing random/seed mechanism, if present, so tests remain deterministic. Do not introduce unseeded randomness into deterministic simulation tests.
- Include occasional cross-hub destinations without making long-haul deliveries the default.

### FR-03 — Nearest **feasible** return hub

At the moment the simulation plans/commits the post-delivery return leg, evaluate operational hubs using the existing distance and flight-energy model. Select the closest **feasible** hub by distance from the delivery location, with deterministic tie-breaking. Feasibility must respect existing constraints, including at minimum:

- Enough remaining battery/energy to complete the return leg with the simulation's existing reserve policy.
- Hub is eligible/operational according to the current domain model; do not invent capacity constraints or hub states that do not exist.
- The route is valid within current simulation rules.

If the geometrically nearest hub is not feasible, choose the next nearest feasible hub. If no hub is feasible, use the existing low-battery/emergency/failure behavior where available; otherwise surface a clearly defined safe fallback and document it in the plan. **Do not teleport a drone, silently refill its battery, or fabricate a successful landing.**

### FR-04 — End-to-end energy feasibility

Audit dispatch/mission planning, not just the return-leg selection. A delivery should not be accepted on the assumption that the drone will return to its origin when its actual destination may be another hub. Ensure the planning/reserve logic and worker execution use compatible feasibility rules and distance units. Avoid making previously valid missions fail due to inconsistent models.

### FR-05 — Hub reassignment after landing

- A drone's hub association must not change merely because a new return hub is chosen; it changes at the appropriate landing/completion transition.
- On successful arrival, persist the destination hub assignment and the drone's final position consistently with the existing schema and worker state machine.
- The drone should become available/charge at the destination hub according to existing charging and dispatch behavior.
- Subsequent orders should treat that drone as belonging to the new hub.
- Preserve mission/flight history (departure hub, return destination and actual route where supported). Do not rewrite historical origin data to match the new hub.

### FR-06 — Existing flight and UI compatibility

Ensure return-leg geometry, moving drone marker, mission details, flight path, charging and hub-specific drone counts continue to reflect the correct state. Reuse existing API contracts when possible. Do not change delivery-marker status mapping, the delivered timestamp semantics or 120-second expiration.

### FR-07 — Existing data compatibility

New generation rules apply to newly generated orders. Do not relocate existing orders, alter in-progress missions, reset the database, reseed drones or rewrite historical flight records. Any schema migration must be separately justified and approved before application.

## 5. Nonfunctional requirements

- Minimal, maintainable changes; prefer pure helpers for location sampling and hub choice.
- Deterministic unit tests via seeded randomness / injected RNG and fixed coordinates.
- No extra frontend polling, background loops, map rendering framework changes or new third-party dependencies unless the audit establishes a clear need.
- Keep automatic simulation performant with the existing polling and worker cadence.
- Maintain transactional consistency between mission completion, drone state and hub assignment.

## 6. Acceptance criteria

1. Newly generated destinations no longer form fixed symmetric rings or regular angular patterns in a representative batch.
2. The generated sample includes varied distances and some cross-hub deliveries; no invalid coordinates or exact hub-location deliveries.
3. A delivery closer to a different feasible hub returns to that hub.
4. A nearer but battery-infeasible hub is skipped for a feasible alternative; no-feasible-hub behavior is explicit and tested.
5. After landing at a different hub, the drone's persisted hub association, position, charging/idle state and subsequent dispatch eligibility agree.
6. The flight/mission history retains the true origin and destination; the drone does not teleport at route transitions.
7. Existing in-progress and historical orders are not modified by the generation change.
8. 017A/017B regressions pass: blue during delivery, green for 120 seconds after actual delivery, then no diamond.
9. Backend tests, lint/type checks and relevant frontend tests/build pass; live smoke test demonstrates at least one cross-hub return.

## 7. Required test scenarios

- Seeded generation: deterministic output; distribution not locked to a few radii/bearings; bounded coordinates; no duplicates; cross-hub sample.
- Existing manual orders: unchanged coordinates.
- Hub selection: origin nearest; another hub nearest; tie; nearest infeasible; all infeasible; one eligible hub; correct distance units and battery reserve.
- Worker: delivery → return leg to chosen hub → landing → hub reassignment → charging/idle → next dispatch from new hub.
- Regression: drone remains associated with its original hub until landing; historical origin preserved; 017A/017B lifecycle unchanged.
- Live: generate a batch, inspect spatial spread, follow a cross-hub mission, verify return and new hub assignment; verify delivery marker lifecycle.

## 8. Suggested implementation stages

**Stage A — Geography:** Audit and replace destination generation; add seeded distribution/bounds tests. No worker-routing change yet.

**Stage B — Routing:** Implement a pure nearest-feasible-hub selector; audit energy budget and mission return-leg planning; add tests.

**Stage C — Worker integration:** Persist return destination and reassignment on landing; verify charging/dispatch/UI, add integration tests.

**Stage D — Live review:** Observe organic destinations and at least one real cross-hub return in the running simulation.

Claude Code may recommend splitting 017C into separate implementation substeps if the audit reveals significant state-machine coupling. Do not implement all stages blindly before the plan is approved.

## 9. Initialize audit questions / decisions

1. Where are generated delivery points created, and what existing geographic constraints are available?
2. What does the current drone `hub_id` mean while in flight, and when is it updated?
3. How are return-leg destination, battery cost and reserve calculated today? Is return-to-origin baked into dispatch validation?
4. Can the current flight/mission schema represent a different return hub without migration?
5. What is the existing behavior when a return is infeasible?
6. Which automated tests can demonstrate a real hub change and later dispatch?
7. What small, testable implementation sequence minimizes risk to the worker?

## 10. Out of scope

Real street-address geocoding, building-level delivery validation, terrain/airspace/obstacle routing, live weather, new hub capacity systems, real battery physics, manual reassignment UI, major map redesign, and any changes to the 017A/017B delivered-order lifecycle.

## 11. Definition of done

Approved audit and plan; implemented stages; automated checks passing; browser/live-worker verification of organic locations and cross-hub return; no data loss; documentation and commit only in the separate Finish step.

## 12. Implementation notes (verified)

**Audit result.** The nearest feasible return Hub was already implemented: the mission planner (`missions/planning.py`, `capacity.py`) picks the Hub nearest to the destination (ties to the lower id) that is within the mission budget, passes the battery check with the parcel assumed to stay on board plus the 20% reserve, and has a free place; the flight lands there, diverts when it is full, and ends in a simulated emergency when nothing is reachable. That behavior was kept unchanged. The repeated "octagon" patterns came from a 16-route catalog whose points repeat, so markers sharing an exact point were spread on rings by the frontend (display only).

**Stage A — organic delivery points (backend)**

- `app/orders/operating_area.py`: a 15-vertex approximate polygon around the four Hubs. It is **not** a land or sea mask; its east edge follows the bay only roughly. The vertices are edited in this one file, and a test checks that every Hub is inside.
- `app/orders/locations.py`: a seeded, pure sampler. It picks an origin Hub and a style: local (about 60%, 0.35–2 km from the origin Hub), medium (about 30%, 2–4.5 km) or cross-hub (about 10%, 0.3–1.8 km around a different Hub). The proportions are targets, not guarantees. A point must be inside the polygon, at least 60 m from every Hub and at least 50 m from every open order; there are 40 attempts.
- `app/orders/generator.py`: feasibility reuses the planner's own helpers (`estimate_energy`, `has_enough_battery`, `hubs_by_distance`): the route to the nearest Hub must be inside the mission budget and the worst case plus reserve must fit in a full battery. The weight is capped at the heaviest 0.1 kg step that fits (minimum 0.2 kg). Destinations are labelled `Delivery Point TC-0001`, counting up (`TC` for Tricity; the real coordinates are in the order details). The catalog in `generator_catalog.py` is now only a fallback, used when there is no Hub or drone model to check against or no flyable point is found. `generate_one_order` gained an optional `payload_energy_factor`. Manual and existing orders are never changed.

**Stage B — return Hub.** No logic change. New `tests/missions/test_return_hub_selection.py` covers: the origin Hub nearest, another Hub nearest, a distance tie, the nearest Hub out of range, no feasible Hub, a single eligible Hub, and a full Hub.

**Stage C — `hub_id` on landing.** `drone.hub_id` is now the Hub where the drone last docked successfully. `engine._decide_landing` sets it only on a successful landing (a diversion that lands included), never during flight and never after an emergency. Missions and flights keep their origin and return Hubs. No schema change and no migration. The definition was updated in `app/drones/models.py`, the README and `context/business-rules.md`, and the frontend label "Assigned Hub" is now "Current Hub" (drone panel, inspector, Management drones table and form). One existing engine test that asserted the old behavior (`ORD-011`, Bałtycka → Forum) was updated to the new rule.

**Verification**

- Backend: 516 tests passed (28 PostgreSQL-marked tests deselected), ruff, ruff format and mypy clean.
- Frontend: lint, typecheck and Prettier clean, 609 unit tests passed, production build succeeded.
- New tests: a seed gives the same points; points are inside the area, clear of Hubs and never repeated; no rings or spokes over 400–800 samples; the style mix over 3000 samples is near the targets; cross-hub points are usually nearer another Hub; the weight cap matches the planner's energy rules; all 120 generated orders get an eligible plan from a full-battery drone at the origin Hub; existing orders are untouched; the catalog fallback works. Engine tests cover a planned cross-hub landing, `hub_id` unchanged in flight and in an emergency, a diversion that lands, charging at the new Hub and a later dispatch from it.

**Not verified / known limitations**

- Organic points were not looked at on the real map. The polygon is hand-drawn, so some points may fall on water inside the area or in parks.
- A real cross-hub return in the live worker was not observed.
- No PostgreSQL tests were run, and no QA or code-review agent.
- Drones that landed at another Hub before this change keep their old `hub_id` until they next land; there was no backfill.
- Workers have no auto-reload and must be restarted after backend changes.
- Before the live check, at the owner's request, all orders, missions and flights in the development database were deleted (225, 144 and 144 rows); drones and Hubs were untouched.

# Feature 019B — Automatic Fleet Rebalancing

**Status:** Implemented and verified by automated checks; Live QA passed per the owner; not yet committed. No QA or code-review agent run. Decisions: `docs/decisions/0010-automatic-fleet-rebalancing.md`  
**Approved adjustment (supersedes conflicting text below):** rebalancing is part of the existing **Auto Dispatch** mode. There is no separate toggle, state table, endpoints or migration; the Auto Dispatch ON/OFF control, its state, its API and its reset-to-OFF when the worker starts are reused unchanged.  
**Depends on:** 019A Manual Drone Relocation (implemented and Live QA reported successful)  
**Scope:** Lean MVP; deterministic, rule-based fleet balancing

## 1. Goal

Prevent long-running simulation imbalance: drones accumulate at some hubs after deliveries while other hubs have queued orders but no available drones. When explicitly enabled by the operator, SkyFleet should automatically relocate eligible idle drones from surplus hubs to hubs with demonstrated unmet demand, using the **existing 019A relocation service and real flight engine**.

This is an operational rules feature, **not AI**, demand forecasting, or a new flight system.

## 2. Operator experience

- **No new control.** The existing Auto Dispatch switch governs both dispatching orders and rebalancing drones. It is OFF by default and the worker resets it to OFF whenever it starts (014C), so nothing relocates just because the system started.
- While Auto Dispatch is ON, each pass (every `DISPATCH_AUTO_INTERVAL_SECONDS`) first dispatches orders and then checks for a genuine hub shortage; it can start one relocation without manual confirmation.
- Each automatic relocation is visible in existing Activity/operational events, including source, destination, and a concise reason (e.g., destination has queued orders and no available drone).
- Manual relocation from 019A continues to work regardless of Auto Dispatch. Switching it OFF prevents **new** automatic dispatches and relocations; already-started flights continue normally.

## 3. Eligibility and safety — reuse 019A

An automatically selected drone must satisfy **all** existing 019A checks at the moment of dispatch:

- Battery **100%** (use the project's canonical representation/precision). *Audit finding:* 019A itself does not require 100% (it needs the empty-flight energy plus the 20% reserve); 019B applies 100% as a selection filter through the shared dispatch definition of an available drone, and 019A is unchanged.
- Status **IDLE**, physically docked at its source hub.
- No active or assigned mission/order.
- Destination is a different, reachable hub; distance, energy/reserve and capacity rules pass.
- No conflicting dispatch, charging, manual relocation, or another rebalancing action.

**Do not duplicate these checks.** Call the shared 019A relocation service and preserve its locking and atomic validation. Reuse the existing flight, landing/diversion, failure, and LPR behavior. `hub_id` changes only after landing.

## 4. MVP balancing policy

### 4.1 Identify demand

A destination hub qualifies when it has **at least one genuinely dispatchable queued order waiting for a drone** and **no currently eligible local drone** to serve it. Use existing dispatch eligibility/business rules rather than raw order counts alone; avoid treating blocked/unserviceable orders as demand. A pending automatic relocation to that hub should count as incoming supply to avoid duplicate transfers.

### 4.2 Identify safe surplus

A source hub may donate only if it has **at least two eligible idle, fully charged drones** and donating one would leave **at least one** such drone behind. Do not donate from a hub with its own dispatchable queued orders waiting for a drone. Check source and destination conditions again immediately before starting a relocation.

### 4.3 Select one transfer

- Choose a destination with the most qualifying unmet demand; use a deterministic tie-break (e.g., hub ID).
- Choose a source/drone that can reach it, preferring the shortest eligible transfer distance; deterministic tie-breaks.
- Start **at most one new automatic relocation per evaluation cycle**.
- Avoid repeated back-and-forth transfers with a simple **per-hub-pair cooldown** (suggested initial value: 5 simulated minutes, or an equivalent established project time basis). The cooldown must not block manual relocation.
- Count active incoming automatic relocations to avoid oversupplying a destination.

These thresholds are MVP defaults. During Initialize, verify them against the real dispatch model, simulation clock and existing settings; flag only material ambiguities for approval. Do not add predictive scoring, complex optimization, or new inventory accounting.

## 5. Execution and persistence

- Run evaluations in the **existing Simulation Worker** or its established periodic orchestration, not in frontend polling or a new long-lived service.
- The ON/OFF state is the existing Auto Dispatch state. The cooldown and incoming-relocation awareness are read from the stored `RELOCATION` missions and flights (`mission_flights.started_at`), so they survive restarts. No migration is needed.
- Keep the evaluation cheap for four hubs / twelve drones. No new scheduler infrastructure.
- Make automatic decisions safe under repeated ticks/restarts and concurrency with dispatch and manual relocation. A stale preview must never bypass 019A's final atomic validation.
- Avoid duplicate worker-induced relocations; if the existing single-worker assumption is relevant, document it and use the smallest reliable DB-side protection already available.
- An inability to find a safe transfer is normal: do nothing and wait for the next cycle, without noisy repeated events.
- Reuse the existing 019A mission/flight model (`purpose=RELOCATION`, no customer order). If attribution is needed, add the smallest backward-compatible way to distinguish **MANUAL** from **AUTOMATIC** relocation in events/history, without inventing customer orders.

## 6. API and frontend

- No new API or frontend control: the existing `/api/dispatch/auto/*` operations and the Auto Dispatch switch are reused. Existing Activity shows each automatic relocation (origin *Automatic*, with the reason in the event).
- Do not build a dashboard, forecasting chart, dedicated history screen, or manual approval queue.
- Existing 019A Relocate UI and backend API must remain unchanged for operators.

## 7. Compatibility

- **014 dispatch:** Dispatch takes priority; do not relocate a drone needed for currently dispatchable local demand. Existing active-mission locking remains authoritative.
- **019A:** Automatic mode calls the same relocation mechanism, never forks the flight engine.
- **018C:** Relocating drones may fail; use existing emergency/maintenance behavior.
- **018E:** LPR HOLD/yield/resume applies to relocation flights as before.
- **Charging:** CHARGING or less-than-full drones are ineligible.
- **Landing:** Destination capacity can change during flight; existing diversion logic applies.
- **018B/018D:** Relocation has no order and must not trigger cancellation or delivery-failure milestones.

## 8. Out of scope

- AI/LLM decision-making (Feature 020), demand prediction, machine learning.
- Relocating IN_FLIGHT, CHARGING, MAINTENANCE or partially charged drones.
- Creating fake delivery orders, teleporting drones, adding a new flight engine.
- Global optimal assignment, multi-hop routing, weather planning, dynamic pricing.
- Automatically reversing or cancelling a flight when the toggle is switched OFF.
- UI redesign or unrelated infrastructure refactors.

## 9. Acceptance criteria — Live QA

1. With Auto Dispatch **OFF**, prolonged simulation produces **no automatic relocation**; manual 019A remains usable.
2. Auto Dispatch is OFF after a worker restart (existing 014C behavior) and ON is visibly reflected in the UI; no relocation starts until the operator turns it on. The 5-minute pair cooldown survives a restart.
3. When a hub has qualifying queued demand and no eligible local drone, and another hub has a safe surplus, **one automatic relocation starts** without operator confirmation.
4. The chosen drone has **100% battery**, is **IDLE**, docked, and mission-free immediately before relocation; otherwise no transfer starts.
5. Source retains at least one eligible drone; hubs with local dispatchable demand do not donate.
6. A real empty flight is visible on the map; battery decreases; destination hub assignment changes **only after landing**.
7. Activity identifies the relocation as **automatic**, with origin, destination and reason; no fake order is created.
8. Repeated worker ticks do not create duplicate transfers or oscillation; incoming flights and cooldown are respected.
9. Turning OFF stops new transfers but does not interrupt one already in flight.
10. Manual relocation, normal delivery dispatch, LPR HOLD, failure handling, and destination diversion still work.

## 10. Automated verification

- Policy unit tests: unmet demand, local availability, donor reserve, blocked orders, distance, full battery, tie-breaks, cooldown, incoming relocation, OFF state.
- Mode tests: OFF by default, OFF after a worker restart (reset), turning OFF stops a transfer not yet started.
- Worker integration tests: starts at most one transfer per cycle; idempotence across repeated ticks/restarts; correct use of 019A service.
- PostgreSQL concurrency tests where relevant: competing dispatch, manual relocation and simultaneous balancing attempts.
- Regression tests: existing 019A, delivery flights, charging, 018C failure, 018E LPR.
- Existing backend/frontend verification gates; Live QA in browser before Finish.

## 11. Initialize audit questions

Before implementation, inspect:

1. How the existing dispatch logic defines a queued **dispatchable** order and eligible drone; whether its logic can be reused without side effects.
2. Where worker ticks are scheduled and which simulation time basis is canonical.
3. Existing persisted operator settings / automatic dispatch toggle patterns.
4. How 019A represents active/incoming relocations and emits events, and the smallest way to record automatic attribution.
5. Whether source-hub protection and destination-capacity checks can be made concurrency-safe using existing locking.

Propose the **smallest implementation plan** and surface genuine decisions only. Initialize is **analysis only**: no edits, migrations, service restarts, development-data changes or commits.

## 12. Workflow

**Initialize → plan review/approval → Start Implementation → automated QA → Live QA → Finish.**

Claude Code must not stop/restart user-managed services, apply development DB migrations, modify development data, or commit without explicit permission.

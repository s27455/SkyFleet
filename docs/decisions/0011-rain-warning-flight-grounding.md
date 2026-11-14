# 0011 — Rain warning and flight grounding (Feature 020)

**Status:** Accepted for the MVP (a manual, global, simulated restriction; no weather data).

## Decisions

- **One global state, persisted.** `weather_state` holds a single row `rain-warning` (`active`, `activated_at`, `cleared_at`, `origin`, `updated_at`), seeded INACTIVE by migration `0016`; a missing row also means INACTIVE. It survives API and worker restarts and is never cleared automatically. Activation and clearing are idempotent: a repeated request changes nothing and records no second event.
- **New takeoffs only.** The gate sits at the two places that create a flight: `simulation.service.start_mission` (every delivery takeoff) and `simulation.relocation._start_once` (manual and automatic relocation). The worker, the flight engine, landing, diversion, recall, drone failure and cancellation never call it, so airborne flights are never interrupted.
- **Race safety.** Each takeoff transaction calls `weather.lock_for_takeoff` first, before any mission, order or drone lock: it reads the state row `FOR SHARE` and raises `RainWarningActiveError` while active. Activation takes the row `FOR UPDATE`, so it waits for takeoffs that already passed the gate and commits before any later one looks. No takeoff commits after the warning became active. Activation touches no domain row, so the locks cannot form a cycle.
- **Refusal writes nothing.** The error is raised before any write and the transaction rolls back. API: 409 `RAIN_WARNING_ACTIVE`.
- **Assignment stays allowed.** `confirm_mission` only creates a pending `ASSIGNED` mission; starting it is refused while the warning is active. After clearing, the existing Start action works; the operator can also cancel it (the existing cancellation) at any time.
- **No stranded dispatch.** `execute_dispatch` checks the warning before creating anything. If the warning wins the race after the mission was created, that call cancels the mission it just created with the existing cancellation, so neither the drone nor the order stays reserved by a mission nobody will start. A mission the operator assigned by hand is never cancelled automatically.
- **Auto Dispatch.** A pass while the warning is active recommends, creates and relocates nothing (so no rebalancing either) and records one outcome line, "Rain warning active; new takeoffs suspended", through the existing change-only recording (no repeated log line). The mode itself (ON/OFF) is untouched; queued orders resume after clearing under the normal rules.
- **Events.** `RAIN_WARNING_ACTIVATED` and `RAIN_WARNING_CLEARED` (origin `MANUAL`, no order, mission or drone), one per real change, in the same transaction as the state. `GET /api/events` accepts `event_type` as a sufficient filter so they can be read; there is no global activity feed in the UI yet (the panel and banner show the live state).
- **API.** `GET /api/incidents/rain-warning`; `POST /api/incidents/rain-warning/activate` and `/clear` (idempotent; `changed` tells whether anything changed).
- **Frontend.** A Rain Warning control in Simulation events, a slim banner when active (precautionary wording; no claim of live weather), and Start mission and Relocate disabled with the reason through a small context. State arrives through the existing polling.

## MVP assumptions (not approved business rules)

- One global warning; no per-Hub or geographic restriction, no intensity, no forecast, no automatic trigger.
- The pre-takeoff recheck of `business-rules.md` §4 is realised by this gate only; other airspace restrictions remain open (Q7).

## Consequences

- A future weather provider or a rooftop station can set the same state (`origin` is stored) without changing the gate.
- A new way to start a flight must call `weather.lock_for_takeoff` first.
- The migration downgrade fails while rain events exist (the narrower CHECK); delete them first.

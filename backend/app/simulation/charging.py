"""Automatic charging of docked drones (Feature 014D), run by the simulation worker each tick.

A drone that is `IDLE`, below 100% battery, physically docked at a Hub and not claimed by an active
mission becomes `CHARGING`. Each tick adds `rate x elapsed` to the battery of every charging drone;
at 100% the battery is clamped to exactly 100 and the drone becomes `IDLE` again, so the 014A to
014C dispatch can use it. Charging does not depend on the Automatic Dispatch mode. `IN_FLIGHT` and
`MAINTENANCE` drones, undocked drones and drones with an active mission never charge, and
`MAINTENANCE` is never cleared here.

The battery column is a whole number, so the fractional part of the charge is carried in memory
(`ChargingState`). That keeps restarts safe without a schema change: the battery itself is stored,
the first tick after a start counts one nominal tick (not the time since the drone landed), and
the time between ticks is clamped, so neither a restart nor a clock jump can add a burst of charge.
What is lost on a restart is less than one tick of charge, and charging pauses while the worker is
down. An operator's manual battery edit simply becomes the new starting point. The rate is one
configurable demo-friendly number (`SIM_CHARGE_RATE_PCT_PER_MINUTE`); there are no charger slots.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.drones.models import Drone, DroneStatus
from app.hubs.models import Hub
from app.missions import repository
from app.missions.presence import docked_hub

logger = logging.getLogger("skyfleet.charging")

FULL_BATTERY_PCT = 100
# The time between two ticks is counted at most this many nominal ticks, whatever the clock says.
MAX_TICKS_PER_STEP = 5


@dataclass
class ChargingState:
    """The worker's memory between ticks; losing it costs less than one tick of charge."""

    last_tick: datetime | None = None
    # Fractional percent not yet added to the stored whole-number battery, per drone.
    carry: dict[str, float] = field(default_factory=dict)
    # The battery value this worker last stored per drone; a different stored value means that
    # someone else changed it (an operator edit), so the carried fraction no longer applies.
    written: dict[str, int] = field(default_factory=dict)

    def forget(self, drone_id: str) -> None:
        self.carry.pop(drone_id, None)
        self.written.pop(drone_id, None)


def elapsed_seconds(state: ChargingState, now: datetime, settings: Settings) -> float:
    """Seconds to charge for this tick: one nominal tick the first time, then the clamped gap."""
    nominal = settings.sim_tick_seconds
    if state.last_tick is None:
        return nominal
    return min(max((now - state.last_tick).total_seconds(), 0.0), nominal * MAX_TICKS_PER_STEP)


def charge_step(
    factory: sessionmaker[Session], settings: Settings, now: datetime, state: ChargingState
) -> int:
    """One charging step for every drone; returns how many drones changed (battery or status)."""
    seconds = elapsed_seconds(state, now, settings)
    state.last_tick = now

    with factory() as session:
        drone_ids = list(
            session.scalars(
                select(Drone.id)
                .where(
                    or_(
                        Drone.status == DroneStatus.CHARGING.value,
                        (Drone.status == DroneStatus.IDLE.value)
                        & (Drone.battery_pct < FULL_BATTERY_PCT),
                    )
                )
                .order_by(Drone.id)
            )
        )
        hubs = list(repository.list_hubs(session))
    if not drone_ids:
        state.carry.clear()
        state.written.clear()
        return 0

    gain_per_second = settings.sim_charge_rate_pct_per_minute / 60.0
    changed = 0
    for drone_id in drone_ids:
        with factory() as session:
            try:
                if _charge_one(session, drone_id, hubs, settings, state, gain_per_second * seconds):
                    changed += 1
                session.commit()
            except Exception:
                session.rollback()
                state.forget(drone_id)
                logger.exception("Could not charge drone %s; the other drones continue", drone_id)
    return changed


def _charge_one(
    session: Session,
    drone_id: str,
    hubs: Sequence[Hub],
    settings: Settings,
    state: ChargingState,
    gain_pct: float,
) -> bool:
    # The row lock serialises this with dispatch and mission confirmation; everything below is
    # decided on the locked, current values.
    drone = repository.get_drone(session, drone_id, lock=True)
    if drone is None:
        state.forget(drone_id)
        return False
    charging = drone.status == DroneStatus.CHARGING
    waiting = drone.status == DroneStatus.IDLE and drone.battery_pct < FULL_BATTERY_PCT
    if not (charging or waiting):
        state.forget(drone_id)  # changed meanwhile (flying, maintenance, already full)
        return False
    if docked_hub(drone, hubs, settings.hub_dock_proximity_m) is None or (
        repository.drone_has_active_mission(session, drone_id)
    ):
        state.forget(drone_id)  # not at a Hub, or claimed by a mission: leave it alone
        return False

    if waiting:
        # Starting to charge adds nothing yet: the first tick never produces an instant jump.
        drone.status = DroneStatus.CHARGING.value
        state.forget(drone_id)
        logger.info("Drone %s started charging at %d%%", drone_id, drone.battery_pct)
        return True

    if drone.battery_pct >= FULL_BATTERY_PCT:  # for example an operator set it to 100
        _finish(drone, state)
        return True

    if state.written.get(drone_id) != drone.battery_pct:
        state.carry[drone_id] = 0.0  # first sight, or edited by someone else: start from here
    carry = state.carry.get(drone_id, 0.0) + gain_pct
    whole = int(carry)
    state.carry[drone_id] = carry - whole
    if whole < 1:
        state.written[drone_id] = drone.battery_pct
        return False
    drone.battery_pct = min(FULL_BATTERY_PCT, drone.battery_pct + whole)
    if drone.battery_pct >= FULL_BATTERY_PCT:
        _finish(drone, state)
    else:
        state.written[drone_id] = drone.battery_pct
    return True


def _finish(drone: Drone, state: ChargingState) -> None:
    drone.battery_pct = FULL_BATTERY_PCT
    drone.status = DroneStatus.IDLE.value
    state.forget(drone.id)
    logger.info("Drone %s is fully charged", drone.id)

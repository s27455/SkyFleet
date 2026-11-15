"""Simulation Worker entrypoint: `uv run python -m app.worker`.

Runs as its own process, independent of the API and of any browser session. Each tick records a
heartbeat (a mission can only start while it is fresh) and advances every active flight
(`app.simulation.engine`). Flight state is derived from stored schedules and the clock, so a
restart neither resets nor invents progress.

The worker also owns the automatic dispatch loop (Feature 014C): it resets the mode to OFF when it
starts, and while the operator has switched it ON it runs a dispatch pass every
`DISPATCH_AUTO_INTERVAL_SECONDS`. API and browser are not involved in dispatching. Each tick it
also charges docked drones below 100% (Feature 014D), whatever the dispatch mode is.

It owns the automatic order generation loop too (Feature 015B), switched by its own Order Simulation
mode: reset to OFF at startup, and while ON one order is created after each random pause. It is
independent of the dispatch mode and of charging and flights.

Random Incidents (Feature 021D-2) is a third independent mode with its own persisted state: reset
to OFF at startup, and while ON the worker makes one attempt after each random real-time pause
(`app.simulation.incident_scheduler`), triggering at most one incident through the existing
incident services. It never stops the loop or the flight updates.

Drone recovery (Feature 022) is not a mode: every `drone_recovery_check_seconds` the worker looks
for drones grounded by a drone failure (automatic or manual) whose delay has passed and moves a few
of them to a Hub (`app.simulation.recovery`). Everything it needs is stored, so a restart loses
nothing, and it does not depend on Random Incidents being ON.
"""

import logging
import time

from sqlalchemy.orm import sessionmaker

from app.config import Settings, get_settings
from app.db.session import get_engine
from app.dispatch import auto
from app.orders import simulation as order_simulation
from app.simulation import clock, engine, random_incidents
from app.simulation.charging import ChargingState, charge_step
from app.simulation.incident_scheduler import IncidentScheduler
from app.simulation.recovery import RecoveryState, run_recovery_step

logger = logging.getLogger("skyfleet.worker")


def run_tick(tick_number: int) -> None:
    """Advance the simulation by one step. Currently a heartbeat only."""
    logger.info("Simulation tick %d", tick_number)


def run_forever(settings: Settings) -> None:
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    tick_number = 0
    charging = ChargingState()
    mode_reset = False  # no automatic dispatch until the mode has been reset to OFF
    next_dispatch_at = 0.0
    orders_reset = False  # no order generation until the mode has been reset to OFF
    order_schedule = order_simulation.GenerationSchedule(settings)
    incidents_reset = False  # no random incident until the mode has been reset to OFF
    incident_scheduler = IncidentScheduler(settings)
    recovery = RecoveryState()
    next_recovery_at = 0.0
    while True:
        tick_number += 1
        run_tick(tick_number)
        try:
            engine.run_step(factory, settings, clock.utcnow())
        except Exception:  # a failed tick must not stop the worker; the next one retries
            logger.exception("Simulation step failed")

        try:  # docked drones below 100% charge, whatever the dispatch mode is
            charge_step(factory, settings, clock.utcnow(), charging)
        except Exception:
            logger.exception("Charging step failed")

        try:
            if not mode_reset:
                with factory() as session:
                    auto.reset_to_off(session, clock.utcnow())
                mode_reset = True
                logger.info("Automatic dispatch is OFF")
            elif time.monotonic() >= next_dispatch_at:
                next_dispatch_at = time.monotonic() + settings.dispatch_auto_interval_seconds
                auto.run_dispatch_pass(factory, settings, clock.utcnow())
        except Exception:  # the dispatcher must never take the worker down
            logger.exception("Automatic dispatch pass failed")

        try:  # automatic order generation: its own mode, schedule and failure handling
            if not orders_reset:
                with factory() as session:
                    order_simulation.reset_to_off(session, clock.utcnow())
                orders_reset = True
                logger.info("Order simulation is OFF")
            elif order_schedule.poll(order_simulation.is_enabled(factory), time.monotonic()):
                order_simulation.run_generation_step(factory, settings, clock.utcnow())
        except Exception:  # order generation must never take the worker down
            logger.exception("Order generation step failed")

        try:  # random incidents: their own mode, schedule, cooldowns and failure handling
            if not incidents_reset:
                with factory() as session:
                    random_incidents.reset_to_off(session, clock.utcnow())
                incidents_reset = True
                logger.info("Random incidents are OFF")
            elif incident_scheduler.poll(random_incidents.is_enabled(factory), time.monotonic()):
                incident_scheduler.run_step(factory, clock.utcnow(), time.monotonic())
        except Exception:  # incidents must never take the worker down
            logger.exception("Random incident step failed")

        try:  # drones grounded by a drone failure return to a Hub after the recovery delay
            if time.monotonic() >= next_recovery_at:
                next_recovery_at = time.monotonic() + settings.drone_recovery_check_seconds
                run_recovery_step(factory, settings, clock.utcnow(), recovery)
        except Exception:  # recovery must never take the worker down
            logger.exception("Drone recovery step failed")
        time.sleep(settings.sim_tick_seconds)


def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("Simulation Worker started (tick interval: %.2fs)", settings.sim_tick_seconds)
    try:
        run_forever(settings)
    except KeyboardInterrupt:
        logger.info("Simulation Worker stopped")


if __name__ == "__main__":
    main()

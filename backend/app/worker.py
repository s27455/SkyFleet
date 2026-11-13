"""Simulation Worker entrypoint: `uv run python -m app.worker`.

Runs as its own process, independent of the API and of any browser session. Each tick records a
heartbeat (a mission can only start while it is fresh) and advances every active flight
(`app.simulation.engine`). Flight state is derived from stored schedules and the clock, so a
restart neither resets nor invents progress.

The worker also owns the automatic dispatch loop (Feature 014C): it resets the mode to OFF when it
starts, and while the operator has switched it ON it runs a dispatch pass every
`DISPATCH_AUTO_INTERVAL_SECONDS`. API and browser are not involved in dispatching. Each tick it
also charges docked drones below 100% (Feature 014D), whatever the dispatch mode is.
"""

import logging
import time

from sqlalchemy.orm import sessionmaker

from app.config import Settings, get_settings
from app.db.session import get_engine
from app.dispatch import auto
from app.simulation import clock, engine
from app.simulation.charging import ChargingState, charge_step

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

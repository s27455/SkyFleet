"""Simulation Worker entrypoint: `uv run python -m app.worker`.

Runs as its own process, independent of the API and of any browser session. Each tick records a
heartbeat (a mission can only start while it is fresh) and advances every active flight
(`app.simulation.engine`). Flight state is derived from stored schedules and the clock, so a
restart neither resets nor invents progress.
"""

import logging
import time

from sqlalchemy.orm import sessionmaker

from app.config import Settings, get_settings
from app.db.session import get_engine
from app.simulation import clock, engine

logger = logging.getLogger("skyfleet.worker")


def run_tick(tick_number: int) -> None:
    """Advance the simulation by one step. Currently a heartbeat only."""
    logger.info("Simulation tick %d", tick_number)


def run_forever(settings: Settings) -> None:
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    tick_number = 0
    while True:
        tick_number += 1
        run_tick(tick_number)
        try:
            engine.run_step(factory, settings, clock.utcnow())
        except Exception:  # a failed tick must not stop the worker; the next one retries
            logger.exception("Simulation step failed")
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

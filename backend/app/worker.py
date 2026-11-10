"""Simulation Worker entrypoint: `uv run python -m app.worker`.

Runs as its own process, independent of the API and of any browser session.
Phase 1 only proves the process model with a heartbeat; simulation logic arrives in Phase 7.
"""

import logging
import time

from app.config import get_settings

logger = logging.getLogger("skyfleet.worker")


def run_tick(tick_number: int) -> None:
    """Advance the simulation by one step. Currently a heartbeat only."""
    logger.info("Simulation tick %d", tick_number)


def run_forever(tick_seconds: float) -> None:
    tick_number = 0
    while True:
        tick_number += 1
        run_tick(tick_number)
        time.sleep(tick_seconds)


def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("Simulation Worker started (tick interval: %.2fs)", settings.sim_tick_seconds)
    try:
        run_forever(settings.sim_tick_seconds)
    except KeyboardInterrupt:
        logger.info("Simulation Worker stopped")


if __name__ == "__main__":
    main()

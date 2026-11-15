"""Automatic random incidents (Feature 021D-2): the schedule and the step the worker runs.

While the operator has Random Incidents ON (`random_incidents.py`), the worker makes one *attempt*
after a random real-time pause (180 to 300 s by default). An attempt triggers at most ONE incident
through the same services the manual controls call (LPR helicopter, recipient unavailable, drone
failure), with the AUTOMATIC origin; Rain Warning and Cancel Order stay manual-only. An attempt may
well be skipped, so an incident is never promised for every interval.

* Timing lives in the worker's memory: only the next due time is kept and it is always recomputed
  from "now", so a restart or a stall never causes a burst. The first look at the ON mode only
  starts the first pause: enabling never triggers an incident immediately. Turning OFF forgets the
  schedule and the cooldowns, and does not undo an incident already in progress.
* Type selection: the configured weights give a random order of the types that are not in
  cooldown. They are tried in that order within the SAME attempt until one triggers; a type with
  no eligible target, an LPR pass already running, or a refused fleet guard is skipped. Nothing is
  retried, and no cooldown, fleet guard or mission-overlap rule is bypassed.
* Cooldown: after a SUCCESSFUL trigger that type waits a random 120 to 180 s. Skipped and failed
  attempts start none.
* Safety (drone failure only): `automatic_safety=True` skips flights another incident already
  affects and applies the fleet guard, both rechecked under the transaction locks (`failure.py`).
* Observability: the time and a short outcome are stored in the state row; a skipped attempt is not
  a mission event. An unexpected error is logged in the worker and stored only as a generic
  outcome, never with its details.
"""

import logging
import random
from collections.abc import Callable, Mapping
from datetime import datetime
from enum import StrEnum

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.events.models import EventOrigin
from app.simulation import lpr, random_incidents
from app.simulation.failed_delivery import trigger_recipient_unavailable
from app.simulation.failure import FleetGuardError, NoEligibleTargetError, trigger_drone_failure

logger = logging.getLogger("skyfleet.incidents")

ERROR_OUTCOME = "Error: the incident attempt failed (see the worker log)"


class IncidentType(StrEnum):
    LPR_HELICOPTER = "LPR_HELICOPTER"
    RECIPIENT_UNAVAILABLE = "RECIPIENT_UNAVAILABLE"
    DRONE_FAILURE = "DRONE_FAILURE"


LABELS: Mapping[IncidentType, str] = {
    IncidentType.LPR_HELICOPTER: "LPR helicopter",
    IncidentType.RECIPIENT_UNAVAILABLE: "Recipient unavailable",
    IncidentType.DRONE_FAILURE: "Drone failure",
}


class SkipError(Exception):
    """This type cannot be triggered now; nothing was changed. Carries a short reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# A trigger runs in its own session and returns a short description, or raises `SkipError`.
Trigger = Callable[[Session, datetime, Settings, random.Random], str]


def _lpr(session: Session, now: datetime, settings: Settings, rng: random.Random) -> str:
    try:
        lpr.start_scenario(session, now, settings, origin=EventOrigin.AUTOMATIC)
    except lpr.LprAlreadyActiveError:
        raise SkipError("already crossing the area") from None
    return "LPR helicopter started"


def _recipient(session: Session, now: datetime, settings: Settings, rng: random.Random) -> str:
    try:
        result = trigger_recipient_unavailable(
            session, now, settings, origin=EventOrigin.AUTOMATIC, rng=rng
        )
    except NoEligibleTargetError:
        raise SkipError("no eligible delivery") from None
    return f"recipient unavailable reported for {result.order_id} (drone {result.drone_id})"


def _failure(session: Session, now: datetime, settings: Settings, rng: random.Random) -> str:
    try:
        result = trigger_drone_failure(
            session,
            now,
            settings,
            origin=EventOrigin.AUTOMATIC,
            rng=rng,
            automatic_safety=True,
        )
    except NoEligibleTargetError:
        raise SkipError("no eligible flight") from None
    except FleetGuardError:
        raise SkipError("fleet guard") from None
    return f"drone {result.drone_id} failed (mission {result.mission_id})"


TRIGGERS: Mapping[IncidentType, Trigger] = {
    IncidentType.LPR_HELICOPTER: _lpr,
    IncidentType.RECIPIENT_UNAVAILABLE: _recipient,
    IncidentType.DRONE_FAILURE: _failure,
}


class IncidentScheduler:
    """When the next attempt is due and which types are cooling down (monotonic seconds)."""

    def __init__(
        self,
        settings: Settings,
        rng: random.Random | None = None,
        triggers: Mapping[IncidentType, Trigger] | None = None,
    ) -> None:
        self._settings = settings
        self._rng = rng or random.Random()
        self._triggers = triggers or TRIGGERS
        self._next_at: float | None = None
        self._cooldown_until: dict[IncidentType, float] = {}
        self._weights: Mapping[IncidentType, float] = {
            IncidentType.LPR_HELICOPTER: settings.incident_sim_weight_lpr,
            IncidentType.RECIPIENT_UNAVAILABLE: settings.incident_sim_weight_recipient,
            IncidentType.DRONE_FAILURE: settings.incident_sim_weight_failure,
        }

    def _pause(self) -> float:
        return self._rng.uniform(
            self._settings.incident_sim_min_interval_seconds,
            self._settings.incident_sim_max_interval_seconds,
        )

    def poll(self, enabled: bool, now: float) -> bool:
        """True when an attempt is due now. Turning OFF forgets the schedule and the cooldowns, and
        the first poll after turning ON only schedules, so enabling never triggers immediately."""
        if not enabled:
            self._next_at = None
            self._cooldown_until.clear()
            return False
        if self._next_at is None:
            self._next_at = now + self._pause()
            return False
        if now < self._next_at:
            return False
        self._next_at = now + self._pause()  # from now, never from the missed due time
        return True

    def in_cooldown(self, incident_type: IncidentType, now: float) -> bool:
        return self._cooldown_until.get(incident_type, 0.0) > now

    def _start_cooldown(self, incident_type: IncidentType, now: float) -> None:
        self._cooldown_until[incident_type] = now + self._rng.uniform(
            self._settings.incident_sim_cooldown_min_seconds,
            self._settings.incident_sim_cooldown_max_seconds,
        )

    def _order(self, types: list[IncidentType]) -> list[IncidentType]:
        """A random order biased by the weights (without replacement); weight 0 is never tried."""
        pool = [t for t in types if self._weights[t] > 0]
        ordered: list[IncidentType] = []
        while pool:
            pick = self._rng.choices(pool, weights=[self._weights[t] for t in pool])[0]
            ordered.append(pick)
            pool.remove(pick)
        return ordered

    def run_step(
        self, factory: sessionmaker[Session], now: datetime, monotonic_now: float
    ) -> str | None:
        """One attempt; returns its summary, or None when the mode is OFF (or turned OFF meanwhile).

        Never raises for an incident problem: it is recorded as the outcome and the next scheduled
        attempt simply tries again.
        """
        if not random_incidents.is_enabled(factory):
            return None

        enabled_types = [t for t in IncidentType if self._weights[t] > 0]
        cooling = [t for t in enabled_types if self.in_cooldown(t, monotonic_now)]
        available = self._order([t for t in enabled_types if t not in cooling])
        reasons = [f"{LABELS[t]}: cooldown" for t in cooling]

        outcome: str | None = None
        error: Exception | None = None
        for incident_type in available:
            if not random_incidents.is_enabled(factory):  # turned OFF meanwhile: trigger nothing
                return None
            try:
                with factory() as session:
                    description = self._triggers[incident_type](
                        session, now, self._settings, self._rng
                    )
            except SkipError as skip:
                reasons.append(f"{LABELS[incident_type]}: {skip.reason}")
                continue
            except Exception as caught:  # recorded generically; the details go to the worker log
                error = caught
                outcome = ERROR_OUTCOME
                break
            self._start_cooldown(incident_type, monotonic_now)  # only a successful trigger
            outcome = f"Triggered: {description}"
            break
        if outcome is None:
            outcome = "Skipped: " + ("; ".join(reasons) if reasons else "no incident type enabled")

        random_incidents.record_attempt(factory, now, outcome)
        if error is not None:
            logger.error("Random incidents: attempt failed", exc_info=error)
        else:
            logger.info("Random incidents: %s", outcome)
        return outcome

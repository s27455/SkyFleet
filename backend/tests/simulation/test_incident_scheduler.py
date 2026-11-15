"""The random incident schedule, cooldowns and attempt step (Feature 021D-2).

Fake triggers, a controllable clock and a seeded random source: nothing here waits, and no real
incident service is involved (those are covered in `test_automatic_incident_safety.py`).
"""

import logging
import random
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app import worker
from app.common import clock
from app.config import Settings
from app.dispatch.models import DispatchAutoState
from app.events.models import OperationalEvent
from app.simulation import random_incidents
from app.simulation.heartbeat import record_heartbeat
from app.simulation.incident_scheduler import (
    ERROR_OUTCOME,
    LABELS,
    TRIGGERS,
    IncidentScheduler,
    IncidentType,
    SkipError,
    Trigger,
)
from app.simulation.models import RANDOM_INCIDENTS, IncidentSchedulerState

Factory = sessionmaker[Session]
NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
LPR, RECIPIENT, FAILURE = (
    IncidentType.LPR_HELICOPTER,
    IncidentType.RECIPIENT_UNAVAILABLE,
    IncidentType.DRONE_FAILURE,
)


def make_settings(**overrides: float) -> Settings:
    values: dict[str, float] = {
        "incident_sim_min_interval_seconds": 180,
        "incident_sim_max_interval_seconds": 300,
        "incident_sim_cooldown_min_seconds": 120,
        "incident_sim_cooldown_max_seconds": 180,
        "incident_sim_weight_lpr": 0.4,
        "incident_sim_weight_recipient": 0.4,
        "incident_sim_weight_failure": 0.2,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


class Fakes:
    """Triggers that count their calls and either succeed or skip, per type."""

    def __init__(self, behaviour: dict[IncidentType, str] | None = None) -> None:
        self.calls: list[IncidentType] = []
        self.behaviour = {LPR: "ok", RECIPIENT: "ok", FAILURE: "ok", **(behaviour or {})}

    def trigger_for(self, incident_type: IncidentType) -> Trigger:
        def run(_session: Session, _now: datetime, _settings: Settings, _rng: random.Random) -> str:
            self.calls.append(incident_type)
            what = self.behaviour[incident_type]
            if what == "skip":
                raise SkipError("nothing eligible")
            if what == "boom":
                raise RuntimeError("secret internal detail")
            return f"{incident_type.value} done"

        return run

    def mapping(self) -> dict[IncidentType, Trigger]:
        return {t: self.trigger_for(t) for t in IncidentType}


def scheduler(fakes: Fakes, settings: Settings | None = None, seed: int = 1) -> IncidentScheduler:
    return IncidentScheduler(
        settings or make_settings(), rng=random.Random(seed), triggers=fakes.mapping()
    )


def turn_on(session_factory: Factory, session: Session) -> None:
    record_heartbeat(session, clock.utcnow())
    with session_factory() as s:
        random_incidents.enable(s, clock.utcnow(), Settings())


# --- schedule ---------------------------------------------------------------------------------


def test_the_first_poll_after_turning_on_only_schedules() -> None:
    sched = scheduler(Fakes())

    assert sched.poll(True, 1000.0) is False  # enabling never triggers immediately
    assert sched.poll(True, 1000.0 + 179.9) is False  # before the shortest pause


def test_an_attempt_is_due_within_the_interval_bounds() -> None:
    for seed in range(20):
        sched = scheduler(Fakes(), seed=seed)
        sched.poll(True, 0.0)

        assert sched.poll(True, 179.9) is False
        assert sched.poll(True, 300.0) is True  # never later than the longest pause


def test_a_fixed_interval_is_exact() -> None:
    sched = scheduler(
        Fakes(),
        make_settings(incident_sim_min_interval_seconds=200, incident_sim_max_interval_seconds=200),
    )
    sched.poll(True, 0.0)

    assert sched.poll(True, 199.9) is False
    assert sched.poll(True, 200.0) is True
    assert sched.poll(True, 399.9) is False
    assert sched.poll(True, 400.0) is True


def test_the_next_pause_counts_from_now_not_from_the_missed_due_time() -> None:
    sched = scheduler(Fakes())
    sched.poll(True, 0.0)

    assert sched.poll(True, 10_000.0) is True  # a long stall: one attempt, not a burst
    assert sched.poll(True, 10_000.0 + 100) is False
    assert sched.poll(True, 10_000.0 + 300.1) is True


def test_turning_off_forgets_the_schedule_and_the_cooldowns(
    session_factory: Factory, session: Session
) -> None:
    fakes = Fakes()
    sched = scheduler(fakes)
    turn_on(session_factory, session)
    sched.poll(True, 0.0)
    sched.run_step(session_factory, NOW, 500.0)
    assert any(sched.in_cooldown(t, 501.0) for t in IncidentType)

    assert sched.poll(False, 600.0) is False

    assert not any(sched.in_cooldown(t, 601.0) for t in IncidentType)
    assert sched.poll(True, 700.0) is False  # ON again: it only schedules afresh
    assert sched.poll(True, 700.0 + 179.9) is False


# --- one attempt ------------------------------------------------------------------------------


def test_nothing_happens_while_the_mode_is_off(session_factory: Factory) -> None:
    fakes = Fakes()

    assert scheduler(fakes).run_step(session_factory, NOW, 0.0) is None

    assert fakes.calls == []


def test_an_attempt_triggers_at_most_one_incident(
    session_factory: Factory, session: Session
) -> None:
    fakes = Fakes()
    turn_on(session_factory, session)

    outcome = scheduler(fakes).run_step(session_factory, NOW, 0.0)

    assert outcome is not None and outcome.startswith("Triggered: ")
    assert len(fakes.calls) == 1


def test_a_type_without_a_target_is_skipped_and_another_type_is_tried_in_the_same_cycle(
    session_factory: Factory, session: Session
) -> None:
    fakes = Fakes({LPR: "skip", RECIPIENT: "skip"})
    turn_on(session_factory, session)
    sched = scheduler(fakes)

    outcome = sched.run_step(session_factory, NOW, 0.0)

    assert outcome == f"Triggered: {FAILURE.value} done"
    assert fakes.calls[-1] == FAILURE and len(fakes.calls) <= 3
    assert not sched.in_cooldown(LPR, 1.0) and not sched.in_cooldown(RECIPIENT, 1.0)
    assert sched.in_cooldown(FAILURE, 1.0)  # only the successful type cools down


def test_when_every_type_is_skipped_the_attempt_is_recorded_as_skipped_without_cooldown(
    session_factory: Factory, session: Session
) -> None:
    fakes = Fakes({LPR: "skip", RECIPIENT: "skip", FAILURE: "skip"})
    turn_on(session_factory, session)
    sched = scheduler(fakes)

    outcome = sched.run_step(session_factory, NOW, 0.0)

    assert outcome is not None and outcome.startswith("Skipped: ")
    for incident_type in IncidentType:
        assert f"{LABELS[incident_type]}: nothing eligible" in outcome
    assert len(fakes.calls) == 3  # each type once, no retries
    assert not any(sched.in_cooldown(t, 1.0) for t in IncidentType)
    row = session.get(IncidentSchedulerState, RANDOM_INCIDENTS)
    session.refresh(row)
    assert row is not None and row.last_outcome == outcome and row.last_check_at is not None


def test_a_skipped_attempt_is_not_a_mission_event(
    session_factory: Factory, session: Session
) -> None:
    fakes = Fakes({LPR: "skip", RECIPIENT: "skip", FAILURE: "skip"})
    turn_on(session_factory, session)
    before = session.scalar(select(func.count()).select_from(OperationalEvent))

    scheduler(fakes).run_step(session_factory, NOW, 0.0)

    assert session.scalar(select(func.count()).select_from(OperationalEvent)) == before


def test_a_cooldown_follows_a_successful_trigger_and_lasts_120_to_180_seconds(
    session_factory: Factory, session: Session
) -> None:
    for seed in range(15):
        fakes = Fakes()
        turn_on(session_factory, session)
        sched = scheduler(fakes, seed=seed)

        sched.run_step(session_factory, NOW, 1000.0)

        (triggered,) = fakes.calls
        assert sched.in_cooldown(triggered, 1000.0 + 119.9)
        assert not sched.in_cooldown(triggered, 1000.0 + 180.0)


def test_a_type_in_cooldown_is_not_tried_again_until_it_expires(
    session_factory: Factory, session: Session
) -> None:
    fixed = make_settings(
        incident_sim_cooldown_min_seconds=150, incident_sim_cooldown_max_seconds=150
    )
    fakes = Fakes()
    turn_on(session_factory, session)
    sched = scheduler(fakes, fixed)
    sched.run_step(session_factory, NOW, 0.0)
    (first,) = fakes.calls

    sched.run_step(session_factory, NOW, 149.0)  # the first type is still cooling down
    assert fakes.calls[1] != first

    sched.run_step(session_factory, NOW, 149.0)  # now two types cool down: only one is left
    assert len(set(fakes.calls[:3])) == 3

    fakes.calls.clear()
    outcome = sched.run_step(session_factory, NOW, 149.5)  # every type cools down
    assert fakes.calls == []
    assert outcome is not None and outcome.startswith("Skipped: ")
    assert outcome.count("cooldown") == 3

    sched.run_step(session_factory, NOW, 400.0)  # all expired
    assert len(fakes.calls) == 1


def test_a_zero_weight_type_is_never_tried(session_factory: Factory, session: Session) -> None:
    only_lpr = make_settings(incident_sim_weight_recipient=0, incident_sim_weight_failure=0)
    fakes = Fakes()
    turn_on(session_factory, session)
    sched = scheduler(fakes, only_lpr)

    for t in range(5):
        sched.run_step(session_factory, NOW, 1000.0 * (t + 1))

    assert set(fakes.calls) == {LPR}


def test_the_weights_bias_which_type_is_tried_first() -> None:
    sched = scheduler(Fakes(), seed=5)
    firsts = [sched._order(list(IncidentType))[0] for _ in range(4000)]

    shares = {t: firsts.count(t) / len(firsts) for t in IncidentType}

    assert shares[LPR] == pytest.approx(0.4, abs=0.04)
    assert shares[RECIPIENT] == pytest.approx(0.4, abs=0.04)
    assert shares[FAILURE] == pytest.approx(0.2, abs=0.04)
    assert sorted(sched._order(list(IncidentType)), key=str) == sorted(IncidentType, key=str)


def test_an_unexpected_error_is_recorded_generically_logged_and_ends_the_attempt(
    session_factory: Factory, session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    fakes = Fakes({LPR: "boom", RECIPIENT: "boom", FAILURE: "boom"})
    turn_on(session_factory, session)
    sched = scheduler(fakes)

    with caplog.at_level(logging.INFO, logger="skyfleet.incidents"):
        outcome = sched.run_step(session_factory, NOW, 0.0)

    assert outcome == ERROR_OUTCOME
    assert "secret internal detail" not in (outcome or "")
    row = session.get(IncidentSchedulerState, RANDOM_INCIDENTS)
    session.refresh(row)
    assert row is not None and "secret" not in (row.last_outcome or "")
    assert len(fakes.calls) == 1  # the attempt ended: no other type was tried
    assert not any(sched.in_cooldown(t, 1.0) for t in IncidentType)  # no cooldown after an error
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1 and errors[0].exc_info is not None

    fakes.behaviour = {LPR: "ok", RECIPIENT: "ok", FAILURE: "ok"}
    again = sched.run_step(session_factory, NOW, 10.0)  # the next attempt simply works
    assert again is not None and again.startswith("Triggered: ")


def test_a_mode_switched_off_meanwhile_triggers_nothing(
    session_factory: Factory, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    fakes = Fakes()
    turn_on(session_factory, session)
    answers = iter([True, False])  # ON at the start, OFF just before the trigger
    monkeypatch.setattr(random_incidents, "is_enabled", lambda _factory: next(answers))

    assert scheduler(fakes).run_step(session_factory, NOW, 0.0) is None

    assert fakes.calls == []


def test_the_real_triggers_are_the_existing_incident_services() -> None:
    assert set(TRIGGERS) == set(IncidentType) == {LPR, RECIPIENT, FAILURE}  # no rain, no cancel


# --- settings ---------------------------------------------------------------------------------


def test_the_defaults_are_the_approved_values() -> None:
    settings = Settings()

    assert (
        settings.incident_sim_min_interval_seconds,
        settings.incident_sim_max_interval_seconds,
    ) == (
        180,
        300,
    )
    assert (
        settings.incident_sim_cooldown_min_seconds,
        settings.incident_sim_cooldown_max_seconds,
    ) == (120, 180)
    assert (
        settings.incident_sim_weight_lpr,
        settings.incident_sim_weight_recipient,
        settings.incident_sim_weight_failure,
    ) == (0.4, 0.4, 0.2)


def test_inconsistent_settings_are_rejected() -> None:
    with pytest.raises(ValueError, match="INCIDENT_SIM_MAX_INTERVAL"):
        make_settings(incident_sim_min_interval_seconds=10, incident_sim_max_interval_seconds=5)
    with pytest.raises(ValueError, match="INCIDENT_SIM_COOLDOWN_MAX"):
        make_settings(incident_sim_cooldown_min_seconds=10, incident_sim_cooldown_max_seconds=5)
    with pytest.raises(ValueError, match="INCIDENT_SIM_WEIGHT"):
        make_settings(
            incident_sim_weight_lpr=0,
            incident_sim_weight_recipient=0,
            incident_sim_weight_failure=0,
        )


def test_the_environment_configures_the_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INCIDENT_SIM_MIN_INTERVAL_SECONDS", "5")
    monkeypatch.setenv("INCIDENT_SIM_MAX_INTERVAL_SECONDS", "9")

    settings = Settings()

    assert (
        settings.incident_sim_min_interval_seconds,
        settings.incident_sim_max_interval_seconds,
    ) == (
        5,
        9,
    )


# --- worker loop ------------------------------------------------------------------------------


class StopLoopError(Exception):
    pass


def _run_worker(
    monkeypatch: pytest.MonkeyPatch,
    engine: Engine,
    settings: Settings,
    ticks: int,
    after_tick: dict[int, object] | None = None,
) -> None:
    """Run the real `run_forever` for a fixed number of ticks with a fake clock and no waiting."""
    count = {"ticks": 0}
    fake_clock = {"now": 0.0}

    def monotonic() -> float:
        fake_clock["now"] += 100.0
        return fake_clock["now"]

    def sleep(_seconds: float) -> None:
        count["ticks"] += 1
        hook = (after_tick or {}).get(count["ticks"])
        if callable(hook):
            hook()
        if count["ticks"] >= ticks:
            raise StopLoopError

    monkeypatch.setattr(worker, "get_engine", lambda: engine)
    monkeypatch.setattr("app.worker.time.sleep", sleep)
    monkeypatch.setattr("app.worker.time.monotonic", monotonic)
    with pytest.raises(StopLoopError):
        worker.run_forever(settings)


def test_the_worker_resets_the_mode_then_schedules_then_triggers_one_incident(
    seeded: Session, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = make_settings(
        incident_sim_min_interval_seconds=180, incident_sim_max_interval_seconds=180
    )
    record_heartbeat(seeded, clock.utcnow())
    random_incidents.enable(seeded, clock.utcnow(), Settings())  # left ON by an earlier worker run
    fakes = Fakes()
    monkeypatch.setattr(
        "app.worker.IncidentScheduler",
        lambda s: IncidentScheduler(s, rng=random.Random(1), triggers=fakes.mapping()),
    )

    def operator_enables() -> None:
        with factory() as session:
            random_incidents.enable(session, clock.utcnow(), Settings())

    # tick 1 resets to OFF (nothing triggers); the operator then enables; tick 2 only schedules.
    _run_worker(monkeypatch, engine, settings, ticks=2, after_tick={1: operator_enables})
    assert fakes.calls == []
    row = seeded.get(IncidentSchedulerState, RANDOM_INCIDENTS)
    seeded.refresh(row)
    assert row is not None and row.enabled is True

    _run_worker(monkeypatch, engine, settings, ticks=4, after_tick={1: operator_enables})

    assert len(fakes.calls) >= 1
    seeded.refresh(row)
    assert (row.last_outcome or "").startswith("Triggered: ")


def test_an_incident_scheduler_failure_never_stops_the_worker(
    seeded: Session, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_factory: Factory) -> bool:
        raise RuntimeError("scheduler broke")

    monkeypatch.setattr("app.worker.random_incidents.is_enabled", boom)

    _run_worker(monkeypatch, engine, make_settings(), ticks=4)  # only the StopLoopError escapes

    # The loop kept running its other steps: Automatic Dispatch was reset to OFF in tick 1.
    dispatch_row = seeded.get(DispatchAutoState, "auto-dispatch")
    assert dispatch_row is not None and not dispatch_row.enabled

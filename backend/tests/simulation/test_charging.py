"""Automatic charging of docked drones (feature 014D), with a controlled clock on SQLite."""

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app import worker
from app.config import Settings
from app.dispatch import auto
from app.drones.models import Drone, DroneStatus
from app.missions import service as missions_service
from app.missions.models import Mission
from app.simulation import engine as flight_engine
from app.simulation.charging import ChargingState, charge_step
from app.simulation.heartbeat import record_heartbeat

NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
Factory = sessionmaker[Session]

# Seeded at Forum: DRN-007 (100 %), DRN-008 (90 %), DRN-009 (80 %); the other Hubs are alike.


@pytest.fixture
def fast(sim_settings: Settings) -> Settings:
    """One percent per second, so the arithmetic in the tests is easy to follow."""
    return sim_settings.model_copy(update={"sim_charge_rate_pct_per_minute": 60.0})


def at(seconds: float) -> datetime:
    return NOW + timedelta(seconds=seconds)


def _drone(session: Session, drone_id: str) -> Drone:
    session.expire_all()
    drone = session.get(Drone, drone_id)
    assert drone is not None
    return drone


def _steps(
    factory: Factory, settings: Settings, state: ChargingState, start: int, stop: int
) -> None:
    for second in range(start, stop + 1):
        charge_step(factory, settings, at(second), state)


# --- starting, progressing, finishing ---------------------------------------------------------


def test_docked_drones_below_full_start_charging_without_a_jump(
    seeded: Session, session_factory: Factory, fast: Settings
) -> None:
    changed = charge_step(session_factory, fast, at(0), ChargingState())

    assert changed == 8  # every docked drone below 100 %
    for drone_id, battery in (("DRN-008", 90), ("DRN-009", 80)):
        drone = _drone(seeded, drone_id)
        assert (drone.status, drone.battery_pct) == (DroneStatus.CHARGING, battery)
    full = _drone(seeded, "DRN-007")
    assert (full.status, full.battery_pct) == (DroneStatus.IDLE, 100)  # untouched


def test_the_battery_rises_tick_by_tick_and_ends_at_exactly_100_and_idle(
    seeded: Session, session_factory: Factory, fast: Settings
) -> None:
    state = ChargingState()
    charge_step(session_factory, fast, at(0), state)  # starts charging

    _steps(session_factory, fast, state, 1, 5)
    mid = _drone(seeded, "DRN-008")
    assert (mid.status, mid.battery_pct) == (DroneStatus.CHARGING, 95)

    _steps(session_factory, fast, state, 6, 10)
    done = _drone(seeded, "DRN-008")
    assert (done.status, done.battery_pct) == (DroneStatus.IDLE, 100)

    _steps(session_factory, fast, state, 11, 40)  # never above 100, nothing more to do
    assert _drone(seeded, "DRN-008").battery_pct == 100
    assert _drone(seeded, "DRN-009").battery_pct == 100  # 80 % -> 100 % after 20 ticks
    assert _drone(seeded, "DRN-009").status == DroneStatus.IDLE


def test_a_slow_rate_accumulates_fractions_and_never_adds_more_than_a_whole_step(
    seeded: Session, session_factory: Factory, sim_settings: Settings
) -> None:
    state = ChargingState()  # the default rate: 20 % a minute, one third of a percent a second
    charge_step(session_factory, sim_settings, at(0), state)
    readings = []
    for second in range(1, 31):
        charge_step(session_factory, sim_settings, at(second), state)
        readings.append(_drone(seeded, "DRN-008").battery_pct)

    assert readings == sorted(readings)
    assert all(b - a <= 1 for a, b in zip([90, *readings], readings, strict=False))
    assert 99 <= readings[-1] <= 100  # 30 s at 1/3 % a second is 10 %, minus float rounding


def test_a_manually_full_charging_drone_becomes_idle(
    seeded: Session, session_factory: Factory, fast: Settings
) -> None:
    state = ChargingState()
    charge_step(session_factory, fast, at(0), state)
    drone = _drone(seeded, "DRN-008")
    drone.battery_pct = 100  # an operator sets it to full while it charges
    seeded.commit()

    charge_step(session_factory, fast, at(1), state)

    drone = _drone(seeded, "DRN-008")
    assert (drone.status, drone.battery_pct) == (DroneStatus.IDLE, 100)


def test_nothing_is_written_when_every_drone_is_full(
    seeded: Session, session_factory: Factory, fast: Settings
) -> None:
    for drone in seeded.scalars(select(Drone)):
        drone.battery_pct = 100
    seeded.commit()

    assert charge_step(session_factory, fast, at(0), ChargingState()) == 0


# --- restarts and clock anomalies -------------------------------------------------------------


def test_a_restart_mid_charge_resumes_without_a_burst(
    seeded: Session, session_factory: Factory, fast: Settings
) -> None:
    first = ChargingState()
    charge_step(session_factory, fast, at(0), first)
    _steps(session_factory, fast, first, 1, 4)
    before = _drone(seeded, "DRN-008").battery_pct
    assert before == 94

    # A new worker, hours later: its first tick counts one nominal tick, not the whole gap.
    charge_step(session_factory, fast, at(3 * 3600), ChargingState())

    after = _drone(seeded, "DRN-008")
    assert after.status == DroneStatus.CHARGING
    assert before <= after.battery_pct <= before + 1


def test_a_long_gap_between_ticks_adds_at_most_a_few_ticks_of_charge(
    seeded: Session, session_factory: Factory, fast: Settings
) -> None:
    state = ChargingState()
    charge_step(session_factory, fast, at(0), state)  # starts at 90

    charge_step(session_factory, fast, at(3600), state)  # a stall, or a forward clock jump

    gained = _drone(seeded, "DRN-008").battery_pct - 90
    assert 0 < gained <= 5  # clamped to five nominal ticks at one percent a second


def test_a_clock_that_goes_backwards_adds_nothing(
    seeded: Session, session_factory: Factory, fast: Settings
) -> None:
    state = ChargingState()
    charge_step(session_factory, fast, at(100), state)

    charge_step(session_factory, fast, at(50), state)

    drone = _drone(seeded, "DRN-008")
    assert (drone.status, drone.battery_pct) == (DroneStatus.CHARGING, 90)


# --- who must not charge ----------------------------------------------------------------------


def _maintenance(session: Session) -> None:
    _drone(session, "DRN-008").status = DroneStatus.MAINTENANCE.value


def _in_flight(session: Session) -> None:
    _drone(session, "DRN-008").status = DroneStatus.IN_FLIGHT.value


def _undocked_idle(session: Session) -> None:
    drone = _drone(session, "DRN-008")
    drone.longitude, drone.latitude = 18.7, 54.5


def _undocked_charging(session: Session) -> None:
    drone = _drone(session, "DRN-008")
    drone.status = DroneStatus.CHARGING.value
    drone.longitude, drone.latitude = 18.7, 54.5


def _active_mission(session: Session) -> None:
    # A manual mission may use a drone below 100 %; it then claims the drone.
    missions_service.confirm_mission(session, "ORD-004", "DRN-008", Settings())


@pytest.mark.parametrize(
    "setup",
    [_maintenance, _in_flight, _undocked_idle, _undocked_charging, _active_mission],
)
def test_these_drones_do_not_charge(
    seeded: Session, session_factory: Factory, fast: Settings, setup: Callable[[Session], None]
) -> None:
    setup(seeded)
    seeded.commit()
    start = _drone(seeded, "DRN-008")
    status, battery = start.status, start.battery_pct

    _steps(session_factory, fast, ChargingState(), 0, 12)

    drone = _drone(seeded, "DRN-008")
    assert (drone.status, drone.battery_pct) == (status, battery)


# --- operator edits ---------------------------------------------------------------------------


def test_a_manual_battery_edit_becomes_the_new_starting_point(
    seeded: Session, session_factory: Factory, fast: Settings
) -> None:
    state = ChargingState()
    charge_step(session_factory, fast, at(0), state)
    _steps(session_factory, fast, state, 1, 5)  # 95 %
    _drone(seeded, "DRN-008").battery_pct = 50
    seeded.commit()

    charge_step(session_factory, fast, at(6), state)

    assert _drone(seeded, "DRN-008").battery_pct in (50, 51)


def test_maintenance_set_during_charging_is_respected(
    seeded: Session, session_factory: Factory, fast: Settings
) -> None:
    state = ChargingState()
    charge_step(session_factory, fast, at(0), state)
    _steps(session_factory, fast, state, 1, 3)
    drone = _drone(seeded, "DRN-008")
    drone.status = DroneStatus.MAINTENANCE.value
    battery = drone.battery_pct
    seeded.commit()

    _steps(session_factory, fast, state, 4, 15)

    drone = _drone(seeded, "DRN-008")
    assert (drone.status, drone.battery_pct) == (DroneStatus.MAINTENANCE, battery)


# --- the whole cycle --------------------------------------------------------------------------


def test_a_landed_drone_charges_at_its_return_hub_and_becomes_idle(
    seeded: Session,
    session_factory: Factory,
    sim_settings: Settings,
    launch: Callable[..., str],
) -> None:
    fast = sim_settings.model_copy(update={"sim_charge_rate_pct_per_minute": 600.0})
    mission_id = launch("ORD-001", "DRN-010")
    flight_engine.advance_flight(session_factory, fast, mission_id, at(60))
    landed = _drone(seeded, "DRN-010")
    assert landed.status == DroneStatus.IDLE and landed.battery_pct < 100
    residual = landed.battery_pct

    state = ChargingState()
    charge_step(session_factory, fast, at(100), state)
    assert _drone(seeded, "DRN-010").status == DroneStatus.CHARGING
    assert _drone(seeded, "DRN-010").battery_pct == residual  # no instant jump

    _steps(session_factory, fast, state, 101, 120)  # 10 % a second
    done = _drone(seeded, "DRN-010")
    assert (done.status, done.battery_pct) == (DroneStatus.IDLE, 100)
    assert (done.longitude, done.latitude) == (landed.longitude, landed.latitude)  # same Hub


def test_with_dispatch_on_a_charged_drone_is_sent_on_a_later_pass(
    seeded: Session, session_factory: Factory, fast: Settings
) -> None:
    record_heartbeat(seeded, NOW)
    _drone(seeded, "DRN-007").battery_pct = 98
    seeded.commit()
    with session_factory() as session:
        auto.enable(session, NOW, fast)
    state = ChargingState()
    charge_step(session_factory, fast, at(0), state)  # DRN-007 starts charging at 98 %

    auto.run_dispatch_pass(session_factory, fast, at(1))  # still charging: not dispatched
    seeded.expire_all()
    assert "DRN-007" not in {m.drone_id for m in seeded.scalars(select(Mission))}

    _steps(session_factory, fast, state, 1, 2)  # 99 %, then 100 % and IDLE
    auto.run_dispatch_pass(session_factory, fast, at(3))

    seeded.expire_all()
    assert ("ORD-004", "DRN-007") in {
        (m.order_id, m.drone_id) for m in seeded.scalars(select(Mission))
    }


def test_with_dispatch_off_charging_continues_but_nothing_starts(
    seeded: Session, session_factory: Factory, fast: Settings
) -> None:
    record_heartbeat(seeded, NOW)
    state = ChargingState()
    charge_step(session_factory, fast, at(0), state)

    _steps(session_factory, fast, state, 1, 25)
    assert auto.run_dispatch_pass(session_factory, fast, at(26)) is None

    assert _drone(seeded, "DRN-009").battery_pct == 100
    assert seeded.scalars(select(Mission)).all() == []


# --- worker wiring ----------------------------------------------------------------------------


class StopWorkerError(Exception):
    pass


def test_the_worker_charges_each_tick_whatever_the_dispatch_mode(
    seeded: Session, engine: Engine, fast: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks = 0

    def stop_after_a_few_ticks(_seconds: float) -> None:
        nonlocal ticks
        ticks += 1
        if ticks >= 3:
            raise StopWorkerError

    monkeypatch.setattr(worker, "get_engine", lambda: engine)
    monkeypatch.setattr(time, "sleep", stop_after_a_few_ticks)  # the worker calls time.sleep

    with pytest.raises(StopWorkerError):
        worker.run_forever(fast)

    drone = _drone(seeded, "DRN-008")
    assert drone.status == DroneStatus.CHARGING
    assert drone.battery_pct >= 90

"""Simulation settings validation and the worker's per-tick behavior."""

import logging
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app import worker
from app.config import Settings
from app.simulation import engine
from app.simulation.heartbeat import is_fresh, last_heartbeat, record_heartbeat

NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)


def test_defaults_match_the_approved_simulation_parameters() -> None:
    settings = Settings(_env_file=None)

    assert settings.sim_flight_min_seconds == 30
    assert settings.sim_flight_max_seconds == 90
    assert settings.sim_delivery_dwell_seconds == 3
    assert settings.sim_landing_approach_m == 60
    assert settings.sim_critical_battery_pct == 5
    assert settings.sim_heartbeat_stale_seconds == 10


def test_the_landing_approach_must_exceed_the_dock_proximity() -> None:
    with pytest.raises(ValueError, match="SIM_LANDING_APPROACH_M"):
        Settings(_env_file=None, sim_landing_approach_m=50, hub_dock_proximity_m=50)


def test_the_flight_durations_must_be_consistent() -> None:
    with pytest.raises(ValueError, match="SIM_FLIGHT_MAX_SECONDS"):
        Settings(_env_file=None, sim_flight_min_seconds=60, sim_flight_max_seconds=30)
    with pytest.raises(ValueError, match="SIM_DELIVERY_DWELL_SECONDS"):
        Settings(_env_file=None, sim_flight_min_seconds=30, sim_delivery_dwell_seconds=30)


def test_environment_variables_configure_the_simulation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIM_FLIGHT_MAX_SECONDS", "120")
    monkeypatch.setenv("SIM_CRITICAL_BATTERY_PCT", "8")

    settings = Settings(_env_file=None)

    assert settings.sim_flight_max_seconds == 120
    assert settings.sim_critical_battery_pct == 8


def test_the_heartbeat_row_is_created_then_updated(session: Session) -> None:
    assert last_heartbeat(session) is None

    record_heartbeat(session, NOW)
    record_heartbeat(session, NOW + timedelta(seconds=1))

    assert last_heartbeat(session) == NOW + timedelta(seconds=1)


def test_a_heartbeat_is_fresh_up_to_the_limit_and_stale_after_it() -> None:
    assert is_fresh(NOW, NOW + timedelta(seconds=10), 10)
    assert not is_fresh(NOW, NOW + timedelta(seconds=10.5), 10)
    assert not is_fresh(None, NOW, 10)


def test_a_step_with_no_flights_still_records_the_heartbeat(
    session: Session, session_factory: sessionmaker[Session], sim_settings: Settings
) -> None:
    assert engine.run_step(session_factory, sim_settings, NOW) == 0

    session.expire_all()
    assert last_heartbeat(session) == NOW


def test_the_heartbeat_only_tick_still_logs(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="skyfleet.worker"):
        worker.run_tick(3)

    assert "Simulation tick 3" in caplog.text

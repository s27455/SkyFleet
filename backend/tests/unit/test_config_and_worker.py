import logging

import pytest

from app.config import Settings
from app.worker import run_tick


def test_cors_origins_parsed_from_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")

    settings = Settings(_env_file=None)

    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_tick_interval_must_be_positive() -> None:
    with pytest.raises(ValueError):
        Settings(sim_tick_seconds=0)


def test_run_tick_logs_heartbeat(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="skyfleet.worker"):
        run_tick(7)

    assert "Simulation tick 7" in caplog.text

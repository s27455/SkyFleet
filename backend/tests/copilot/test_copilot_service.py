"""The Copilot service: one Settings for everything, one call, fixed errors."""

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.ai.errors import AiError
from app.api.routes import copilot as copilot_route
from app.config import Settings
from app.copilot import service as copilot_service
from app.copilot.schemas import ErrorCode
from app.copilot.service import (
    MESSAGES,
    CopilotError,
    CopilotService,
    copilot_available,
    copilot_problems,
    map_ai_error,
)
from app.main import create_app

from .helpers import RigFactory, copilot_settings


class Recorder:
    """Stands in for `ask_fleet_question` and remembers exactly how it was called."""

    def __init__(self, error: BaseException | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.error = error

    def __call__(self, question: str, **kwargs: Any) -> Any:
        self.calls.append({"question": question, **kwargs})
        if self.error is not None:
            raise self.error
        raise AssertionError("not reached in these tests")


def build(settings: Settings, session_factory: sessionmaker[Session]) -> tuple[Any, list[Any]]:
    received: list[Any] = []

    def gateway_factory(given: Settings, factory: sessionmaker[Session]) -> Any:
        received.append((given, factory))
        return SimpleNamespace(marker="gateway")

    return CopilotService(settings, session_factory, gateway_factory=gateway_factory), received


# --- one Settings instance for the gateway and the fleet context -------------------------------


def test_the_gateway_and_the_fleet_context_share_one_settings_instance(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = copilot_settings()
    recorder = Recorder(error=AiError("stop"))
    monkeypatch.setattr(copilot_service, "ask_fleet_question", recorder)

    service, received = build(settings, session_factory)
    with pytest.raises(CopilotError):
        service.ask("How many drones?")

    (given, factory), (call,) = received[0], recorder.calls
    assert given is settings and call["settings"] is settings  # the very same object
    assert factory is session_factory and call["factory"] is session_factory
    assert call["gateway"].marker == "gateway"  # the gateway that was built from those settings


def test_the_service_builds_its_gateway_once_not_per_question(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(copilot_service, "ask_fleet_question", Recorder(error=AiError("stop")))
    service, received = build(copilot_settings(), session_factory)

    for _ in range(3):
        with pytest.raises(CopilotError):
            service.ask("q")

    assert len(received) == 1


def test_one_ask_is_one_fleet_question_call_whatever_happens(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    for error in (AiError("x"), RuntimeError("boom")):
        recorder = Recorder(error=error)
        monkeypatch.setattr(copilot_service, "ask_fleet_question", recorder)
        service, _ = build(copilot_settings(), session_factory)

        with pytest.raises(CopilotError):
            service.ask("q")

        assert len(recorder.calls) == 1  # never a retry, a fallback or a second attempt


def test_an_unexpected_exception_becomes_a_fixed_internal_error(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        copilot_service, "ask_fleet_question", Recorder(error=RuntimeError("SECRET-DETAIL"))
    )
    service, _ = build(copilot_settings(), session_factory)

    with pytest.raises(CopilotError) as caught:
        service.ask("q")

    assert (caught.value.code, caught.value.status) == (ErrorCode.INTERNAL_ERROR, 500)
    assert caught.value.message == MESSAGES[ErrorCode.INTERNAL_ERROR]
    assert "SECRET" not in str(caught.value) and caught.value.__cause__ is None


def test_an_error_nobody_mapped_is_an_internal_error_not_a_leak() -> None:
    mapped = map_ai_error(AiError("SECRET-DETAIL"))

    assert (mapped.code, mapped.status) == (ErrorCode.INTERNAL_ERROR, 500)
    assert "SECRET" not in mapped.message


def test_every_error_code_has_one_fixed_message() -> None:
    assert set(MESSAGES) == set(ErrorCode)
    assert all(message and "SECRET" not in message for message in MESSAGES.values())


# --- availability ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "available"),
    [
        ({}, True),
        ({"ai_enabled": False}, False),
        ({"ai_access_token": None}, False),
        ({"ai_access_token": "x" * 31}, False),
        ({"anthropic_api_key": None}, False),
        ({"ai_model": "claude-some-other-model"}, False),
        ({"ai_budget_ceiling_usd": 5}, False),  # above the MVP maximum
    ],
)
def test_availability_follows_the_gateway_readiness_and_the_token(
    overrides: dict[str, Any], available: bool
) -> None:
    settings = copilot_settings(**overrides)

    assert copilot_available(settings) is available
    assert (not copilot_problems(settings)) is (available or not settings.ai_enabled)


def test_stale_prices_make_the_copilot_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = copilot_settings()
    assert copilot_available(settings)

    monkeypatch.setattr(copilot_service, "_today", lambda: date(2027, 6, 1))

    assert not copilot_available(settings)
    assert any("pricing" in problem for problem in copilot_problems(settings))


def test_disabled_ai_has_no_problems_to_report() -> None:
    assert copilot_problems(copilot_settings(ai_enabled=False, ai_access_token=None)) == ()


# --- the route's lazy service ------------------------------------------------------------------


def test_the_route_builds_the_service_once_from_the_apps_own_settings(
    session_factory: sessionmaker[Session], engine: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(copilot_settings())
    built: list[Any] = []

    class FakeService:
        def __init__(self, settings: Settings, factory: Any) -> None:
            built.append((settings, factory))

    monkeypatch.setattr(copilot_route, "CopilotService", FakeService)
    monkeypatch.setattr(copilot_route, "get_engine", lambda: engine)
    request = SimpleNamespace(app=app)

    first = copilot_route.get_copilot_service(request)  # type: ignore[arg-type]
    second = copilot_route.get_copilot_service(request)  # type: ignore[arg-type]

    assert first is second and len(built) == 1
    assert built[0][0] is app.state.settings  # the app's own Settings, not a fresh copy


def test_the_ask_route_runs_the_access_check_before_the_service_dependency() -> None:
    (route,) = [
        item
        for item in copilot_route.router.routes
        if getattr(item, "path", "") == "/ai/copilot/ask"
    ]

    dependencies = [dependency.call for dependency in route.dependant.dependencies]  # type: ignore[attr-defined]

    assert dependencies[0] is copilot_route.require_copilot_access  # first, before anything else
    assert copilot_route.get_copilot_service in dependencies[1:]


def test_a_refused_request_never_creates_the_service(
    make_rig: RigFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig()
    rig.app.dependency_overrides.clear()  # use the REAL lazy dependency this time
    created: list[Any] = []
    monkeypatch.setattr(copilot_route, "CopilotService", lambda *a, **k: created.append(a))

    for headers in ({}, {"Origin": "http://evil.test"}, {"Origin": "http://allowed.test"}):
        assert rig.post(headers=headers).status_code in (401, 403)

    assert created == [] and not hasattr(rig.app.state, "copilot_service")

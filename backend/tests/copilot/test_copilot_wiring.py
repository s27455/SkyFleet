"""The production wiring: no dependency override, the real service and the real gateway builder.

Every other Copilot test injects a fake-transport gateway. This one lets the route build its service
the way production does (`get_copilot_service` -> `CopilotService` -> `build_gateway`) and only
replaces the SDK-bound transport class by a recorder, so no client and no network is involved.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes import copilot as copilot_route
from app.main import create_app
from app.simulation.heartbeat import record_heartbeat

from .helpers import ASK, FAKE_KEY, QUESTION, TOKEN, FakeTransport, copilot_settings, good_headers


def test_the_real_dependency_builds_the_gateway_from_the_apps_settings_and_serves_one_question(
    engine: Engine,
    seeded: Session,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: list[Any] = []

    class TransportStandIn(FakeTransport):
        def __init__(
            self, api_key: SecretStr, *, timeout_seconds: float, client: object | None = None
        ) -> None:
            super().__init__()
            self.api_key = api_key
            self.timeout_seconds = timeout_seconds
            built.append(self)

    monkeypatch.setattr("app.ai.anthropic_transport.AnthropicTransport", TransportStandIn)
    monkeypatch.setattr("app.ai.readiness.pricing_age_problem", lambda *_: None)  # not the calendar
    monkeypatch.setattr(copilot_route, "get_engine", lambda: engine)
    settings = copilot_settings()
    app = create_app(settings)  # NO dependency override: the production path
    with session_factory() as session:
        record_heartbeat(session, datetime.now(UTC))
    client = TestClient(app)

    first = client.post(ASK, json={"question": QUESTION}, headers=good_headers())
    second = client.post(ASK, json={"question": QUESTION}, headers=good_headers())

    assert first.status_code == 200 and first.json()["answer"] == "An answer."
    (transport,) = built  # the transport was built once, from the app's own settings
    assert transport.api_key.get_secret_value() == FAKE_KEY
    assert transport.timeout_seconds == settings.ai_request_timeout_seconds
    assert app.state.copilot_service.settings is settings
    assert len(transport.requests) == 1  # one provider request for two POSTs
    assert second.status_code == 429 and second.json()["detail"]["code"] == "RATE_LIMITED"
    for response in (first, second):
        assert FAKE_KEY not in response.text and TOKEN not in response.text


def test_the_production_path_refuses_a_missing_token_without_building_anything(
    engine: Engine, seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[Any] = []
    monkeypatch.setattr(
        "app.ai.anthropic_transport.AnthropicTransport", lambda *a, **k: built.append(a)
    )
    monkeypatch.setattr(copilot_route, "get_engine", lambda: engine)
    app = create_app(copilot_settings())
    client = TestClient(app)

    response = client.post(
        ASK, json={"question": QUESTION}, headers={"Origin": good_headers()["Origin"]}
    )

    assert response.status_code == 401
    assert built == [] and not hasattr(app.state, "copilot_service")  # no service, no transport

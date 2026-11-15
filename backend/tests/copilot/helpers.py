"""A real FastAPI app wired to a fake-transport gateway. Nothing here can reach the network."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.budget import SqlBudgetStore
from app.ai.errors import UpstreamError, UpstreamKind
from app.ai.gateway import AiGateway
from app.ai.models import AiBudgetState, AiRequestLog
from app.ai.types import TransportRequest, TransportResult, TransportUsage
from app.api.routes.copilot import get_copilot_service
from app.config import Settings
from app.copilot.service import CopilotService
from app.main import create_app
from app.simulation.heartbeat import record_heartbeat

FAKE_KEY = "sk-ant-api03-THIS-IS-A-FAKE-TEST-KEY"
TOKEN = "test-operator-token-" + "x" * 30  # FAKE, 50 characters
ORIGIN = "http://allowed.test"
ASK = "/api/ai/copilot/ask"
STATUS = "/api/ai/copilot/status"
GATEWAY_START = datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)  # five days after prices were verified
QUESTION = "How many drones are charging right now?"


class Clock:
    def __init__(self, now: datetime = GATEWAY_START) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class FakeTransport:
    """Records every request; returns an answer or raises the given error."""

    def __init__(
        self,
        error: Exception | None = None,
        *,
        stop_reason: str = "end_turn",
        text: str = "An answer.",
    ) -> None:
        self.error = error
        self.stop_reason = stop_reason
        self.text = text
        self.requests: list[TransportRequest] = []

    def send(self, request: TransportRequest) -> TransportResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return TransportResult(
            text=self.text,
            usage=TransportUsage(input_tokens=1_000, output_tokens=100),
            stop_reason=self.stop_reason,
            provider_request_id="req_fake_001",
        )


def upstream(kind: str, status: int | None = None) -> UpstreamError:
    return UpstreamError(UpstreamKind(kind), status_code=status)


def copilot_settings(**overrides: Any) -> Settings:
    """AI enabled with FAKE secrets, never reading `.env` or the real environment."""
    values: dict[str, Any] = {
        "ai_enabled": True,
        "anthropic_api_key": SecretStr(FAKE_KEY),
        "ai_access_token": SecretStr(TOKEN),
        "cors_origins": [ORIGIN],
        "hub_dock_proximity_m": 50,
        "sim_heartbeat_stale_seconds": 10,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def good_headers(**extra: str) -> dict[str, str]:
    return {"Origin": ORIGIN, "Authorization": f"Bearer {TOKEN}", **extra}


class Rig:
    """The app, its fake provider, and counters that prove what was (not) touched."""

    def __init__(
        self,
        engine: Engine,
        factory: sessionmaker[Session],
        *,
        transport: FakeTransport | None = None,
        heartbeat: bool = True,
        **settings_overrides: Any,
    ) -> None:
        self.engine = engine
        self.factory = factory
        self.transport = transport or FakeTransport()
        self.clock = Clock()
        self.settings = copilot_settings(**settings_overrides)
        self.app = create_app(self.settings)
        self.store = SqlBudgetStore(factory)
        self.service_requests = 0
        if heartbeat:
            with factory() as session:
                record_heartbeat(session, datetime.now(UTC))

        def gateway_factory(
            settings: Settings, session_factory: sessionmaker[Session]
        ) -> AiGateway:
            return AiGateway(
                settings, self.transport, SqlBudgetStore(session_factory), clock=self.clock
            )

        self.service = CopilotService(self.settings, factory, gateway_factory=gateway_factory)

        def service_dependency() -> CopilotService:
            self.service_requests += 1
            return self.service

        self.app.dependency_overrides[get_copilot_service] = service_dependency
        self.client = TestClient(self.app)
        self.statements = 0

        def count(*_: object) -> None:
            self.statements += 1

        event.listen(engine, "before_cursor_execute", count)
        self._listener = count

    def post(
        self,
        question: str = QUESTION,
        *,
        headers: dict[str, str] | None = None,
        json: Any = "default",
    ) -> Any:
        body = {"question": question} if json == "default" else json
        return self.client.post(
            ASK, json=body, headers=good_headers() if headers is None else headers
        )

    def ledger(self) -> list[AiRequestLog]:
        with self.factory() as session:
            return list(session.scalars(select(AiRequestLog)))

    def budget_rows(self) -> int:
        with self.factory() as session:
            return int(session.scalar(select(func.count()).select_from(AiBudgetState)) or 0)

    def close(self) -> None:
        event.remove(self.engine, "before_cursor_execute", self._listener)


RigFactory = Callable[..., Rig]

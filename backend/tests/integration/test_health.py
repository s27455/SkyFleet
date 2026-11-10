from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_client() -> TestClient:
    return TestClient(create_app(Settings(cors_origins=["http://allowed.test"])))


def test_health_returns_ok() -> None:
    response = make_client().get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_allows_configured_origin() -> None:
    response = make_client().get("/api/health", headers={"Origin": "http://allowed.test"})

    assert response.headers["access-control-allow-origin"] == "http://allowed.test"


def test_cors_rejects_unknown_origin() -> None:
    response = make_client().get("/api/health", headers={"Origin": "http://evil.test"})

    assert "access-control-allow-origin" not in response.headers

"""`GET /api/orders?limit=N`: the most recent N orders of the history, applied in SQL.

The Management "All orders" view polls this, so it must not download the whole history. The active
list (`active=true`) is already bounded and stays as it was.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.hubs.seed import seed_hubs
from app.orders import repository
from app.orders.models import DeliveryOrder

START = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)


@pytest.fixture
def twelve_orders(session: Session, make_order: Callable[..., DeliveryOrder]) -> list[str]:
    seed_hubs(session)
    ids = [f"ORD-{number:03d}" for number in range(100, 112)]
    for number, order_id in enumerate(ids):
        session.add(make_order(id=order_id, created_at=START + timedelta(minutes=number)))
    session.commit()
    return ids


def listed(client: TestClient, **params: str | int | list[str]) -> list[str]:
    response = client.get("/api/orders", params=params)
    assert response.status_code == 200
    return [order["id"] for order in response.json()]


def test_without_a_limit_the_whole_history_is_returned_oldest_first(
    client: TestClient, twelve_orders: list[str]
) -> None:
    assert listed(client) == twelve_orders


def test_a_limit_keeps_the_most_recent_orders_still_oldest_first(
    client: TestClient, twelve_orders: list[str]
) -> None:
    assert listed(client, limit=5) == twelve_orders[-5:]


def test_a_limit_larger_than_the_history_returns_everything(
    client: TestClient, twelve_orders: list[str]
) -> None:
    assert listed(client, limit=500) == twelve_orders


def test_the_limit_is_applied_in_sql_not_in_python(
    session: Session, twelve_orders: list[str]
) -> None:
    rows = repository.list_orders(session, limit=3)

    assert [order.id for order in rows] == twelve_orders[-3:]


@pytest.mark.parametrize("limit", [0, -5, repository.MAX_LIST_LIMIT + 1])
def test_a_limit_outside_the_allowed_range_is_rejected(client: TestClient, limit: int) -> None:
    assert client.get("/api/orders", params={"limit": limit}).status_code == 422


def test_limit_cannot_be_combined_with_active(client: TestClient, twelve_orders: list[str]) -> None:
    response = client.get("/api/orders", params={"active": "true", "limit": 5})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "LIMIT_NOT_ALLOWED_WITH_ACTIVE"


def test_the_active_list_is_unchanged_by_the_new_parameter(
    client: TestClient, twelve_orders: list[str]
) -> None:
    assert listed(client, active="true") == twelve_orders

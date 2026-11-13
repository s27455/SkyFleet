"""Feature 017A: active-view visibility of delivered orders (rule, repository and API)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.hubs.seed import seed_hubs
from app.orders import repository
from app.orders.models import DeliveryOrder, OrderStatus
from app.orders.seed import seed_orders
from app.orders.visibility import is_order_active
from app.simulation import clock

NOW = datetime(2026, 11, 13, 12, 0, 0, tzinfo=UTC)
WINDOW = 120.0
DELIVERED = OrderStatus.DELIVERED.value


@pytest.mark.parametrize(
    ("age_s", "visible"),
    [(0, True), (119, True), (119.999, True), (120, False), (121, False), (3600, False)],
)
def test_the_rule_hides_a_delivered_order_from_exactly_the_window(
    age_s: float, visible: bool
) -> None:
    delivered_at = NOW - timedelta(seconds=age_s)

    assert is_order_active(DELIVERED, delivered_at, NOW, WINDOW) is visible


def test_a_delivered_order_without_a_delivery_time_is_hidden() -> None:
    assert is_order_active(DELIVERED, None, NOW, WINDOW) is False


@pytest.mark.parametrize(
    "status",
    [
        s.value
        for s in OrderStatus
        if s not in (OrderStatus.DELIVERED, OrderStatus.CANCELLED, OrderStatus.DELIVERY_FAILED)
    ],
)
def test_every_other_status_stays_visible_whatever_its_timestamp(status: str) -> None:
    assert is_order_active(status, None, NOW, WINDOW) is True
    assert is_order_active(status, NOW - timedelta(days=9), NOW, WINDOW) is True


def test_a_failed_delivery_is_visible_for_the_window_after_the_failure() -> None:
    failed = OrderStatus.DELIVERY_FAILED.value
    inside = NOW - timedelta(seconds=WINDOW - 1)
    edge = NOW - timedelta(seconds=WINDOW)

    assert is_order_active(failed, None, NOW, WINDOW, delivery_failed_at=inside) is True
    assert is_order_active(failed, None, NOW, WINDOW, delivery_failed_at=edge) is False
    assert is_order_active(failed, None, NOW, WINDOW, delivery_failed_at=None) is False
    # `delivered_at` is never used for it: a failed delivery is not a delivery.
    assert is_order_active(failed, inside, NOW, WINDOW) is False


def test_a_cancelled_order_is_visible_for_the_window_after_cancellation() -> None:
    cancelled = OrderStatus.CANCELLED.value
    inside = NOW - timedelta(seconds=WINDOW - 1)
    edge = NOW - timedelta(seconds=WINDOW)

    assert is_order_active(cancelled, None, NOW, WINDOW, cancelled_at=inside) is True
    assert is_order_active(cancelled, None, NOW, WINDOW, cancelled_at=edge) is False
    assert is_order_active(cancelled, None, NOW, WINDOW, cancelled_at=None) is False


def test_an_interrupted_undelivered_order_is_visible_for_the_window_after_the_landing() -> None:
    status = OrderStatus.OUT_FOR_DELIVERY.value
    inside = NOW - timedelta(seconds=WINDOW - 1)
    edge = NOW - timedelta(seconds=WINDOW)

    assert is_order_active(status, None, NOW, WINDOW, interrupted_at=inside) is True
    assert is_order_active(status, None, NOW, WINDOW, interrupted_at=edge) is False
    assert is_order_active(status, None, NOW, WINDOW, interrupted_at=None) is True  # still flying


def _prepare(session: Session) -> dict[str, DeliveryOrder]:
    """Seeded orders; four are made DELIVERED at 119 s, 120 s, 121 s and unknown time ago."""
    seed_hubs(session)
    seed_orders(session)
    orders = {o.id: o for o in session.query(DeliveryOrder).all()}
    for order_id, age in (("ORD-001", 119), ("ORD-002", 120), ("ORD-003", 121), ("ORD-004", None)):
        order = orders[order_id]
        order.status = DELIVERED
        order.delivered_at = None if age is None else NOW - timedelta(seconds=age)
    session.commit()
    return orders


def test_the_repository_applies_the_same_boundaries_as_the_rule(session: Session) -> None:
    orders = _prepare(session)

    active = repository.list_active_orders(session, NOW, WINDOW)

    ids = [o.id for o in active]
    assert "ORD-001" in ids  # 119 s
    assert not {"ORD-002", "ORD-003", "ORD-004"} & set(ids)  # 120 s, 121 s, legacy null
    assert ids == sorted(ids)  # same stable order as the full list
    for order in orders.values():  # SQL and the pure rule never disagree
        expected = is_order_active(order.status, order.delivered_at, NOW, WINDOW)
        assert (order.id in ids) is expected


def test_the_active_list_keeps_pending_orders_and_the_full_list_keeps_history(
    session: Session,
) -> None:
    _prepare(session)

    active = repository.list_active_orders(session, NOW, WINDOW)
    everything = repository.list_orders(session)

    assert len(everything) == 11  # nothing is removed
    assert len(active) == 11 - 3
    assert all(o.status == "READY_FOR_PICKUP" for o in active if o.id != "ORD-001")


def test_the_api_filters_only_when_asked(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare(session)
    monkeypatch.setattr(clock, "utcnow", lambda: NOW)

    full = client.get("/api/orders").json()
    active = client.get("/api/orders", params={"active": "true"}).json()
    explicit_full = client.get("/api/orders", params={"active": "false"}).json()

    assert len(full) == 11 and explicit_full == full
    assert {o["id"] for o in full} - {o["id"] for o in active} == {"ORD-002", "ORD-003", "ORD-004"}
    delivered = next(o for o in active if o["id"] == "ORD-001")
    assert delivered["status"] == "DELIVERED"
    assert delivered["delivered_at"].startswith("2026-11-13T11:58:01")
    assert next(o for o in full if o["id"] == "ORD-004")["delivered_at"] is None

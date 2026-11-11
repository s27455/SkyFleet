"""Database-level validation of orders: ranges, status vocabulary, weight limit and foreign keys."""

from collections.abc import Callable

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.drones.seed import build_sf1_model
from app.hubs.models import Hub
from app.orders.models import MAX_PACKAGE_WEIGHT_KG, DeliveryOrder, OrderStatus

OrderFactory = Callable[..., DeliveryOrder]


def test_valid_order_is_stored_with_timestamps(
    hubs_and_model: Session, make_order: OrderFactory
) -> None:
    hubs_and_model.add(make_order())
    hubs_and_model.commit()

    stored = hubs_and_model.get(DeliveryOrder, "ORD-900")
    assert stored is not None
    assert stored.status == OrderStatus.READY_FOR_PICKUP
    assert stored.created_at is not None
    assert stored.updated_at is not None


def test_weight_limit_matches_the_sf1_payload() -> None:
    assert MAX_PACKAGE_WEIGHT_KG == build_sf1_model().max_payload_kg == 3.0


def test_weight_at_the_limit_is_accepted(hubs_and_model: Session, make_order: OrderFactory) -> None:
    hubs_and_model.add(make_order(package_weight_kg=3.0))
    hubs_and_model.commit()


@pytest.mark.parametrize(
    "overrides",
    [
        {"package_weight_kg": 0},
        {"package_weight_kg": -0.5},
        {"package_weight_kg": 3.01},
        {"status": "PENDING"},
        {"status": "ready_for_pickup"},
        {"destination_longitude": 181.0},
        {"destination_latitude": -91.0},
        {"destination_address": ""},
        {"destination_address": "   "},
        {"origin_hub_id": "hub-does-not-exist"},
    ],
)
def test_invalid_order_is_rejected(
    hubs_and_model: Session, make_order: OrderFactory, overrides: dict[str, object]
) -> None:
    hubs_and_model.add(make_order(**overrides))

    with pytest.raises(IntegrityError):
        hubs_and_model.commit()


def test_duplicate_order_id_is_rejected(hubs_and_model: Session, make_order: OrderFactory) -> None:
    hubs_and_model.add(make_order())
    hubs_and_model.commit()
    hubs_and_model.add(make_order())

    with pytest.raises(IntegrityError):
        hubs_and_model.commit()


def test_hub_with_orders_cannot_be_deleted(
    hubs_and_model: Session, make_order: OrderFactory
) -> None:
    hubs_and_model.add(make_order())
    hubs_and_model.commit()
    hubs_and_model.delete(hubs_and_model.get(Hub, "hub-forum-gdansk"))

    with pytest.raises(IntegrityError):
        hubs_and_model.commit()


def test_updating_an_order_refreshes_updated_at_but_not_created_at(
    hubs_and_model: Session, make_order: OrderFactory
) -> None:
    hubs_and_model.add(make_order())
    hubs_and_model.commit()
    order = hubs_and_model.get(DeliveryOrder, "ORD-900")
    assert order is not None
    created, updated = order.created_at, order.updated_at

    order.status = OrderStatus.AWAITING_HANDOVER.value
    hubs_and_model.commit()
    hubs_and_model.refresh(order)

    assert order.created_at == created
    assert order.updated_at > updated

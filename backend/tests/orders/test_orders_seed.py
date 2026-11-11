from collections import Counter

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.hubs.models import Hub
from app.hubs.seed import seed_hubs
from app.orders.models import MAX_PACKAGE_WEIGHT_KG, DeliveryOrder, OrderStatus
from app.orders.seed import SEED_ORDERS, SeedError, seed_orders


def count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(DeliveryOrder)) or 0


def test_seed_inserts_ten_orders_on_first_run(session: Session) -> None:
    seed_hubs(session)

    assert seed_orders(session) == 10

    assert count(session) == 10
    assert [o.id for o in session.scalars(select(DeliveryOrder).order_by(DeliveryOrder.id))] == [
        f"ORD-{n:03d}" for n in range(1, 11)
    ]


def test_second_run_inserts_nothing_and_changes_nothing(session: Session) -> None:
    seed_hubs(session)
    seed_orders(session)
    before = {o.id: o.created_at for o in session.scalars(select(DeliveryOrder))}

    assert seed_orders(session) == 0

    assert count(session) == 10
    assert {o.id: o.created_at for o in session.scalars(select(DeliveryOrder))} == before


def test_seed_never_overwrites_an_existing_order(session: Session) -> None:
    seed_hubs(session)
    seed_orders(session)
    order = session.get(DeliveryOrder, "ORD-001")
    assert order is not None
    order.destination_address = "Changed by an operator"
    order.package_weight_kg = 2.9
    session.commit()

    assert seed_orders(session) == 0

    session.expire_all()
    order = session.get(DeliveryOrder, "ORD-001")
    assert order is not None
    assert order.destination_address == "Changed by an operator"
    assert order.package_weight_kg == 2.9


def test_seed_only_adds_the_missing_orders(session: Session) -> None:
    seed_hubs(session)
    seed_orders(session)
    session.delete(session.get(DeliveryOrder, "ORD-005"))
    session.commit()

    assert seed_orders(session) == 1
    assert count(session) == 10


def test_seed_spreads_orders_over_all_four_hubs(session: Session) -> None:
    seed_hubs(session)
    seed_orders(session)

    per_hub = Counter(session.scalars(select(DeliveryOrder.origin_hub_id)))
    assert set(per_hub) == set(session.scalars(select(Hub.id)))
    assert sum(per_hub.values()) == 10


def test_seeded_orders_are_ready_for_pickup_with_valid_weights_and_no_assignment(
    session: Session,
) -> None:
    seed_hubs(session)
    seed_orders(session)

    for order in session.scalars(select(DeliveryOrder)):
        assert order.status == OrderStatus.READY_FOR_PICKUP
        assert 0 < order.package_weight_kg <= MAX_PACKAGE_WEIGHT_KG
        assert order.destination_address.strip()
    assert not hasattr(DeliveryOrder, "assigned_drone_id")


def test_seed_data_has_unique_ids_and_valid_coordinates() -> None:
    assert len({seed.id for seed in SEED_ORDERS}) == len(SEED_ORDERS)
    for seed in SEED_ORDERS:
        assert -180 <= seed.longitude <= 180
        assert -90 <= seed.latitude <= 90


def test_seed_fails_clearly_without_hubs_and_writes_nothing(session: Session) -> None:
    with pytest.raises(SeedError, match="app.hubs.seed"):
        seed_orders(session)

    assert count(session) == 0

"""Operational events on PostgreSQL in a temporary database (Feature 018A).

Opt-in (`uv run pytest -m postgres`); it uses the `temp_engine` fixture, which applies the real
migrations to a throwaway database, so the development database is never touched.
"""

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from app.events.models import EventOrigin, EventType, OperationalEvent
from app.events.service import append_event
from app.orders import service
from app.orders.models import DeliveryOrder
from app.orders.schemas import OrderCreateRequest

pytestmark = pytest.mark.postgres

REQUEST = OrderCreateRequest(
    origin_hub_id="hub-forum-gdansk",
    destination_address="ul. Testowa 1, Gdańsk",
    destination_longitude=18.65,
    destination_latitude=54.35,
    package_weight_kg=1.5,
)


def test_duplicate_key_does_not_abort_the_postgresql_transaction(temp_engine: Engine) -> None:
    factory = sessionmaker(bind=temp_engine, expire_on_commit=False)
    with factory() as session:
        order = service.create_order(session, REQUEST)
        key = f"pg-dedupe:{order.id}"
        first = append_event(
            session,
            event_type=EventType.ORDER_CREATED,
            origin=EventOrigin.SYSTEM,
            order_id=order.id,
            dedupe_key=key,
        )
        second = append_event(
            session,
            event_type=EventType.ORDER_CREATED,
            origin=EventOrigin.SYSTEM,
            order_id=order.id,
            dedupe_key=key,
        )
        # The transaction must still be usable after the ignored duplicate.
        count = session.scalar(
            select(func.count())
            .select_from(OperationalEvent)
            .where(OperationalEvent.dedupe_key == key)
        )
        session.commit()

    assert (first, second, count) == (True, False, 1)


def test_deleting_an_order_removes_its_events_in_one_transaction(temp_engine: Engine) -> None:
    factory = sessionmaker(bind=temp_engine, expire_on_commit=False)
    with factory() as session:
        order = service.create_order(session, REQUEST)
        order_id = order.id
        assert (
            session.scalar(
                select(func.count())
                .select_from(OperationalEvent)
                .where(OperationalEvent.order_id == order_id)
            )
            == 1
        )

        service.delete_order(session, order_id)

        assert session.get(DeliveryOrder, order_id) is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(OperationalEvent)
                .where(OperationalEvent.order_id == order_id)
            )
            == 0
        )

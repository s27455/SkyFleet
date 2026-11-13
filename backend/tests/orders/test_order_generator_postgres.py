"""Concurrent order generation on PostgreSQL in a temporary database (feature 015A).

Opt-in (`uv run pytest -m postgres`) and skipped when the Docker PostgreSQL is unreachable; it
uses the `temp_engine` fixture, so the development database is never touched.
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from app.orders.generator import generate_one_order
from app.orders.models import DeliveryOrder, OrderStatus

pytestmark = pytest.mark.postgres


def test_parallel_generation_creates_distinct_orders_and_keeps_existing_ones(
    temp_engine: Engine,
) -> None:
    factory = sessionmaker(bind=temp_engine, expire_on_commit=False)
    with factory() as session:
        before = set(session.scalars(select(DeliveryOrder.id)))

    def generate() -> str:
        with factory() as session:
            return generate_one_order(session).id

    with ThreadPoolExecutor(max_workers=12) as pool:
        created = [
            future.result(timeout=60) for future in [pool.submit(generate) for _ in range(24)]
        ]

    assert len(set(created)) == 24
    with factory() as session:
        after = set(session.scalars(select(DeliveryOrder.id)))
        assert after == before | set(created)
        assert (
            session.scalar(
                select(func.count())
                .select_from(DeliveryOrder)
                .where(
                    DeliveryOrder.id.in_(created),
                    DeliveryOrder.status != OrderStatus.READY_FOR_PICKUP.value,
                )
            )
            == 0
        )

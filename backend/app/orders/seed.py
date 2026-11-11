"""Idempotent, insert-only seed of illustrative delivery orders.

Run with `uv run python -m app.orders.seed` after `alembic upgrade head` and the Hub seed
(`uv run python -m app.hubs.seed`). Existing orders are never modified, so re-running the seed
cannot overwrite operational state.

All addresses, coordinates and weights are ILLUSTRATIVE SIMULATION DATA. They are not verified
customer addresses, not proof of a deliverable location and not a legal flight corridor. Distance
from the origin Hub is deliberately not validated: mission feasibility belongs to a later feature.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_engine
from app.hubs.models import Hub
from app.orders.models import DeliveryOrder, OrderStatus


class SeedError(RuntimeError):
    """Raised when the orders cannot be seeded safely."""


@dataclass(frozen=True)
class OrderSeed:
    id: str
    origin_hub_id: str
    destination_address: str
    longitude: float
    latitude: float
    package_weight_kg: float


# Ten orders spread over the four Hubs (3 + 3 + 2 + 2). Append-only: add new orders with new ids.
SEED_ORDERS: tuple[OrderSeed, ...] = (
    OrderSeed(
        "ORD-001", "hub-galeria-baltycka", "ul. Grunwaldzka 82, Gdańsk", 18.5972, 54.3768, 0.8
    ),
    OrderSeed(
        "ORD-002", "hub-galeria-baltycka", "ul. Do Studzienki 25, Gdańsk", 18.5887, 54.3881, 1.5
    ),
    OrderSeed(
        "ORD-003", "hub-galeria-baltycka", "ul. Słowackiego 200, Gdańsk", 18.6120, 54.3935, 2.2
    ),
    OrderSeed("ORD-004", "hub-forum-gdansk", "ul. Długa 45, Gdańsk", 18.6531, 54.3487, 0.3),
    OrderSeed("ORD-005", "hub-forum-gdansk", "ul. Chmielna 10, Gdańsk", 18.6410, 54.3512, 1.1),
    OrderSeed(
        "ORD-006", "hub-forum-gdansk", "ul. Podwale Staromiejskie 60, Gdańsk", 18.6459, 54.3558, 3.0
    ),
    OrderSeed(
        "ORD-007", "hub-centrum-riviera", "ul. Świętojańska 30, Gdynia", 18.5440, 54.5189, 0.6
    ),
    OrderSeed("ORD-008", "hub-centrum-riviera", "ul. Morska 59, Gdynia", 18.5120, 54.5050, 2.4),
    OrderSeed(
        "ORD-009", "hub-centrum-handlowe-osowa", "ul. Spacerowa 12, Gdańsk", 18.4952, 54.4311, 1.9
    ),
    OrderSeed(
        "ORD-010", "hub-centrum-handlowe-osowa", "ul. Kielnieńska 5, Gdańsk", 18.4720, 54.4180, 0.5
    ),
)


def seed_orders(session: Session) -> int:
    """Insert any missing orders (matched by id). Returns the number inserted.

    Validates every origin Hub before writing, so a failure leaves the database unchanged.
    """
    hub_ids = set(session.scalars(select(Hub.id)))
    missing = sorted({seed.origin_hub_id for seed in SEED_ORDERS} - hub_ids)
    if missing:
        raise SeedError(
            f"Hubs not found: {', '.join(missing)}. Run `python -m app.hubs.seed` first."
        )

    existing_ids = set(session.scalars(select(DeliveryOrder.id)))
    # One timestamp per run, so a fresh seed lists in id order. Orders added by a later run get a
    # later created_at and list after the existing ones.
    now = datetime.now(UTC)
    new_orders = [
        DeliveryOrder(
            id=seed.id,
            origin_hub_id=seed.origin_hub_id,
            destination_address=seed.destination_address,
            destination_longitude=seed.longitude,
            destination_latitude=seed.latitude,
            package_weight_kg=seed.package_weight_kg,
            status=OrderStatus.READY_FOR_PICKUP.value,
            created_at=now,
            updated_at=now,
        )
        for seed in SEED_ORDERS
        if seed.id not in existing_ids
    ]
    session.add_all(new_orders)
    session.commit()
    return len(new_orders)


def main() -> None:
    with sessionmaker(bind=get_engine())() as session:
        try:
            inserted = seed_orders(session)
        except SeedError as error:
            raise SystemExit(f"Order seed failed: {error}") from error
    print(
        f"Order seed complete: {inserted} inserted, {len(SEED_ORDERS) - inserted} already present."
    )


if __name__ == "__main__":
    main()

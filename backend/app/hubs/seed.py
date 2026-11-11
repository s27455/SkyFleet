"""Idempotent seed of the four initial demo Hubs.

Run with `uv run python -m app.hubs.seed` after `uv run alembic upgrade head`.
The malls are illustrative, not real SkyFleet facilities. Coordinates are WGS84.
"""

from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_engine
from app.hubs.models import DEFAULT_DRONE_CAPACITY, Hub


@dataclass(frozen=True)
class HubSeed:
    id: str
    name: str
    address: str
    longitude: float
    latitude: float
    drone_capacity: int = DEFAULT_DRONE_CAPACITY


SEED_HUBS: tuple[HubSeed, ...] = (
    HubSeed(
        id="hub-galeria-baltycka",
        name="Galeria Bałtycka",
        address="al. Grunwaldzka 141, Gdańsk",
        longitude=18.6006944,
        latitude=54.3826244,
    ),
    HubSeed(
        id="hub-forum-gdansk",
        name="Forum Gdańsk",
        address="Targ Sienny 7, Gdańsk",
        longitude=18.643527,
        latitude=54.349346,
    ),
    HubSeed(
        id="hub-centrum-riviera",
        name="Centrum Riviera",
        address="Kazimierza Górskiego 2, Gdynia",
        longitude=18.5317863,
        latitude=54.5046621,
    ),
    HubSeed(
        id="hub-centrum-handlowe-osowa",
        name="Centrum Handlowe Osowa",
        address="Spacerowa 48, 80-299 Gdańsk",
        longitude=18.49097,
        latitude=54.42569,
    ),
)


def seed_hubs(session: Session) -> int:
    """Insert Hubs that are missing (matched by id); never modify existing rows.

    Returns the number inserted. Existing rows are left untouched so that re-running the seed
    can never revert later changes to Hub data.
    """
    inserted = 0
    for seed in SEED_HUBS:
        if session.get(Hub, seed.id) is None:
            session.add(Hub(**asdict(seed)))
            inserted += 1
    session.commit()
    return inserted


def main() -> None:
    with sessionmaker(bind=get_engine())() as session:
        inserted = seed_hubs(session)
    print(f"Hub seed complete: {inserted} inserted, {len(SEED_HUBS) - inserted} already present.")


if __name__ == "__main__":
    main()

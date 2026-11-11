import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.hubs.models import DEFAULT_DRONE_CAPACITY, Hub
from app.hubs.seed import SEED_HUBS, seed_hubs


def hub_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Hub)) or 0


def test_seed_is_idempotent(session: Session) -> None:
    assert seed_hubs(session) == 4
    assert seed_hubs(session) == 0

    assert hub_count(session) == 4


def test_seed_does_not_overwrite_existing_hub(session: Session) -> None:
    seed_hubs(session)
    hub = session.get(Hub, "hub-forum-gdansk")
    assert hub is not None
    hub.drone_capacity = 20
    session.commit()

    assert seed_hubs(session) == 0

    session.expire_all()
    kept = session.get(Hub, "hub-forum-gdansk")
    assert kept is not None
    assert kept.drone_capacity == 20
    assert hub_count(session) == 4


def test_seed_coordinates_are_lng_lat_in_tricity() -> None:
    for hub in SEED_HUBS:
        assert 18.0 < hub.longitude < 19.0  # longitude ~18.5 E
        assert 54.0 < hub.latitude < 55.0  # latitude ~54.4 N


def test_drone_capacity_defaults_to_50(session: Session) -> None:
    session.add(Hub(id="h", name="n", address="a", longitude=18.0, latitude=54.0))
    session.commit()

    hub = session.get(Hub, "h")
    assert hub is not None
    assert hub.drone_capacity == DEFAULT_DRONE_CAPACITY == 50


@pytest.mark.parametrize(
    ("longitude", "latitude", "capacity"),
    [
        (181.0, 54.0, 50),
        (18.0, 91.0, 50),
        (18.0, 54.0, 0),
        (18.0, 54.0, -5),
    ],
)
def test_invalid_hub_fields_are_rejected(
    session: Session, longitude: float, latitude: float, capacity: int
) -> None:
    session.add(
        Hub(
            id="bad",
            name="Bad",
            address="a",
            longitude=longitude,
            latitude=latitude,
            drone_capacity=capacity,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_duplicate_hub_name_is_rejected(session: Session) -> None:
    session.add(Hub(id="a", name="Same", address="x", longitude=18.0, latitude=54.0))
    session.add(Hub(id="b", name="Same", address="y", longitude=18.1, latitude=54.1))

    with pytest.raises(IntegrityError):
        session.commit()

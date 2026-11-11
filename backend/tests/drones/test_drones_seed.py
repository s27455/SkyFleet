from collections import Counter

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.drones.models import Drone, DroneModel, DroneStatus
from app.drones.seed import SeedError, seed_drones
from app.hubs.models import Hub
from app.hubs.seed import seed_hubs


def count(session: Session, table: type[Drone] | type[DroneModel]) -> int:
    return session.scalar(select(func.count()).select_from(table)) or 0


def test_seed_inserts_one_model_and_twelve_drones(session: Session) -> None:
    seed_hubs(session)

    assert seed_drones(session) == 12

    assert count(session, DroneModel) == 1
    assert count(session, Drone) == 12
    model = session.get(DroneModel, "SF-1")
    assert model is not None
    assert model.max_payload_kg == 3.0


def test_seed_distributes_three_drones_per_hub_within_capacity(session: Session) -> None:
    seed_hubs(session)
    seed_drones(session)

    per_hub = Counter(session.scalars(select(Drone.hub_id)))
    assert len(per_hub) == 4
    assert set(per_hub.values()) == {3}
    for hub in session.scalars(select(Hub)):
        assert per_hub[hub.id] <= hub.drone_capacity


def test_seeded_drones_start_idle_at_their_hub_with_the_sf1_model(session: Session) -> None:
    seed_hubs(session)
    seed_drones(session)

    hubs = {hub.id: hub for hub in session.scalars(select(Hub))}
    for drone in session.scalars(select(Drone)):
        hub = hubs[drone.hub_id]
        assert drone.model_id == "SF-1"
        assert drone.status == DroneStatus.IDLE
        assert (drone.longitude, drone.latitude) == (hub.longitude, hub.latitude)
        assert drone.battery_pct in (100, 90, 80)


def test_seed_is_idempotent(session: Session) -> None:
    seed_hubs(session)

    assert seed_drones(session) == 12
    assert seed_drones(session) == 0

    assert count(session, Drone) == 12
    assert count(session, DroneModel) == 1


def test_seed_does_not_reset_existing_drone_state(session: Session) -> None:
    seed_hubs(session)
    seed_drones(session)
    drone = session.get(Drone, "DRN-002")
    assert drone is not None
    drone.status = DroneStatus.CHARGING.value
    drone.battery_pct = 35
    drone.longitude = 18.5
    session.commit()

    seed_drones(session)

    session.expire_all()
    kept = session.get(Drone, "DRN-002")
    assert kept is not None
    assert (kept.status, kept.battery_pct, kept.longitude) == ("CHARGING", 35, 18.5)


def test_seed_fills_in_only_missing_drones(session: Session) -> None:
    seed_hubs(session)
    seed_drones(session)
    session.delete(session.get(Drone, "DRN-005"))
    session.commit()

    assert seed_drones(session) == 1

    assert count(session, Drone) == 12


def test_seed_fails_clearly_without_hubs_and_writes_nothing(session: Session) -> None:
    with pytest.raises(SeedError, match="Run `python -m app.hubs.seed` first"):
        seed_drones(session)

    assert count(session, DroneModel) == 0
    assert count(session, Drone) == 0


def test_seed_fails_when_a_hub_capacity_would_be_exceeded(session: Session) -> None:
    seed_hubs(session)
    hub = session.get(Hub, "hub-forum-gdansk")
    assert hub is not None
    hub.drone_capacity = 2
    session.commit()

    with pytest.raises(SeedError, match="hub-forum-gdansk.*capacity of 2"):
        seed_drones(session)

    assert count(session, Drone) == 0
    assert count(session, DroneModel) == 0

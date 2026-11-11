"""Database-level guarantees for missions: constraints, keys and active-mission uniqueness."""

import re
from collections.abc import Callable

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.drones.models import Drone
from app.hubs.models import Hub
from app.missions.models import ACTIVE_MISSION_STATUSES, Mission, MissionStatus, new_mission_id
from app.orders.models import DeliveryOrder

MissionFactory = Callable[..., Mission]


@pytest.fixture
def make_mission() -> MissionFactory:
    counter = iter(range(1, 1000))

    def factory(**overrides: object) -> Mission:
        values: dict[str, object] = {
            "id": f"MIS-{next(counter):08X}",
            "order_id": "ORD-001",
            "drone_id": "DRN-010",
            "origin_hub_id": "hub-galeria-baltycka",
            "return_hub_id": "hub-galeria-baltycka",
            "status": MissionStatus.ASSIGNED.value,
            "origin_to_destination_km": 0.7,
            "destination_to_return_km": 0.7,
            "total_km": 1.4,
            "expected_energy_pct": 7.0,
            "worst_case_energy_pct": 7.5,
        }
        values.update(overrides)
        return Mission(**values)

    return factory


def count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Mission)) or 0


def test_the_mission_id_has_the_agreed_format_and_is_not_repeated() -> None:
    ids = {new_mission_id() for _ in range(200)}

    assert len(ids) == 200
    assert all(re.fullmatch(r"MIS-[0-9A-F]{8}", mission_id) for mission_id in ids)


def test_active_statuses_are_assigned_and_in_flight() -> None:
    assert set(ACTIVE_MISSION_STATUSES) == {MissionStatus.ASSIGNED, MissionStatus.IN_FLIGHT}


def test_a_valid_mission_is_stored_with_timestamps(
    seeded: Session, make_mission: MissionFactory
) -> None:
    seeded.add(make_mission())
    seeded.commit()

    stored = seeded.scalars(select(Mission)).one()
    assert stored.status == MissionStatus.ASSIGNED
    assert stored.created_at is not None
    assert stored.updated_at is not None


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "PENDING"},
        {"status": "assigned"},
        {"origin_to_destination_km": -0.1},
        {"destination_to_return_km": -0.1},
        {"total_km": -0.1},
        {"expected_energy_pct": -1},
        {"worst_case_energy_pct": -1},
        {"order_id": "ORD-999"},
        {"drone_id": "DRN-999"},
        {"origin_hub_id": "hub-nowhere"},
        {"return_hub_id": "hub-nowhere"},
    ],
)
def test_an_invalid_mission_is_rejected(
    seeded: Session, make_mission: MissionFactory, overrides: dict[str, object]
) -> None:
    seeded.add(make_mission(**overrides))

    with pytest.raises(IntegrityError):
        seeded.commit()


@pytest.mark.parametrize("first", [MissionStatus.ASSIGNED, MissionStatus.IN_FLIGHT])
@pytest.mark.parametrize("second", [MissionStatus.ASSIGNED, MissionStatus.IN_FLIGHT])
def test_two_active_missions_cannot_claim_the_same_order(
    seeded: Session, make_mission: MissionFactory, first: MissionStatus, second: MissionStatus
) -> None:
    seeded.add(make_mission(status=first.value))
    seeded.commit()
    seeded.add(make_mission(status=second.value, drone_id="DRN-011"))

    with pytest.raises(IntegrityError):
        seeded.commit()


@pytest.mark.parametrize("first", [MissionStatus.ASSIGNED, MissionStatus.IN_FLIGHT])
@pytest.mark.parametrize("second", [MissionStatus.ASSIGNED, MissionStatus.IN_FLIGHT])
def test_two_active_missions_cannot_claim_the_same_drone(
    seeded: Session, make_mission: MissionFactory, first: MissionStatus, second: MissionStatus
) -> None:
    seeded.add(make_mission(status=first.value))
    seeded.commit()
    seeded.add(make_mission(status=second.value, order_id="ORD-002"))

    with pytest.raises(IntegrityError):
        seeded.commit()


def test_a_cancelled_mission_no_longer_claims_its_order_or_drone(
    seeded: Session, make_mission: MissionFactory
) -> None:
    seeded.add(make_mission(status=MissionStatus.CANCELLED.value))
    seeded.add(make_mission(status=MissionStatus.CANCELLED.value))  # history may repeat
    seeded.add(make_mission())  # and a new active mission is fine
    seeded.commit()

    assert count(seeded) == 3


def test_cancelling_the_active_mission_frees_the_order_and_the_drone(
    seeded: Session, make_mission: MissionFactory
) -> None:
    first = make_mission()
    seeded.add(first)
    seeded.commit()
    first.status = MissionStatus.CANCELLED.value
    seeded.commit()

    seeded.add(make_mission())
    seeded.commit()

    assert count(seeded) == 2


def test_missions_for_different_orders_and_drones_can_all_be_active(
    seeded: Session, make_mission: MissionFactory
) -> None:
    seeded.add(make_mission())
    seeded.add(make_mission(order_id="ORD-002", drone_id="DRN-011"))
    seeded.commit()

    assert count(seeded) == 2


@pytest.mark.parametrize(
    ("model", "key"),
    [(DeliveryOrder, "ORD-001"), (Drone, "DRN-010"), (Hub, "hub-galeria-baltycka")],
)
def test_a_referenced_order_drone_or_hub_cannot_be_deleted(
    seeded: Session, make_mission: MissionFactory, model: type, key: str
) -> None:
    seeded.add(make_mission())
    seeded.commit()
    seeded.delete(seeded.get(model, key))

    with pytest.raises(IntegrityError):
        seeded.commit()

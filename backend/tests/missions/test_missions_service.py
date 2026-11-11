"""Transactional behaviour of confirmation and cancellation."""

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.drones.models import Drone
from app.missions import repository, service
from app.missions.models import Mission, MissionStatus
from app.orders.models import DeliveryOrder

SETTINGS = Settings(mission_payload_energy_factor=0.5, hub_dock_proximity_m=50)
ORDER, DRONE = "ORD-001", "DRN-010"


def mission_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Mission)) or 0


def test_a_failure_while_saving_leaves_neither_a_mission_nor_a_changed_order_or_drone(
    seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_insert(session: Session, mission: Mission) -> None:
        session.add(mission)
        session.flush()  # the row exists inside the transaction...
        raise RuntimeError("boom")  # ...and then something goes wrong

    monkeypatch.setattr(service, "_insert_mission", failing_insert)
    order_before = seeded.get(DeliveryOrder, ORDER)
    drone_before = seeded.get(Drone, DRONE)
    assert order_before is not None and drone_before is not None
    order_state = (order_before.status, order_before.package_weight_kg)
    drone_state = (drone_before.status, drone_before.battery_pct, drone_before.longitude)

    with pytest.raises(RuntimeError, match="boom"):
        service.confirm_mission(seeded, ORDER, DRONE, SETTINGS)

    seeded.expire_all()
    assert mission_count(seeded) == 0
    order, drone = seeded.get(DeliveryOrder, ORDER), seeded.get(Drone, DRONE)
    assert order is not None and drone is not None
    assert (order.status, order.package_weight_kg) == order_state
    assert (drone.status, drone.battery_pct, drone.longitude) == drone_state
    # The order and drone are still assignable afterwards.
    monkeypatch.undo()
    assert service.confirm_mission(seeded, ORDER, DRONE, SETTINGS).status == "ASSIGNED"


def test_a_rejected_confirmation_writes_nothing(seeded: Session) -> None:
    with pytest.raises(service.PlanRejectedError) as raised:
        service.confirm_mission(seeded, ORDER, "DRN-001", SETTINGS)  # DRN-001 sits at Osowa

    assert not raised.value.plan.eligible
    assert mission_count(seeded) == 0


def test_unknown_ids_are_reported_before_anything_is_written(seeded: Session) -> None:
    with pytest.raises(service.OrderNotFoundError):
        service.confirm_mission(seeded, "ORD-999", DRONE, SETTINGS)
    with pytest.raises(service.DroneNotFoundError):
        service.confirm_mission(seeded, ORDER, "DRN-999", SETTINGS)

    assert mission_count(seeded) == 0


def test_losing_a_race_to_the_unique_index_is_reported_as_already_assigned(
    seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulates a concurrent winner: the pre-check misses it, the database index catches it."""
    first = service.confirm_mission(seeded, ORDER, DRONE, SETTINGS)
    real_check = repository.order_has_active_mission
    seen: list[int] = []

    def stale_then_real(session: Session, order_id: str) -> bool:
        seen.append(1)
        return False if len(seen) == 1 else real_check(session, order_id)

    monkeypatch.setattr(repository, "order_has_active_mission", stale_then_real)

    with pytest.raises(service.PlanRejectedError) as raised:
        service.confirm_mission(seeded, ORDER, "DRN-011", SETTINGS)

    assert "ORDER_ALREADY_ASSIGNED" in [r.code for r in raised.value.plan.reasons]
    assert [m.id for m in seeded.scalars(select(Mission))] == [first.id]


# The shared test session keeps the first mission in its identity map; production uses one
# session per request. SQLAlchemy warns about the duplicate key before the database rejects it.
@pytest.mark.filterwarnings("ignore:New instance:sqlalchemy.exc.SAWarning")
def test_a_repeated_mission_id_is_retried_with_a_new_one(
    seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    taken = service.confirm_mission(seeded, "ORD-002", "DRN-011", SETTINGS)
    ids = iter([taken.id, taken.id, "MIS-0000000B"])
    monkeypatch.setattr(service, "new_mission_id", lambda: next(ids))

    mission = service.confirm_mission(seeded, ORDER, DRONE, SETTINGS)

    assert mission.id == "MIS-0000000B"
    assert mission_count(seeded) == 2


def test_cancelling_requires_an_assigned_mission(seeded: Session) -> None:
    mission = service.confirm_mission(seeded, ORDER, DRONE, SETTINGS)

    cancelled = service.cancel_mission(seeded, mission.id)

    assert cancelled.status == MissionStatus.CANCELLED
    with pytest.raises(service.MissionNotCancellableError) as again:
        service.cancel_mission(seeded, mission.id)
    assert again.value.status == "CANCELLED"
    with pytest.raises(service.MissionNotFoundError):
        service.cancel_mission(seeded, "MIS-00000000")


def test_an_in_flight_mission_is_not_cancellable_and_stays_unchanged(seeded: Session) -> None:
    mission = service.confirm_mission(seeded, ORDER, DRONE, SETTINGS)
    mission.status = MissionStatus.IN_FLIGHT.value
    seeded.commit()

    with pytest.raises(service.MissionNotCancellableError):
        service.cancel_mission(seeded, mission.id)

    seeded.expire_all()
    stored = seeded.get(Mission, mission.id)
    assert stored is not None
    assert stored.status == MissionStatus.IN_FLIGHT


def test_confirmation_stores_the_plan_snapshot(seeded: Session) -> None:
    plan = service.preview_plan(seeded, ORDER, DRONE, SETTINGS)

    mission = service.confirm_mission(seeded, ORDER, DRONE, SETTINGS)

    assert mission.return_hub_id == plan.route.return_hub_id
    assert mission.origin_to_destination_km == plan.route.origin_to_destination_km
    assert mission.destination_to_return_km == plan.route.destination_to_return_km
    assert mission.total_km == plan.route.total_km
    assert mission.expected_energy_pct == plan.energy.expected_pct
    assert mission.worst_case_energy_pct == plan.energy.worst_case_pct


def test_an_unexpected_integrity_error_is_not_retried_as_an_id_collision(
    seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts: list[int] = []

    def failing_insert(session: Session, mission: Mission) -> None:
        attempts.append(1)
        raise IntegrityError("INSERT", {}, Exception("some other constraint"))

    monkeypatch.setattr(service, "_insert_mission", failing_insert)

    with pytest.raises(IntegrityError):
        service.confirm_mission(seeded, ORDER, DRONE, SETTINGS)

    assert attempts == [1]  # no pointless retries
    assert mission_count(seeded) == 0


def test_locking_reads_refresh_rows_that_changed_since_they_were_loaded(seeded: Session) -> None:
    stale = repository.get_drone(seeded, DRONE)
    assert stale is not None
    assert stale.battery_pct == 100

    seeded.execute(update(Drone).where(Drone.id == DRONE).values(battery_pct=42))
    refreshed = repository.get_drone(seeded, DRONE, lock=True)

    assert refreshed is stale  # same identity, fresh values
    assert refreshed.battery_pct == 42

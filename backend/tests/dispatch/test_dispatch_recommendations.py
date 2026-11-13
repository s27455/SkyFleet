"""Read-only dispatch recommendations (feature 014A)."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.dispatch.schemas import PendingReason, RecommendationsResponse
from app.dispatch.service import recommend_for_session
from app.drones.models import Drone, DroneStatus
from app.hubs.models import Hub
from app.missions import service as missions_service
from app.missions.models import Mission
from app.orders.models import DeliveryOrder, OrderStatus

# Seeded layout (see conftest `seeded`): DRN-007..009 at Forum (100, 90, 80 %), DRN-010..012 at
# Galeria Bałtycka, DRN-004..006 at Riviera, DRN-001..003 at Osowa. ORD-004..006 start at Forum.
SETTINGS = Settings()


def _recommend(session: Session) -> RecommendationsResponse:
    return recommend_for_session(session, SETTINGS)


def _pairs(result: RecommendationsResponse) -> list[tuple[str, str]]:
    return [(r.order_id, r.drone_id) for r in result.recommendations]


def _pending(result: RecommendationsResponse) -> dict[str, PendingReason]:
    return {p.order_id: p.reason for p in result.pending}


def _drone(session: Session, drone_id: str) -> Drone:
    drone = session.get(Drone, drone_id)
    assert drone is not None
    return drone


def _charge(session: Session, *drone_ids: str) -> None:
    for drone_id in drone_ids:
        _drone(session, drone_id).battery_pct = 100
    session.commit()


# --- selection --------------------------------------------------------------------------------


def test_each_hub_gets_its_oldest_order_and_only_fully_charged_drones(seeded: Session) -> None:
    result = _recommend(seeded)

    # One 100 % drone per Hub: DRN-001 Osowa, DRN-004 Riviera, DRN-007 Forum, DRN-010 Bałtycka.
    assert _pairs(result) == [
        ("ORD-009", "DRN-001"),  # Osowa
        ("ORD-007", "DRN-004"),  # Riviera
        ("ORD-004", "DRN-007"),  # Forum
        ("ORD-001", "DRN-010"),  # Bałtycka
    ]
    assert all(r.return_hub_id for r in result.recommendations)


def test_two_orders_and_two_charged_drones_in_one_hub_give_two_distinct_pairs(
    seeded: Session,
) -> None:
    _charge(seeded, "DRN-008")

    result = _recommend(seeded)

    forum = [(o, d) for o, d in _pairs(result) if o in {"ORD-004", "ORD-005", "ORD-006"}]
    assert forum == [("ORD-004", "DRN-007"), ("ORD-005", "DRN-008")]
    assert _pending(result)["ORD-006"] == PendingReason.NO_ELIGIBLE_DRONE_AT_HUB


def test_one_drone_and_several_orders_recommend_the_oldest_and_never_reuse_the_drone(
    seeded: Session,
) -> None:
    result = _recommend(seeded)

    forum = [(o, d) for o, d in _pairs(result) if d == "DRN-007"]
    assert forum == [("ORD-004", "DRN-007")]
    assert set(_pending(result)) >= {"ORD-005", "ORD-006"}
    drones = [r.drone_id for r in result.recommendations]
    orders = [r.order_id for r in result.recommendations]
    assert len(set(drones)) == len(drones) and len(set(orders)) == len(orders)


def test_an_unserviceable_oldest_order_does_not_block_a_newer_one_in_the_hub(
    seeded: Session,
) -> None:
    far = seeded.get(DeliveryOrder, "ORD-004")
    assert far is not None
    far.destination_longitude, far.destination_latitude = 19.9, 55.4  # far beyond the budget
    seeded.commit()

    result = _recommend(seeded)

    assert ("ORD-005", "DRN-007") in _pairs(result)
    rejected = next(p for p in result.pending if p.order_id == "ORD-004")
    assert rejected.reason == PendingReason.PLANNER_REJECTED
    assert "ROUTE_TOO_LONG" in rejected.planner_reasons


def test_a_hub_without_eligible_drones_does_not_block_other_hubs(seeded: Session) -> None:
    _drone(seeded, "DRN-007").battery_pct = 99  # Forum has no 100 % drone left
    seeded.commit()

    result = _recommend(seeded)

    assert set(_pairs(result)) == {
        ("ORD-009", "DRN-001"),
        ("ORD-007", "DRN-004"),
        ("ORD-001", "DRN-010"),
    }
    assert _pending(result)["ORD-004"] == PendingReason.NO_ELIGIBLE_DRONE_AT_HUB


# --- exclusions: each makes DRN-007 (the only candidate at Forum) ineligible -------------------


def _exclude_battery(session: Session) -> None:
    _drone(session, "DRN-007").battery_pct = 99


def _exclude_maintenance(session: Session) -> None:
    _drone(session, "DRN-007").status = DroneStatus.MAINTENANCE.value


def _exclude_in_flight(session: Session) -> None:
    _drone(session, "DRN-007").status = DroneStatus.IN_FLIGHT.value


def _exclude_charging(session: Session) -> None:
    _drone(session, "DRN-007").status = DroneStatus.CHARGING.value


def _exclude_wrong_hub(session: Session) -> None:
    osowa = session.get(Hub, "hub-centrum-handlowe-osowa")
    assert osowa is not None
    drone = _drone(session, "DRN-007")  # still assigned to Forum, but physically at Osowa
    drone.longitude, drone.latitude = osowa.longitude, osowa.latitude


def _exclude_off_hub(session: Session) -> None:
    drone = _drone(session, "DRN-007")
    drone.longitude, drone.latitude = 18.7, 54.5  # IDLE and charged, but docked nowhere


@pytest.mark.parametrize(
    "exclude",
    [
        _exclude_battery,
        _exclude_maintenance,
        _exclude_in_flight,
        _exclude_charging,
        _exclude_wrong_hub,
        _exclude_off_hub,
    ],
)
def test_an_ineligible_drone_is_never_recommended(
    seeded: Session, exclude: Callable[[Session], None]
) -> None:
    exclude(seeded)
    seeded.commit()

    result = _recommend(seeded)

    # A drone docked elsewhere (the wrong-Hub case) may serve that Hub, but never Forum's orders.
    forum = [r for r in result.recommendations if r.origin_hub_id == "hub-forum-gdansk"]
    assert forum == []
    assert _pending(result)["ORD-004"] == PendingReason.NO_ELIGIBLE_DRONE_AT_HUB


def test_a_drone_with_an_active_mission_is_excluded_and_its_order_is_not_considered(
    seeded: Session,
) -> None:
    missions_service.confirm_mission(seeded, "ORD-005", "DRN-007", SETTINGS)

    result = _recommend(seeded)

    assert "DRN-007" not in [r.drone_id for r in result.recommendations]
    assert "ORD-005" not in {r.order_id for r in result.recommendations}
    assert "ORD-005" not in _pending(result)  # already has a mission: not waiting
    assert _pending(result)["ORD-004"] == PendingReason.NO_ELIGIBLE_DRONE_AT_HUB


def test_orders_that_are_not_ready_are_not_considered(seeded: Session) -> None:
    order = seeded.get(DeliveryOrder, "ORD-004")
    assert order is not None
    order.status = OrderStatus.AWAITING_HANDOVER.value
    seeded.commit()

    result = _recommend(seeded)

    assert ("ORD-005", "DRN-007") in _pairs(result)
    assert "ORD-004" not in _pending(result)


def test_a_drone_left_below_full_charge_stays_ineligible_until_charged(seeded: Session) -> None:
    drone = _drone(seeded, "DRN-007")
    drone.battery_pct = 87  # what a landing leaves; nothing recharges it yet
    seeded.commit()
    assert "DRN-007" not in [r.drone_id for r in _recommend(seeded).recommendations]

    drone.battery_pct = 100  # a later charging feature
    seeded.commit()
    assert ("ORD-004", "DRN-007") in _pairs(_recommend(seeded))


# --- read-only and deterministic --------------------------------------------------------------


@contextmanager
def _statements(engine: Engine) -> Iterator[list[str]]:
    seen: list[str] = []

    def record(_conn: object, _cur: object, statement: str, *_rest: object) -> None:
        seen.append(statement.lstrip().split(None, 1)[0].upper())

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", record)


def test_repeated_calls_are_identical_and_write_nothing(seeded: Session, engine: Engine) -> None:
    first = _recommend(seeded)
    with _statements(engine) as statements:
        second = _recommend(seeded)
        third = _recommend(seeded)

    assert first == second == third
    assert statements and not {"INSERT", "UPDATE", "DELETE"} & set(statements)
    assert not (seeded.new or seeded.dirty or seeded.deleted)
    assert seeded.scalars(select(Mission)).all() == []


def test_recommendations_do_not_change_orders_or_drones(seeded: Session) -> None:
    before = (
        [(o.id, o.status, o.updated_at) for o in seeded.scalars(select(DeliveryOrder))],
        [(d.id, d.status, d.battery_pct, d.longitude) for d in seeded.scalars(select(Drone))],
    )

    _recommend(seeded)
    seeded.expire_all()

    after = (
        [(o.id, o.status, o.updated_at) for o in seeded.scalars(select(DeliveryOrder))],
        [(d.id, d.status, d.battery_pct, d.longitude) for d in seeded.scalars(select(Drone))],
    )
    assert before == after


# --- endpoint ---------------------------------------------------------------------------------


def test_endpoint_returns_recommendations_and_creates_no_mission(
    client: TestClient, seeded: Session
) -> None:
    response = client.get("/api/dispatch/recommendations")

    assert response.status_code == 200
    body = response.json()
    assert {(r["order_id"], r["drone_id"]) for r in body["recommendations"]} == {
        ("ORD-009", "DRN-001"),
        ("ORD-007", "DRN-004"),
        ("ORD-004", "DRN-007"),
        ("ORD-001", "DRN-010"),
    }
    first = body["recommendations"][0]
    assert set(first) == {"order_id", "drone_id", "origin_hub_id", "return_hub_id"}
    assert body["pending"]
    assert set(body["pending"][0]) == {"order_id", "origin_hub_id", "reason", "planner_reasons"}
    assert client.get("/api/missions").json() == []
    assert client.get("/api/dispatch/recommendations").json() == body


def test_endpoint_is_empty_without_data(client: TestClient) -> None:
    response = client.get("/api/dispatch/recommendations")

    assert response.status_code == 200
    assert response.json() == {"recommendations": [], "pending": []}

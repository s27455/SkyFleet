"""Dispatch execution: one explicit, revalidated create-and-start (feature 014B)."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.dispatch import service as dispatch_service
from app.drones.models import Drone, DroneStatus
from app.missions import service as missions_service
from app.missions.models import Mission, MissionStatus
from app.orders.models import DeliveryOrder, OrderStatus
from app.simulation import clock
from app.simulation import service as simulation_service
from app.simulation.heartbeat import record_heartbeat

FORUM = "hub-forum-gdansk"
# Seeded: DRN-007 (100 %), DRN-008 (90 %), DRN-009 (80 %) at Forum; ORD-004..006 start at Forum.
PAIR = {"order_id": "ORD-004", "drone_id": "DRN-007"}


@pytest.fixture
def live(seeded: Session) -> Session:
    """The seeded data with a fresh simulation worker heartbeat (takeoff needs one)."""
    record_heartbeat(seeded, clock.utcnow())
    return seeded


def _execute(client: TestClient, **pair: str) -> tuple[int, dict[str, object]]:
    response = client.post("/api/dispatch/execute", json=pair or PAIR)
    return response.status_code, response.json()


def _missions(session: Session) -> list[Mission]:
    session.expire_all()
    return list(session.scalars(select(Mission)))


def _detail(body: dict[str, object]) -> dict[str, object]:
    detail = body["detail"]
    assert isinstance(detail, dict)
    return detail


def _drone(session: Session, drone_id: str) -> Drone:
    drone = session.get(Drone, drone_id)
    assert drone is not None
    return drone


# --- success ----------------------------------------------------------------------------------


def test_a_valid_pair_creates_one_mission_and_starts_it(client: TestClient, live: Session) -> None:
    status, body = _execute(client)

    assert status == 201
    assert body["status"] == "IN_FLIGHT"
    assert (body["order_id"], body["drone_id"]) == ("ORD-004", "DRN-007")
    assert str(body["id"]).startswith("MIS-")
    [mission] = _missions(live)
    assert mission.id == body["id"] and mission.status == MissionStatus.IN_FLIGHT
    assert _drone(live, "DRN-007").status == DroneStatus.IN_FLIGHT
    order = live.get(DeliveryOrder, "ORD-004")
    assert order is not None and order.status == OrderStatus.OUT_FOR_DELIVERY


def test_a_recommended_pair_can_be_executed(client: TestClient, live: Session) -> None:
    recommended = client.get("/api/dispatch/recommendations").json()["recommendations"][0]

    status, body = _execute(
        client, order_id=recommended["order_id"], drone_id=recommended["drone_id"]
    )

    assert status == 201 and body["return_hub_id"] == recommended["return_hub_id"]


# --- rejections create nothing ----------------------------------------------------------------


def test_a_drone_below_full_charge_is_rejected_atomically(
    client: TestClient, live: Session
) -> None:
    status, body = _execute(client, order_id="ORD-004", drone_id="DRN-008")  # 90 %

    assert status == 409
    detail = _detail(body)
    assert detail["code"] == "DRONE_NOT_FULLY_CHARGED"
    assert (detail["battery_pct"], detail["required_pct"]) == (90, 100)
    assert _missions(live) == []


def _maintenance(session: Session) -> None:
    _drone(session, "DRN-007").status = DroneStatus.MAINTENANCE.value


def _in_flight(session: Session) -> None:
    _drone(session, "DRN-007").status = DroneStatus.IN_FLIGHT.value


def _not_ready(session: Session) -> None:
    order = session.get(DeliveryOrder, "ORD-004")
    assert order is not None
    order.status = OrderStatus.AWAITING_HANDOVER.value


def _out_of_range(session: Session) -> None:
    order = session.get(DeliveryOrder, "ORD-004")
    assert order is not None
    order.destination_longitude, order.destination_latitude = 19.9, 55.4


@pytest.mark.parametrize(
    ("break_it", "reason"),
    [
        (_maintenance, "DRONE_NOT_AVAILABLE"),
        (_in_flight, "DRONE_NOT_AVAILABLE"),
        (_not_ready, "ORDER_NOT_READY"),
        (_out_of_range, "ROUTE_TOO_LONG"),
    ],
)
def test_planner_rejections_name_the_reason_and_create_no_mission(
    client: TestClient, live: Session, break_it: Callable[[Session], None], reason: str
) -> None:
    break_it(live)
    live.commit()

    status, body = _execute(client)

    assert status == 409
    detail = _detail(body)
    assert detail["code"] == "MISSION_NOT_ELIGIBLE"
    plan = detail["plan"]
    assert isinstance(plan, dict)
    assert reason in [r["code"] for r in plan["reasons"]]
    assert _missions(live) == []


def test_a_drone_at_another_hub_is_rejected(client: TestClient, live: Session) -> None:
    status, body = _execute(client, order_id="ORD-004", drone_id="DRN-001")  # DRN-001 is at Osowa

    assert status == 409
    plan = _detail(body)["plan"]
    assert isinstance(plan, dict)
    assert "DRONE_NOT_AT_ORIGIN_HUB" in [r["code"] for r in plan["reasons"]]
    assert _missions(live) == []


def test_a_drone_with_an_active_mission_is_rejected(client: TestClient, live: Session) -> None:
    missions_service.confirm_mission(live, "ORD-005", "DRN-007", Settings())

    status, body = _execute(client)  # ORD-004 with the busy DRN-007

    assert status == 409
    plan = _detail(body)["plan"]
    assert isinstance(plan, dict)
    assert "DRONE_ALREADY_ASSIGNED" in [r["code"] for r in plan["reasons"]]
    assert len(_missions(live)) == 1


def test_unknown_order_or_drone_is_404(client: TestClient, live: Session) -> None:
    assert _execute(client, order_id="ORD-999", drone_id="DRN-007")[0] == 404
    assert _execute(client, order_id="ORD-004", drone_id="DRN-999")[0] == 404
    assert _missions(live) == []


def test_invalid_bodies_are_422(client: TestClient, live: Session) -> None:
    assert client.post("/api/dispatch/execute", json={"order_id": "ORD-004"}).status_code == 422
    assert client.post("/api/dispatch/execute", json={**PAIR, "order_id": ""}).status_code == 422


def test_without_a_running_worker_nothing_is_created(client: TestClient, seeded: Session) -> None:
    status, body = _execute(client)  # no heartbeat recorded

    assert status == 503
    assert _detail(body)["code"] == "SIMULATION_WORKER_UNAVAILABLE"
    assert _missions(seeded) == []
    assert _drone(seeded, "DRN-007").status == DroneStatus.IDLE


# --- repeats ----------------------------------------------------------------------------------


def test_a_repeated_request_creates_no_second_mission(client: TestClient, live: Session) -> None:
    _, first = _execute(client)

    status, body = _execute(client)

    assert status == 409
    detail = _detail(body)
    assert detail["code"] == "DISPATCH_ALREADY_ASSIGNED"
    assert detail["mission_id"] == first["id"] and detail["status"] == "IN_FLIGHT"
    assert len(_missions(live)) == 1


# --- failed and ambiguous starts --------------------------------------------------------------


def test_a_failed_start_keeps_the_mission_assigned_and_blocks_duplicates(
    client: TestClient, live: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_start(*_args: object, **_kwargs: object) -> Mission:
        raise simulation_service.WorkerUnavailableError(None, 10)  # the worker died in between

    monkeypatch.setattr(dispatch_service, "start_mission", failing_start)

    status, body = _execute(client)

    assert status == 409
    detail = _detail(body)
    assert detail["code"] == "DISPATCH_START_FAILED"
    assert detail["status"] == "ASSIGNED"
    [mission] = _missions(live)
    assert detail["mission_id"] == mission.id and mission.status == MissionStatus.ASSIGNED
    assert f"/api/missions/{mission.id}/start" in str(detail["message"])
    # Nothing flew: the drone and the order are untouched.
    assert _drone(live, "DRN-007").status == DroneStatus.IDLE
    order = live.get(DeliveryOrder, "ORD-004")
    assert order is not None and order.status == OrderStatus.READY_FOR_PICKUP

    # A retry does not create another mission while this one is active, and says which it is.
    status, body = _execute(client)
    assert status == 409 and _detail(body)["code"] == "DISPATCH_ALREADY_ASSIGNED"
    assert _detail(body)["mission_id"] == mission.id
    assert len(_missions(live)) == 1

    # Recovery with the existing manual endpoint.
    monkeypatch.undo()
    assert client.post(f"/api/missions/{mission.id}/start").status_code == 200


def test_an_unexpected_start_error_is_reported_without_echoing_it(
    client: TestClient, live: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_start(*_args: object, **_kwargs: object) -> Mission:
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(dispatch_service, "start_mission", broken_start)

    status, body = _execute(client)

    assert status == 409
    detail = _detail(body)
    assert detail["code"] == "DISPATCH_START_FAILED" and detail["cause"] == "unexpected error"
    assert "secret" not in str(body)
    assert [m.status for m in _missions(live)] == [MissionStatus.ASSIGNED]


def test_a_start_that_committed_before_erroring_is_reported_as_started(
    client: TestClient, live: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_start = simulation_service.start_mission

    def commit_then_fail(*args: object, **kwargs: object) -> Mission:
        real_start(*args, **kwargs)  # type: ignore[arg-type]
        raise RuntimeError("connection lost after commit")

    monkeypatch.setattr(dispatch_service, "start_mission", commit_then_fail)

    status, body = _execute(client)

    assert status == 201 and body["status"] == "IN_FLIGHT"
    assert [m.status for m in _missions(live)] == [MissionStatus.IN_FLIGHT]


# --- existing behavior is unchanged -----------------------------------------------------------


def test_manual_missions_still_accept_a_drone_below_full_charge(
    client: TestClient, live: Session
) -> None:
    response = client.post("/api/missions", json={"order_id": "ORD-004", "drone_id": "DRN-008"})

    assert response.status_code == 201  # 90 % battery: the 100 % rule is dispatch-only


def test_recommendations_still_work(client: TestClient, live: Session) -> None:
    response = client.get("/api/dispatch/recommendations")

    assert response.status_code == 200 and response.json()["recommendations"]
    assert _missions(live) == []

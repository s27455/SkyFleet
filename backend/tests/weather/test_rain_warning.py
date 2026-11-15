"""Rain warning and flight grounding (Feature 020) on SQLite with a controlled clock.

The warning blocks NEW takeoffs only. Every test that checks a refusal also checks that nothing was
written, and every test of an airborne flight checks that the warning changes nothing for it.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.common import clock
from app.config import Settings
from app.dispatch import auto
from app.dispatch import service as dispatch_service
from app.drones.models import Drone, DroneStatus
from app.events.models import EventOrigin, EventType, OperationalEvent
from app.hubs.models import Hub
from app.missions import service as missions_service
from app.missions.models import Mission, MissionPurpose, MissionStatus
from app.orders import cancellation
from app.orders.models import DeliveryOrder, OrderStatus
from app.simulation import engine
from app.simulation.failure import trigger_drone_failure
from app.simulation.heartbeat import record_heartbeat
from app.simulation.models import FlightPhase, MissionFlight
from app.simulation.relocation import start_relocation
from app.weather import service as weather
from app.weather.service import RainWarningActiveError

Launch = Callable[..., str]
Factory = sessionmaker[Session]

NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
ORDER, DRONE = "ORD-001", "DRN-010"  # docked at Galeria Baltycka, 100%
BALTYCKA, FORUM = "hub-galeria-baltycka", "hub-forum-gdansk"


def at(seconds: float) -> datetime:
    return NOW + timedelta(seconds=seconds)


def _count(session: Session, model: type) -> int:
    session.expire_all()
    return session.scalar(select(func.count()).select_from(model)) or 0


def _events(session: Session, kind: EventType) -> list[OperationalEvent]:
    session.expire_all()
    return list(
        session.scalars(select(OperationalEvent).where(OperationalEvent.event_type == kind.value))
    )


def _rain(factory: Factory, on: bool) -> None:
    with factory() as session:
        (weather.activate if on else weather.clear)(session, NOW)


def _advance(factory: Factory, settings: Settings, mission_id: str, seconds: float) -> None:
    engine.advance_flight(factory, settings, mission_id, at(seconds))


def _flight(session: Session, mission_id: str) -> MissionFlight:
    session.expire_all()
    flight = session.get(MissionFlight, mission_id)
    assert flight is not None
    return flight


def _mission(session: Session, mission_id: str) -> Mission:
    session.expire_all()
    mission = session.get(Mission, mission_id)
    assert mission is not None
    return mission


def _drone(session: Session, drone_id: str = DRONE) -> Drone:
    session.expire_all()
    drone = session.get(Drone, drone_id)
    assert drone is not None
    return drone


@pytest.fixture
def live(seeded: Session) -> Session:
    record_heartbeat(seeded, NOW)
    return seeded


@pytest.fixture
def api(client: TestClient, live: Session, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(clock, "utcnow", lambda: NOW)
    return client


# --- state: idempotent, one event each, persisted -----------------------------------------------


def test_activation_and_clearing_are_idempotent_and_record_one_event_each(
    session: Session, session_factory: Factory
) -> None:
    assert weather.get_status(session).active is False  # a missing row means inactive

    first, changed_first = weather.activate(session, NOW)
    again, changed_again = weather.activate(session, at(5))
    assert (first.active, changed_first, changed_again) == (True, True, False)
    assert again.activated_at == first.activated_at  # the second click changed nothing
    assert len(_events(session, EventType.RAIN_WARNING_ACTIVATED)) == 1

    with session_factory() as other:  # persisted: a new session (a restarted process) sees it
        assert weather.get_status(other).active is True

    cleared, changed_clear = weather.clear(session, at(10))
    _, changed_clear_again = weather.clear(session, at(11))
    assert (cleared.active, changed_clear, changed_clear_again) == (False, True, False)
    assert len(_events(session, EventType.RAIN_WARNING_CLEARED)) == 1
    event = _events(session, EventType.RAIN_WARNING_ACTIVATED)[0]
    assert event.origin == EventOrigin.MANUAL.value
    assert event.order_id is None and event.drone_id is None


def test_the_api_activates_clears_and_lists_the_events(api: TestClient) -> None:
    assert api.get("/api/incidents/rain-warning").json()["active"] is False

    body = api.post("/api/incidents/rain-warning/activate").json()
    assert body["active"] is True and body["changed"] is True and body["origin"] == "MANUAL"
    repeated = api.post("/api/incidents/rain-warning/activate").json()
    assert repeated["active"] is True and repeated["changed"] is False
    assert api.get("/api/incidents/rain-warning").json()["activated_at"] is not None

    events = api.get("/api/events", params={"event_type": "RAIN_WARNING_ACTIVATED"}).json()
    assert [event["event_type"] for event in events] == ["RAIN_WARNING_ACTIVATED"]

    cleared = api.post("/api/incidents/rain-warning/clear").json()
    assert cleared["active"] is False and cleared["changed"] is True
    assert api.post("/api/incidents/rain-warning/clear").json()["changed"] is False


# --- takeoff blocked, nothing written -----------------------------------------------------------


def test_a_manual_start_is_refused_and_the_assigned_mission_starts_after_clearing(
    live: Session, api: TestClient, sim_settings: Settings, session_factory: Factory
) -> None:
    mission = missions_service.confirm_mission(live, ORDER, DRONE, sim_settings)  # assignment: OK
    _rain(session_factory, True)
    flights_before = _count(live, MissionFlight)

    response = api.post(f"/api/missions/{mission.id}/start")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "RAIN_WARNING_ACTIVE"
    assert "rain warning" in response.json()["detail"]["message"].lower()
    assert _count(live, MissionFlight) == flights_before  # no flight, no partial writes
    assert _mission(live, mission.id).status == MissionStatus.ASSIGNED
    assert _drone(live).status == DroneStatus.IDLE
    order = live.get(DeliveryOrder, ORDER)
    assert order is not None and order.status != OrderStatus.OUT_FOR_DELIVERY

    _rain(session_factory, False)  # recoverable with the existing workflow, no restart
    assert api.post(f"/api/missions/{mission.id}/start").status_code == 200
    assert _mission(live, mission.id).status == MissionStatus.IN_FLIGHT


def test_an_assigned_mission_can_still_be_cancelled_while_the_warning_is_active(
    live: Session, sim_settings: Settings, session_factory: Factory
) -> None:
    mission = missions_service.confirm_mission(live, ORDER, DRONE, sim_settings)
    _rain(session_factory, True)

    missions_service.cancel_mission(live, mission.id)

    assert _mission(live, mission.id).status == MissionStatus.CANCELLED  # drone and order released
    again = missions_service.confirm_mission(live, ORDER, DRONE, sim_settings)
    assert again.status == MissionStatus.ASSIGNED


def test_a_manual_dispatch_is_refused_before_anything_is_created(
    live: Session, api: TestClient, session_factory: Factory
) -> None:
    _rain(session_factory, True)

    response = api.post("/api/dispatch/execute", json={"order_id": ORDER, "drone_id": DRONE})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "RAIN_WARNING_ACTIVE"
    assert _count(live, Mission) == 0
    assert _drone(live).status == DroneStatus.IDLE

    _rain(session_factory, False)
    assert (
        api.post("/api/dispatch/execute", json={"order_id": ORDER, "drone_id": DRONE}).status_code
        == 201
    )


def test_a_warning_that_wins_the_race_after_the_assignment_leaves_no_stranded_mission(
    live: Session,
    sim_settings: Settings,
    session_factory: Factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The warning activates between the dispatch's early check and the takeoff itself."""
    _rain(session_factory, True)
    monkeypatch.setattr(weather, "is_active", lambda session: False)

    with pytest.raises(RainWarningActiveError):
        dispatch_service.execute_dispatch(live, ORDER, DRONE, NOW, sim_settings)

    # The mission the call created was cancelled with the existing cancellation: the drone and the
    # order are free again, nothing flies, nothing stays reserved.
    missions = list(live.scalars(select(Mission)))
    assert [m.status for m in missions] == [MissionStatus.CANCELLED.value]
    assert _count(live, MissionFlight) == 0
    assert _drone(live).status == DroneStatus.IDLE

    _rain(session_factory, False)
    monkeypatch.undo()
    record_heartbeat(live, NOW)
    started = dispatch_service.execute_dispatch(live, ORDER, DRONE, NOW, sim_settings)
    assert started.status == MissionStatus.IN_FLIGHT


def test_a_relocation_is_refused_and_writes_nothing(
    live: Session, api: TestClient, sim_settings: Settings, session_factory: Factory
) -> None:
    _rain(session_factory, True)
    events_before = _count(live, OperationalEvent)

    response = api.post(f"/api/drones/{DRONE}/relocate", json={"destination_hub_id": FORUM})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "RAIN_WARNING_ACTIVE"
    assert _count(live, Mission) == 0 and _count(live, MissionFlight) == 0
    assert _count(live, OperationalEvent) == events_before
    assert _drone(live).status == DroneStatus.IDLE

    _rain(session_factory, False)
    assert (
        api.post(f"/api/drones/{DRONE}/relocate", json={"destination_hub_id": FORUM}).status_code
        == 201
    )


# --- Auto Dispatch and automatic rebalancing ----------------------------------------------------


def test_auto_dispatch_starts_nothing_while_active_and_resumes_after_clearing(
    live: Session,
    sim_settings: Settings,
    session_factory: Factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with session_factory() as session:
        auto.enable(session, NOW, sim_settings)
    _rain(session_factory, True)
    relocations: list[object] = []
    monkeypatch.setattr(auto, "run_rebalancing", lambda *args, **kwargs: relocations.append(1))

    first = auto.run_dispatch_pass(session_factory, sim_settings, NOW)
    second = auto.run_dispatch_pass(session_factory, sim_settings, at(2))

    assert first == second == auto.RAIN_OUTCOME
    assert _count(live, Mission) == 0  # no pending missions either: queued orders just wait
    assert relocations == []  # no rebalancing relocation was even considered
    with session_factory() as session:
        assert auto.is_enabled(session_factory)  # the mode itself is unchanged
        assert auto.get_status(session, at(2), sim_settings).enabled is True

    _rain(session_factory, False)
    monkeypatch.undo()
    outcome = auto.run_dispatch_pass(session_factory, sim_settings, at(4))
    assert outcome is not None and "Started" in outcome
    assert _count(live, Mission) > 0


def test_a_blocked_rebalancing_relocation_starts_nothing(
    live: Session, sim_settings: Settings, session_factory: Factory
) -> None:
    _rain(session_factory, True)
    with pytest.raises(RainWarningActiveError):
        start_relocation(live, DRONE, FORUM, NOW, sim_settings, origin=EventOrigin.AUTOMATIC)
    assert _count(live, Mission) == 0


# --- airborne flights are never affected --------------------------------------------------------


def test_a_delivery_in_flight_completes_normally_while_the_warning_is_active(
    live: Session, launch: Launch, sim_settings: Settings, session_factory: Factory
) -> None:
    live.rollback()
    mission_id = launch(ORDER, DRONE)
    _rain(session_factory, True)

    phases = []
    for seconds in (5, 25, 33, 500):  # outbound, delivering/returning, landing decision, landed
        _advance(session_factory, sim_settings, mission_id, seconds)
        phases.append(_flight(live, mission_id).phase)

    assert phases[0] == FlightPhase.OUTBOUND
    assert FlightPhase.RETURNING in phases or FlightPhase.DELIVERING in phases
    assert phases[-1] == FlightPhase.LANDED
    assert _mission(live, mission_id).status == MissionStatus.COMPLETED
    assert _drone(live).status == DroneStatus.IDLE
    order = live.get(DeliveryOrder, ORDER)
    assert order is not None and order.status == OrderStatus.DELIVERED


def test_a_diversion_to_another_hub_still_lands_while_the_warning_is_active(
    live: Session, launch: Launch, sim_settings: Settings, session_factory: Factory
) -> None:
    live.rollback()
    mission_id = launch(ORDER, DRONE)
    live.execute(update(Hub).where(Hub.id == BALTYCKA).values(drone_capacity=2))
    live.commit()
    _rain(session_factory, True)

    _advance(session_factory, sim_settings, mission_id, 34.7)
    assert _flight(live, mission_id).phase == FlightPhase.DIVERTING

    _advance(session_factory, sim_settings, mission_id, 500)
    assert _flight(live, mission_id).landed_hub_id == FORUM
    assert _mission(live, mission_id).status == MissionStatus.COMPLETED
    assert _drone(live).status == DroneStatus.IDLE


def test_a_relocation_in_flight_completes_while_the_warning_is_active(
    live: Session, sim_settings: Settings, session_factory: Factory
) -> None:
    mission = start_relocation(live, DRONE, FORUM, NOW, sim_settings)
    _rain(session_factory, True)

    _advance(session_factory, sim_settings, mission.id, 5)
    assert _flight(live, mission.id).phase == FlightPhase.RELOCATING
    _advance(session_factory, sim_settings, mission.id, 500)

    assert _flight(live, mission.id).phase == FlightPhase.LANDED
    assert _mission(live, mission.id).status == MissionStatus.COMPLETED
    assert _mission(live, mission.id).purpose == MissionPurpose.RELOCATION
    assert _drone(live).hub_id == FORUM


def test_a_relocation_diverts_to_another_hub_while_the_warning_is_active(
    live: Session, sim_settings: Settings, session_factory: Factory
) -> None:
    mission = start_relocation(live, DRONE, FORUM, NOW, sim_settings)
    live.execute(
        update(Hub).where(Hub.id == FORUM).values(drone_capacity=3)  # full on arrival
    )
    live.commit()
    _rain(session_factory, True)

    _advance(session_factory, sim_settings, mission.id, 500)

    flight = _flight(live, mission.id)
    assert flight.phase == FlightPhase.LANDED
    assert flight.landed_hub_id not in (None, FORUM)  # the existing diversion took it elsewhere
    assert _mission(live, mission.id).status == MissionStatus.COMPLETED


def test_failure_recall_and_cancellation_still_work_while_the_warning_is_active(
    live: Session, launch: Launch, sim_settings: Settings, session_factory: Factory
) -> None:
    live.rollback()
    failing = launch(ORDER, DRONE)
    recalled = launch("ORD-002", "DRN-011")
    _rain(session_factory, True)
    _advance(session_factory, sim_settings, failing, 3)
    _advance(session_factory, sim_settings, recalled, 3)

    cancellation.cancel_order(live, "ORD-002", at(4), sim_settings)  # recall of an active mission
    result = trigger_drone_failure(live, at(5), sim_settings)  # failure handling

    assert result.mission_id in (failing, recalled)  # either eligible flight may be chosen
    other = recalled if result.mission_id == failing else failing
    for mission_id in (failing, recalled):
        _advance(session_factory, sim_settings, mission_id, 500)
    assert _flight(live, result.mission_id).phase == FlightPhase.EMERGENCY
    assert _flight(live, other).phase == FlightPhase.LANDED

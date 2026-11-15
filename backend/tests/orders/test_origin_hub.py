"""Automatic origin Hub for a manual order (Feature 021D): the nearest Hub that can serve it."""

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.drones.models import Drone, DroneModel
from app.events.models import OperationalEvent
from app.hubs.models import Hub
from app.missions.planning import evaluate_plan
from app.orders.feasibility import choose_origin_hub, route_problem
from app.orders.models import DeliveryOrder

SETTINGS = Settings()
FACTOR = SETTINGS.mission_payload_energy_factor
FORUM = "hub-forum-gdansk"
GALERIA = "hub-galeria-baltycka"
OSOWA = "hub-centrum-handlowe-osowa"
RIVIERA = "hub-centrum-riviera"

NEAR_FORUM = (18.6531, 54.3487)
NEAR_RIVIERA = (18.5440, 54.5189)
LIMIT_OF_RANGE = (18.57, 54.445)  # Osowa serves it up to 2.6 kg
TOO_FAR = (18.70, 54.50)


def _body(point: tuple[float, float], weight: float = 0.5, **extra: object) -> dict[str, object]:
    return {
        "destination_address": "ul. Testowa 1, Gdańsk",
        "destination_longitude": point[0],
        "destination_latitude": point[1],
        "package_weight_kg": weight,
        **extra,
    }


def _hubs(session: Session) -> list[Hub]:
    return list(session.scalars(select(Hub).order_by(Hub.id)))


def _model(session: Session) -> DroneModel:
    model = session.scalars(select(DroneModel).order_by(DroneModel.id)).first()
    assert model is not None
    return model


def _count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(DeliveryOrder)) or 0


# --- the rule ---------------------------------------------------------------------------------


def test_the_nearest_hub_wins(seeded: Session) -> None:
    hubs, model = _hubs(seeded), _model(seeded)

    forum, _ = choose_origin_hub(hubs, model, NEAR_FORUM, 0.5, FACTOR)
    riviera, _ = choose_origin_hub(hubs, model, NEAR_RIVIERA, 0.5, FACTOR)

    assert forum is not None and forum.id == FORUM
    assert riviera is not None and riviera.id == RIVIERA


def test_a_tie_goes_to_the_lower_hub_id(seeded: Session) -> None:
    hubs, model = _hubs(seeded), _model(seeded)
    first = hubs[0]
    twin = Hub(
        id="a-twin-of-" + first.id,
        name="Twin",
        address="x",
        longitude=first.longitude,
        latitude=first.latitude,
        drone_capacity=6,
    )

    chosen, _ = choose_origin_hub(
        [*hubs, twin], model, (first.longitude, first.latitude), 0.5, FACTOR
    )

    assert chosen is not None and chosen.id == twin.id  # sorts before the original id


def test_a_destination_beyond_the_mission_distance_has_no_hub(seeded: Session) -> None:
    hubs, model = _hubs(seeded), _model(seeded)

    chosen, reason = choose_origin_hub(hubs, model, TOO_FAR, 0.5, FACTOR)

    assert chosen is None
    assert reason is not None and "exceeds the 14 km mission distance" in reason


def test_a_parcel_too_heavy_for_the_battery_reports_the_heaviest_possible(seeded: Session) -> None:
    hubs, model = _hubs(seeded), _model(seeded)
    osowa = next(h for h in hubs if h.id == OSOWA)

    assert route_problem(osowa, LIMIT_OF_RANGE, 2.6, hubs, model, FACTOR) is None
    reason = route_problem(osowa, LIMIT_OF_RANGE, 3.0, hubs, model, FACTOR)

    assert reason is not None and "the heaviest possible here is 2.6 kg" in reason
    assert choose_origin_hub(hubs, model, LIMIT_OF_RANGE, 3.0, FACTOR)[0] is None


def test_a_parcel_above_the_model_payload_is_refused(seeded: Session) -> None:
    hubs, model = _hubs(seeded), _model(seeded)

    reason = route_problem(hubs[0], NEAR_FORUM, model.max_payload_kg + 0.5, hubs, model, FACTOR)

    assert reason is not None and "carries at most" in reason


# --- API --------------------------------------------------------------------------------------


def test_create_without_a_hub_picks_the_nearest_and_records_a_manual_event(
    client: TestClient, seeded: Session
) -> None:
    response = client.post("/api/orders", json=_body(NEAR_FORUM))

    assert response.status_code == 201
    body = response.json()
    assert body["origin_hub_id"] == FORUM
    assert body["status"] == "READY_FOR_PICKUP"
    event = seeded.scalars(
        select(OperationalEvent).where(OperationalEvent.order_id == body["id"])
    ).one()
    assert (event.event_type, event.origin) == ("ORDER_CREATED", "MANUAL")


def test_the_chosen_hub_is_stored_and_not_reassigned(client: TestClient, seeded: Session) -> None:
    created = client.post("/api/orders", json=_body(NEAR_RIVIERA)).json()

    again = client.get(f"/api/orders/{created['id']}").json()

    assert created["origin_hub_id"] == again["origin_hub_id"] == RIVIERA


def test_the_chosen_hub_gives_an_order_the_planner_accepts(
    client: TestClient, seeded: Session
) -> None:
    hubs = _hubs(seeded)
    drones = list(seeded.scalars(select(Drone)))
    full = {d.hub_id: d for d in drones if d.battery_pct == 100}
    for point, weight in ((NEAR_FORUM, 3.0), (NEAR_RIVIERA, 1.0), (LIMIT_OF_RANGE, 2.6)):
        body = client.post("/api/orders", json=_body(point, weight)).json()
        order = seeded.get(DeliveryOrder, body["id"])
        assert order is not None
        plan = evaluate_plan(
            order=order,
            drone=full[order.origin_hub_id],
            hubs=hubs,
            drones=drones,
            order_has_active_mission=False,
            drone_has_active_mission=False,
            payload_energy_factor=FACTOR,
            dock_proximity_m=SETTINGS.hub_dock_proximity_m,
        )
        assert plan.eligible, (point, [r.code for r in plan.reasons])


def test_an_explicit_hub_is_still_honoured_even_if_it_is_not_the_nearest(
    client: TestClient, seeded: Session
) -> None:
    response = client.post("/api/orders", json=_body(NEAR_FORUM, origin_hub_id=GALERIA))

    assert response.status_code == 201
    assert response.json()["origin_hub_id"] == GALERIA


def test_an_unknown_explicit_hub_is_still_404(client: TestClient, seeded: Session) -> None:
    response = client.post("/api/orders", json=_body(NEAR_FORUM, origin_hub_id="hub-nowhere"))

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "HUB_NOT_FOUND"


def test_no_serviceable_hub_is_a_422_with_a_reason_and_creates_nothing(
    client: TestClient, seeded: Session
) -> None:
    before = _count(seeded)

    response = client.post("/api/orders", json=_body(TOO_FAR))

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "ORDER_NOT_SERVICEABLE"
    assert "No Hub can serve this order" in detail["message"]
    assert "mission distance" in detail["message"]
    assert _count(seeded) == before


def test_too_heavy_for_the_battery_is_a_422_that_names_the_heaviest_weight(
    client: TestClient, seeded: Session
) -> None:
    response = client.post("/api/orders", json=_body(LIMIT_OF_RANGE, 3.0))

    assert response.status_code == 422
    assert "2.6 kg" in response.json()["detail"]["message"]


def test_a_blank_hub_is_still_rejected(client: TestClient, seeded: Session) -> None:
    assert client.post("/api/orders", json=_body(NEAR_FORUM, origin_hub_id="")).status_code == 422


def test_editing_the_origin_hub_still_works(client: TestClient, seeded: Session) -> None:
    created = client.post("/api/orders", json=_body(NEAR_FORUM)).json()

    response = client.patch(f"/api/orders/{created['id']}", json={"origin_hub_id": OSOWA})

    assert response.status_code == 200
    assert response.json()["origin_hub_id"] == OSOWA

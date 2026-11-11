"""Database-level validation: ranges, status vocabulary and foreign keys are enforced."""

from collections.abc import Callable

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.drones.models import Drone
from app.drones.seed import build_sf1_model
from app.hubs.models import Hub

DroneFactory = Callable[..., Drone]


def test_valid_drone_is_stored(hubs_and_model: Session, make_drone: DroneFactory) -> None:
    hubs_and_model.add(make_drone())
    hubs_and_model.commit()

    stored = hubs_and_model.get(Drone, "DRN-900")
    assert stored is not None
    assert stored.model.id == "SF-1"


@pytest.mark.parametrize(
    "overrides",
    [
        {"battery_pct": -1},
        {"battery_pct": 101},
        {"status": "FLYING"},
        {"status": "idle"},
        {"longitude": 181.0},
        {"latitude": -91.0},
        {"hub_id": "hub-does-not-exist"},
        {"model_id": "SF-99"},
    ],
)
def test_invalid_drone_is_rejected(
    hubs_and_model: Session, make_drone: DroneFactory, overrides: dict[str, object]
) -> None:
    hubs_and_model.add(make_drone(**overrides))

    with pytest.raises(IntegrityError):
        hubs_and_model.commit()


def test_hub_with_drones_cannot_be_deleted(
    hubs_and_model: Session, make_drone: DroneFactory
) -> None:
    hubs_and_model.add(make_drone())
    hubs_and_model.commit()
    hub = hubs_and_model.get(Hub, "hub-forum-gdansk")
    assert hub is not None

    hubs_and_model.delete(hub)

    with pytest.raises(IntegrityError):
        hubs_and_model.commit()


def test_sf1_model_has_the_approved_specification() -> None:
    model = build_sf1_model()

    assert model.id == "SF-1"
    assert model.name == "SkyFleet SF-1 Courier"
    assert model.max_payload_kg == 3.0
    assert model.max_range_km == 20.0
    assert 12.0 <= model.recommended_mission_range_km <= 14.0
    assert model.cruise_speed_kmh == 45.0
    assert model.max_speed_kmh == 60.0
    assert 30 <= model.nominal_flight_time_min <= 35
    assert model.min_battery_reserve_pct == 20
    assert model.charge_to_80_minutes == 45
    assert model.max_wind_mps == 10.0
    assert model.empty_weight_kg == 9.0


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_payload_kg": 0.0},
        {"max_range_km": -1.0},
        {"recommended_mission_range_km": 25.0},
        {"cruise_speed_kmh": 0.0},
        {"max_speed_kmh": 40.0},
        {"nominal_flight_time_min": 0},
        {"min_battery_reserve_pct": 101},
        {"charge_to_80_minutes": 0},
        {"max_wind_mps": 0.0},
        {"empty_weight_kg": -9.0},
    ],
)
def test_invalid_model_parameters_are_rejected(
    session: Session, overrides: dict[str, float]
) -> None:
    model = build_sf1_model()
    for field, value in overrides.items():
        setattr(model, field, value)
    session.add(model)

    with pytest.raises(IntegrityError):
        session.commit()


def test_duplicate_model_name_is_rejected(session: Session) -> None:
    session.add(build_sf1_model())
    other = build_sf1_model()
    other.id = "SF-2"
    session.add(other)

    with pytest.raises(IntegrityError):
        session.commit()

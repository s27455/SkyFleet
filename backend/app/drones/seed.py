"""Idempotent, insert-only seed of the SF-1 drone model and a small deterministic fleet.

Run with `uv run python -m app.drones.seed` after `alembic upgrade head` and the Hub seed
(`uv run python -m app.hubs.seed`). Existing rows are never modified, so re-running the seed cannot
reset operational state. The SF-1 specification consists of simulation assumptions, not certified
real-world performance.

Hub capacity is checked here against the drones assigned to each Hub. Every seeded drone starts
docked at its assigned Hub, so this bounds the initial physical occupancy. At runtime a Hub's
occupancy is the number of drones physically docked there (see app/missions/presence.py).
"""

from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_engine
from app.drones.models import Drone, DroneModel, DroneStatus
from app.hubs.models import Hub
from app.hubs.seed import SEED_HUBS


class SeedError(RuntimeError):
    """Raised when the fleet cannot be seeded safely."""


SF1_MODEL_ID = "SF-1"


def build_sf1_model() -> DroneModel:
    """A fresh SF-1 Courier model row (simulation assumptions, see module docstring)."""
    return DroneModel(
        id=SF1_MODEL_ID,
        name="SkyFleet SF-1 Courier",
        airframe_type="quadcopter",
        max_payload_kg=3.0,
        max_range_km=20.0,
        recommended_mission_range_km=14.0,
        cruise_speed_kmh=45.0,
        max_speed_kmh=60.0,
        nominal_flight_time_min=32,
        min_battery_reserve_pct=20,
        charge_to_80_minutes=45,
        max_wind_mps=10.0,
        empty_weight_kg=9.0,
    )


# Three drones per Hub, with these initial battery levels.
BATTERY_LEVELS_PER_HUB: tuple[int, ...] = (100, 90, 80)


@dataclass(frozen=True)
class DroneSeed:
    id: str
    hub_id: str
    battery_pct: int


def build_fleet_plan() -> tuple[DroneSeed, ...]:
    """DRN-001.. assigned to the seeded Hubs in Hub-id order, three per Hub.

    Append-only: adding or renaming a seeded Hub would shift new numbering, so extend the fleet
    with a new plan instead of reordering this one.
    """
    hub_ids = sorted(hub.id for hub in SEED_HUBS)
    plan: list[DroneSeed] = []
    for hub_id in hub_ids:
        for battery_pct in BATTERY_LEVELS_PER_HUB:
            plan.append(DroneSeed(f"DRN-{len(plan) + 1:03d}", hub_id, battery_pct))
    return tuple(plan)


def seed_drones(session: Session) -> int:
    """Insert the SF-1 model and any missing fleet drones. Returns the number of drones inserted.

    Validates everything before writing, so a failure leaves the database unchanged.
    """
    hubs = {hub.id: hub for hub in session.scalars(select(Hub))}
    missing = sorted({seed.hub_id for seed in build_fleet_plan()} - hubs.keys())
    if missing:
        raise SeedError(
            f"Hubs not found: {', '.join(missing)}. Run `python -m app.hubs.seed` first."
        )

    existing_ids = set(session.scalars(select(Drone.id)))
    new_seeds = [seed for seed in build_fleet_plan() if seed.id not in existing_ids]

    assigned = Counter(session.scalars(select(Drone.hub_id)))
    assigned.update(seed.hub_id for seed in new_seeds)
    for hub_id, count in sorted(assigned.items()):
        if count > hubs[hub_id].drone_capacity:
            raise SeedError(
                f"Hub '{hub_id}' would have {count} assigned drones, above its capacity of "
                f"{hubs[hub_id].drone_capacity}."
            )

    if session.get(DroneModel, SF1_MODEL_ID) is None:
        session.add(build_sf1_model())
    for seed in new_seeds:
        hub = hubs[seed.hub_id]
        session.add(
            Drone(
                id=seed.id,
                model_id=SF1_MODEL_ID,
                hub_id=seed.hub_id,
                status=DroneStatus.IDLE.value,
                battery_pct=seed.battery_pct,
                longitude=hub.longitude,
                latitude=hub.latitude,
            )
        )
    session.commit()
    return len(new_seeds)


def main() -> None:
    plan_size = len(build_fleet_plan())
    with sessionmaker(bind=get_engine())() as session:
        try:
            inserted = seed_drones(session)
        except SeedError as error:
            raise SystemExit(f"Drone seed failed: {error}") from error
    print(f"Drone seed complete: {inserted} inserted, {plan_size - inserted} already present.")


if __name__ == "__main__":
    main()

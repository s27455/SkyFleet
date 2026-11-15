"""Feature 017C: organic delivery points, the operating area and planner-based feasibility."""

import math
import random
from collections import Counter

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.drones.models import Drone, DroneModel
from app.hubs.models import Hub
from app.missions.energy import estimate_energy, has_enough_battery
from app.missions.planning import evaluate_plan
from app.missions.routing import Point, distance_km, hub_point, hubs_by_distance
from app.orders.feasibility import max_flyable_weight_kg
from app.orders.generator import generate_one_order
from app.orders.locations import (
    MIN_HUB_CLEARANCE_KM,
    MIN_POINT_SEPARATION_KM,
    offset_point,
    sample_delivery,
)
from app.orders.models import MAX_PACKAGE_WEIGHT_KG, DeliveryOrder
from app.orders.operating_area import OPERATING_AREA, contains

SETTINGS = Settings()
FACTOR = SETTINGS.mission_payload_energy_factor


def _hubs(session: Session) -> list[Hub]:
    return list(session.scalars(select(Hub).order_by(Hub.id)))


def _model(session: Session) -> DroneModel:
    model = session.get(DroneModel, "SF-1")
    assert model is not None
    return model


def _bearing_deg(a: Point, b: Point) -> float:
    d_lon = math.radians(b[0] - a[0]) * math.cos(math.radians(a[1]))
    d_lat = math.radians(b[1] - a[1])
    return math.degrees(math.atan2(d_lon, d_lat)) % 360


# --- the operating area -------------------------------------------------------------------------


def test_every_hub_is_inside_the_operating_area(seeded: Session) -> None:
    for hub in _hubs(seeded):
        assert contains(hub_point(hub)), hub.id


@pytest.mark.parametrize(
    "point",
    [(18.80, 54.45), (18.68, 54.46), (18.45, 54.60), (19.50, 54.00), (18.30, 54.40)],
    ids=["bay east", "bay", "north", "far east", "west"],
)
def test_points_outside_the_area_are_rejected(point: Point) -> None:
    assert not contains(point)


def test_the_area_is_a_proper_polygon() -> None:
    assert len(OPERATING_AREA) >= 3
    assert len(set(OPERATING_AREA)) == len(OPERATING_AREA)


def test_offset_point_moves_the_requested_distance_in_any_direction() -> None:
    anchor = (18.6, 54.4)
    for bearing in (0.0, 1.0, 2.5, 4.0, 5.5):
        moved = offset_point(anchor, 2.0, bearing)
        assert distance_km(anchor, moved) == pytest.approx(2.0, rel=0.01)


# --- the sampler --------------------------------------------------------------------------------


def _sample_many(session: Session, count: int, seed: int = 11) -> list:  # type: ignore[type-arg]
    hubs = _hubs(session)
    rng = random.Random(seed)
    taken: list[Point] = []
    samples = []
    for _ in range(count):
        sample = sample_delivery(rng, hubs, taken, lambda _origin, _point: True)
        assert sample is not None
        taken.append(sample.point)
        samples.append(sample)
    return samples


def test_a_seed_gives_the_same_samples(seeded: Session) -> None:
    first = [(s.origin.id, s.point, s.style) for s in _sample_many(seeded, 30, seed=5)]
    second = [(s.origin.id, s.point, s.style) for s in _sample_many(seeded, 30, seed=5)]
    other = [(s.origin.id, s.point, s.style) for s in _sample_many(seeded, 30, seed=6)]

    assert first == second
    assert first != other


def test_samples_are_inside_the_area_clear_of_hubs_and_never_repeat(seeded: Session) -> None:
    hubs = _hubs(seeded)
    samples = _sample_many(seeded, 400)
    points = [s.point for s in samples]

    assert all(contains(p) for p in points)
    for point in points:
        assert all(distance_km(point, hub_point(h)) >= MIN_HUB_CLEARANCE_KM for h in hubs)
    assert len({(round(lon, 5), round(lat, 5)) for lon, lat in points}) == len(points)
    for i, a in enumerate(points):
        assert all(distance_km(a, b) >= MIN_POINT_SEPARATION_KM for b in points[:i])


def test_points_do_not_form_rings_or_fixed_spokes(seeded: Session) -> None:
    """Around a Hub the bearings and distances are spread out, not locked to a few values."""
    samples = [s for s in _sample_many(seeded, 800) if s.style != "cross-hub"]
    galeria = [s for s in samples if s.origin.id == "hub-galeria-baltycka"]
    bearings = [round(_bearing_deg(hub_point(s.origin), s.point) / 5) for s in galeria]
    radii = [round(distance_km(hub_point(s.origin), s.point) * 20) for s in galeria]  # 50 m bins

    assert len(galeria) > 100
    assert len(set(bearings)) >= 40  # 72 possible 5-degree bins; spokes would use a handful
    assert len(set(radii)) >= 25  # many different distances, not a few rings
    assert max(Counter(bearings).values()) <= 0.1 * len(galeria)
    assert max(Counter(radii).values()) <= 0.25 * len(galeria)


def test_the_styles_follow_the_target_mix_roughly(seeded: Session) -> None:
    samples = _sample_many(seeded, 3000)
    share = {k: v / len(samples) for k, v in Counter(s.style for s in samples).items()}

    assert 0.45 <= share["local"] <= 0.75  # target about 60 %
    assert 0.20 <= share["medium"] <= 0.40  # target about 30 %
    assert 0.04 <= share["cross-hub"] <= 0.20  # target about 10 %
    assert len({s.origin.id for s in samples}) == 4  # every Hub originates orders


def test_cross_hub_points_are_usually_nearer_to_another_hub(seeded: Session) -> None:
    hubs = _hubs(seeded)
    cross = [s for s in _sample_many(seeded, 3000) if s.style == "cross-hub"]
    nearest_elsewhere = [hubs_by_distance(s.point, hubs)[0][0].id != s.origin.id for s in cross]

    assert len(cross) > 100
    assert sum(nearest_elsewhere) / len(cross) >= 0.7


def test_the_sampler_respects_the_flyable_check_and_gives_up_cleanly(seeded: Session) -> None:
    hubs = _hubs(seeded)
    assert sample_delivery(random.Random(1), hubs, [], lambda _o, _p: False) is None
    assert sample_delivery(random.Random(1), [], [], lambda _o, _p: True) is None
    only_far = sample_delivery(
        random.Random(1), hubs, [], lambda o, p: distance_km(hub_point(o), p) > 3.0
    )
    assert only_far is None or distance_km(hub_point(only_far.origin), only_far.point) > 3.0


# --- feasibility reuses the planner's rules -------------------------------------------------------


def test_the_weight_cap_matches_the_planner_energy_rules(seeded: Session) -> None:
    hubs, model = _hubs(seeded), _model(seeded)
    galeria = next(h for h in hubs if h.id == "hub-galeria-baltycka")
    for point in [(18.597, 54.377), (18.57, 54.445), (18.68, 54.37), (18.50, 54.40)]:
        cap = max_flyable_weight_kg(galeria, point, hubs, model, FACTOR)
        outbound = distance_km(hub_point(galeria), point)
        back = hubs_by_distance(point, hubs)[0][1]

        def fits(weight: float, outbound: float = outbound, back: float = back) -> bool:
            estimate = estimate_energy(
                outbound_km=outbound,
                return_km=back,
                weight_kg=weight,
                model=model,
                payload_energy_factor=FACTOR,
            )
            return has_enough_battery(100, estimate)

        if cap is None:
            assert not fits(0.2) or outbound + back > model.recommended_mission_range_km
        else:
            assert fits(cap)
            if cap + 0.1 <= MAX_PACKAGE_WEIGHT_KG + 1e-9:
                assert not fits(round(cap + 0.1, 1))


def test_a_point_beyond_the_mission_budget_is_never_flyable(seeded: Session) -> None:
    hubs, model = _hubs(seeded), _model(seeded)
    galeria = next(h for h in hubs if h.id == "hub-galeria-baltycka")

    assert max_flyable_weight_kg(galeria, (18.70, 54.50), hubs, model, FACTOR) is None
    assert max_flyable_weight_kg(galeria, (18.5990, 54.3830), hubs, model, FACTOR) == 3.0


def test_every_generated_order_is_accepted_by_the_planner(seeded: Session) -> None:
    """A full-battery drone at the origin Hub gets an eligible plan for every generated order."""
    hubs = _hubs(seeded)
    drones = list(seeded.scalars(select(Drone)))
    full = {d.hub_id: d for d in drones if d.battery_pct == 100}
    rng = random.Random(21)

    for _ in range(120):
        order = generate_one_order(seeded, rng=rng)
        assert not order.destination_address.startswith("Delivery Point")
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
        assert plan.eligible, (order.id, [r.code for r in plan.reasons])


def test_a_batch_of_generated_orders_keeps_existing_orders(seeded: Session) -> None:
    before = {
        o.id: (o.destination_address, o.destination_longitude, o.package_weight_kg)
        for o in seeded.scalars(select(DeliveryOrder))
    }
    rng = random.Random(4)

    created = [generate_one_order(seeded, rng=rng) for _ in range(30)]

    assert len({o.destination_address for o in created}) > 5  # varied, within the 16 routes
    assert len({o.origin_hub_id for o in created}) == 4
    assert len({o.package_weight_kg for o in created}) > 5
    after = {
        o.id: (o.destination_address, o.destination_longitude, o.package_weight_kg)
        for o in seeded.scalars(select(DeliveryOrder))
    }
    assert before.items() <= after.items()  # existing orders are untouched


def test_the_generator_works_when_nothing_can_be_checked(session: Session) -> None:
    from app.hubs.seed import seed_hubs

    seed_hubs(session)  # Hubs but no drone model: the catalog needs neither

    order = generate_one_order(session, rng=random.Random(2))

    assert not order.destination_address.startswith("Delivery Point")

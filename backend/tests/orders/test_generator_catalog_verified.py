"""Verified delivery catalog (Feature 021E): official PRG records, feasibility, spread, selection.

These checks are offline: they cannot ask the PRG service, so they verify that every entry is
internally consistent (one record per entry, unique ids, address matching the locality) and that
the planner's own rules accept it. The entries themselves were copied from the PRG records.
"""

import random
import re
from collections import Counter

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.drones.models import DroneModel
from app.hubs.models import Hub
from app.missions.routing import distance_km
from app.orders import feasibility
from app.orders.generator import generate_one_order, pick_route
from app.orders.generator_catalog import ROUTE_CATALOG, CatalogRoute
from app.orders.models import DeliveryOrder
from app.orders.operating_area import contains
from app.orders.seed import SEED_ORDERS

SETTINGS = Settings()
CITIES = {"Gdańsk", "Gdynia", "Sopot"}
# The central Gdańsk districts around the old town; together they must not dominate the catalog.
OLD_TOWN = {
    ("Gdańsk", "Główne Miasto"),
    ("Gdańsk", "Stare Przedmieście"),
    ("Gdańsk", "Dolne Miasto"),
    ("Gdańsk", "Śródmieście"),
    ("Gdańsk", "Biskupia Górka"),
}
PRG_ID = re.compile(r"^ID-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
PRG_VERSION = re.compile(r"^\d{8}T\d{6}[+-]\d{4}$")


def _district(route: CatalogRoute) -> tuple[str, str]:
    return (route.city, route.district)


# --- integrity --------------------------------------------------------------------------------


def test_the_catalog_has_about_eighty_verified_points() -> None:
    assert len(ROUTE_CATALOG) >= 80


@pytest.mark.parametrize("route", ROUTE_CATALOG, ids=lambda r: r.destination_address)
def test_every_entry_is_one_complete_prg_record(route: CatalogRoute) -> None:
    assert route.prg_id is not None and PRG_ID.match(route.prg_id)
    assert route.prg_version is not None and PRG_VERSION.match(route.prg_version)
    assert route.city in CITIES
    assert route.district
    # "<street> <number>, <locality>": the locality is the entry's own PRG locality.
    street_and_number, _, locality = route.destination_address.rpartition(", ")
    assert locality == route.city
    assert re.search(r"\S \d", street_and_number), route.destination_address
    # The PRG identifier is metadata only, never part of the label operators see.
    assert route.prg_id not in route.destination_address
    assert not route.destination_address.startswith("Delivery Point")


def test_prg_ids_addresses_and_points_are_unique() -> None:
    assert len({r.prg_id for r in ROUTE_CATALOG}) == len(ROUTE_CATALOG)
    assert len({r.destination_address for r in ROUTE_CATALOG}) == len(ROUTE_CATALOG)
    assert len({(r.longitude, r.latitude) for r in ROUTE_CATALOG}) == len(ROUTE_CATALOG)


def test_no_two_points_are_on_top_of_each_other() -> None:
    points = [(r.longitude, r.latitude) for r in ROUTE_CATALOG]
    closest = min(distance_km(a, b) for i, a in enumerate(points) for b in points[i + 1 :])
    assert closest > 0.05  # more than 50 m between any two entries


def test_every_point_is_inside_the_operating_area() -> None:
    outside = [
        r.destination_address for r in ROUTE_CATALOG if not contains((r.longitude, r.latitude))
    ]
    assert outside == []


# --- feasibility ------------------------------------------------------------------------------


@pytest.mark.parametrize("route", ROUTE_CATALOG, ids=lambda r: r.destination_address)
def test_the_planner_accepts_every_route_at_both_weight_bounds(
    route: CatalogRoute, seeded: Session
) -> None:
    hubs = list(seeded.scalars(select(Hub)))
    model = seeded.get(DroneModel, "SF-1")
    assert model is not None
    origin = next(hub for hub in hubs if hub.id == route.origin_hub_id)
    destination = (route.longitude, route.latitude)
    factor = SETTINGS.mission_payload_energy_factor

    for weight in (route.min_weight_kg, route.max_weight_kg):
        problem = feasibility.route_problem(origin, destination, weight, hubs, model, factor)
        assert problem is None, f"{route.destination_address} at {weight} kg: {problem}"
    # The origin is the Hub the planner itself would choose, and the heaviest parcel fits.
    chosen, _ = feasibility.choose_origin_hub(hubs, model, destination, route.min_weight_kg, factor)
    assert chosen is not None and chosen.id == route.origin_hub_id
    cap = feasibility.max_flyable_weight_kg(origin, destination, hubs, model, factor)
    assert cap is not None and route.max_weight_kg <= cap
    assert route.max_weight_kg >= 0.5


# --- geographic distribution ------------------------------------------------------------------


def test_the_catalog_covers_all_three_cities_and_every_hub(seeded: Session) -> None:
    by_city = Counter(r.city for r in ROUTE_CATALOG)
    assert set(by_city) == CITIES
    assert by_city["Gdańsk"] > by_city["Gdynia"] > by_city["Sopot"] >= 3
    by_hub = Counter(r.origin_hub_id for r in ROUTE_CATALOG)
    assert set(by_hub) == set(seeded.scalars(select(Hub.id)))
    assert min(by_hub.values()) >= 8


def test_many_districts_and_no_old_town_concentration() -> None:
    by_district = Counter(_district(r) for r in ROUTE_CATALOG)
    assert len(by_district) >= 30
    assert max(by_district.values()) <= 4
    old_town = sum(count for district, count in by_district.items() if district in OLD_TOWN)
    assert old_town / len(ROUTE_CATALOG) <= 0.10


# --- selection --------------------------------------------------------------------------------


def _route(district: str, number: int) -> CatalogRoute:
    return CatalogRoute(
        "hub-forum-gdansk",
        f"ul. Testowa {number}, Gdańsk",
        18.6 + number / 1000,
        54.35,
        0.2,
        1.0,
        "Gdańsk",
        district,
    )


def test_a_district_is_chosen_before_a_route_so_a_crowded_district_does_not_dominate() -> None:
    crowded = [_route("Crowded", n) for n in range(20)]
    routes = [*crowded, _route("Quiet A", 100), _route("Quiet B", 101)]
    rng = random.Random(7)

    picks = Counter(pick_route(routes, rng).district for _ in range(3000))

    # Each of the three districts is about one third, although "Crowded" has 20 of 22 routes.
    for district in ("Crowded", "Quiet A", "Quiet B"):
        assert 800 < picks[district] < 1200


def test_selection_is_reproducible_for_a_seed() -> None:
    first = [pick_route(ROUTE_CATALOG, random.Random(11)) for _ in range(5)]
    second = [pick_route(ROUTE_CATALOG, random.Random(11)) for _ in range(5)]
    assert first == second


def test_real_catalog_picks_stay_spread_over_the_districts() -> None:
    rng = random.Random(3)
    picks = [pick_route(ROUTE_CATALOG, rng) for _ in range(2000)]

    old_town = sum(1 for r in picks if _district(r) in OLD_TOWN)
    assert old_town / len(picks) < 0.2
    assert len({_district(r) for r in picks}) >= 30
    assert {r.city for r in picks} == CITIES


def test_generation_prefers_a_district_that_still_has_a_free_route(seeded: Session) -> None:
    rng = random.Random(5)
    orders = [generate_one_order(seeded, rng=rng) for _ in range(30)]

    districts = {
        next(r for r in ROUTE_CATALOG if r.destination_address == o.destination_address).district
        for o in orders
    }
    assert len(districts) >= 15  # 30 orders, no small cluster repeated


# --- existing orders --------------------------------------------------------------------------


def test_replacing_the_catalog_never_rewrites_existing_orders(seeded: Session) -> None:
    for seed in range(5):
        generate_one_order(seeded, rng=random.Random(seed))

    for seed_order in SEED_ORDERS:
        stored = seeded.get(DeliveryOrder, seed_order.id)
        assert stored is not None
        assert stored.destination_address == seed_order.destination_address
        assert (stored.destination_longitude, stored.destination_latitude) == (
            seed_order.longitude,
            seed_order.latitude,
        )
        assert stored.origin_hub_id == seed_order.origin_hub_id
        assert stored.package_weight_kg == seed_order.package_weight_kg

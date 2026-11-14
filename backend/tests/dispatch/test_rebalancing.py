"""Automatic fleet rebalancing inside the Auto Dispatch pass (Feature 019B), on SQLite.

Seeded drones: DRN-001..003 Osowa, 004..006 Riviera, 007..009 Forum, 010..012 Bałtycka, batteries
100, 90 and 80 per Hub. The helpers below rebuild the orders and batteries so each test states its
own scenario.
"""

from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.dispatch import auto
from app.dispatch.rebalancing import (
    Transfer,
    _cooling_pairs,
    plan_transfer,
    run_rebalancing,
    select_transfer,
)
from app.dispatch.service import active_claims, recommend_for_session
from app.drones import repository as drone_repository
from app.drones.models import Drone
from app.events.models import EventOrigin, OperationalEvent
from app.missions import repository as mission_repository
from app.missions.models import Mission, MissionPurpose
from app.orders.models import DeliveryOrder
from app.simulation.heartbeat import record_heartbeat
from app.simulation.relocation import start_relocation

NOW = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
BALTYCKA, FORUM, OSOWA, RIVIERA = (
    "hub-galeria-baltycka",
    "hub-forum-gdansk",
    "hub-centrum-handlowe-osowa",
    "hub-centrum-riviera",
)
Factory = sessionmaker[Session]
MakeOrder = Callable[..., DeliveryOrder]


def battery(session: Session, **levels: int) -> None:
    for drone_id, pct in levels.items():
        drone = session.get(Drone, drone_id.replace("_", "-").upper())
        assert drone is not None
        drone.battery_pct = pct
    session.commit()


def only_orders(session: Session, make_order: MakeOrder, **per_hub: int) -> None:
    """Replace every order by `n` waiting orders at each given Hub (keyword = Hub, uppercase)."""
    session.execute(delete(DeliveryOrder))
    hubs = {"BALTYCKA": BALTYCKA, "FORUM": FORUM, "OSOWA": OSOWA, "RIVIERA": RIVIERA}
    number = 0
    for name, count in per_hub.items():
        for _ in range(count):
            number += 1
            session.add(
                make_order(
                    id=f"ORD-{number:03d}",
                    origin_hub_id=hubs[name],
                    created_at=NOW + timedelta(seconds=number),
                )
            )
    session.commit()


def decide(session: Session, settings: Settings, now: datetime = NOW) -> Transfer | None:
    session.expire_all()
    return select_transfer(session, settings, now)


def relocations(session: Session) -> list[Mission]:
    session.expire_all()
    return list(
        session.scalars(select(Mission).where(Mission.purpose == MissionPurpose.RELOCATION.value))
    )


def turn_on(factory: Factory, settings: Settings) -> None:
    with factory() as session:
        auto.enable(session, NOW, settings)


def shortage_at_forum(session: Session, make_order: MakeOrder, orders: int = 1) -> None:
    """Forum has waiting orders and no 100% drone; Bałtycka has two (DRN-010 and DRN-011)."""
    battery(session, drn_007=50, drn_010=100, drn_011=100, drn_012=80)
    only_orders(session, make_order, FORUM=orders)


# --- policy -----------------------------------------------------------------------------------


def test_no_demand_means_no_transfer(
    seeded: Session, make_order: MakeOrder, sim_settings: Settings
) -> None:
    battery(seeded, drn_010=100, drn_011=100)
    only_orders(seeded, make_order)  # no orders at all

    assert decide(seeded, sim_settings) is None


def test_a_hub_without_a_free_drone_gets_one_from_a_hub_with_a_spare(
    seeded: Session, make_order: MakeOrder, sim_settings: Settings
) -> None:
    shortage_at_forum(seeded, make_order)

    transfer = decide(seeded, sim_settings)

    assert transfer is not None
    assert (transfer.drone_id, transfer.source_hub_id, transfer.destination_hub_id) == (
        "DRN-010",
        BALTYCKA,
        FORUM,
    )
    assert "queued order(s) and no available drone" in transfer.reason


def test_a_hub_with_its_own_free_drone_is_not_in_shortage(
    seeded: Session, make_order: MakeOrder, sim_settings: Settings
) -> None:
    battery(seeded, drn_010=100, drn_011=100)  # Forum keeps DRN-007 at 100%
    only_orders(seeded, make_order, FORUM=1)

    assert decide(seeded, sim_settings) is None


def test_the_last_free_drone_of_a_hub_is_never_taken(
    seeded: Session, make_order: MakeOrder, sim_settings: Settings
) -> None:
    shortage_at_forum(seeded, make_order)
    battery(seeded, drn_011=90)  # Bałtycka is left with one free drone

    assert decide(seeded, sim_settings) is None


def test_a_donor_keeps_the_drones_its_own_queue_needs(
    seeded: Session, make_order: MakeOrder, sim_settings: Settings
) -> None:
    battery(seeded, drn_007=50, drn_010=100, drn_011=100)
    only_orders(seeded, make_order, FORUM=1, BALTYCKA=1)
    transfer = decide(seeded, sim_settings)
    assert transfer is not None  # one drone serves Bałtycka's order, one is spare

    only_orders(seeded, make_order, FORUM=1, BALTYCKA=2)
    assert decide(seeded, sim_settings) is None  # both drones are needed at home


def test_an_order_the_planner_rejects_is_not_demand(
    seeded: Session, make_order: MakeOrder, sim_settings: Settings
) -> None:
    battery(seeded, drn_010=100, drn_011=100)
    seeded.execute(delete(DeliveryOrder))
    seeded.add(make_order(id="ORD-001", destination_longitude=19.9))  # far beyond any range
    seeded.commit()

    result = recommend_for_session(seeded, sim_settings)
    assert [p.reason for p in result.pending] == ["PLANNER_REJECTED"]
    assert decide(seeded, sim_settings) is None


def test_the_most_demanding_hub_first_then_the_lower_hub_id(
    seeded: Session, make_order: MakeOrder, sim_settings: Settings
) -> None:
    battery(seeded, drn_001=50, drn_007=50, drn_010=100, drn_011=100)
    only_orders(seeded, make_order, OSOWA=1, FORUM=2)
    transfer = decide(seeded, sim_settings)
    assert transfer is not None and transfer.destination_hub_id == FORUM

    only_orders(seeded, make_order, OSOWA=1, FORUM=1)
    transfer = decide(seeded, sim_settings)
    assert transfer is not None and transfer.destination_hub_id == OSOWA  # lower id on a tie


def test_a_hub_too_far_for_the_source_is_skipped_for_the_next_one(
    seeded: Session, make_order: MakeOrder, sim_settings: Settings
) -> None:
    # Riviera is over the 14 km budget from Bałtycka, so the only feasible demand is Forum.
    battery(seeded, drn_004=50, drn_007=50, drn_010=100, drn_011=100)
    only_orders(seeded, make_order, RIVIERA=2, FORUM=1)

    transfer = decide(seeded, sim_settings)

    assert transfer is not None and transfer.destination_hub_id == FORUM


def test_the_shortest_transfer_wins(
    seeded: Session, make_order: MakeOrder, sim_settings: Settings
) -> None:
    # Two donors for Forum: Osowa and Bałtycka; Bałtycka is the closer one.
    battery(seeded, drn_001=100, drn_002=100, drn_007=50, drn_010=100, drn_011=100)
    only_orders(seeded, make_order, FORUM=1)

    transfer = decide(seeded, sim_settings)

    assert transfer is not None and transfer.source_hub_id == BALTYCKA


def test_a_relocation_already_on_its_way_counts_as_supply(
    seeded: Session, make_order: MakeOrder, sim_settings: Settings
) -> None:
    shortage_at_forum(seeded, make_order, orders=1)
    record_heartbeat(seeded, NOW)
    start_relocation(seeded, "DRN-012", FORUM, NOW, sim_settings)  # manual, 80% is enough

    assert decide(seeded, sim_settings) is None  # one order, one drone coming

    only_orders(seeded, make_order, FORUM=2)
    after_cooldown = NOW + timedelta(seconds=sim_settings.rebalance_pair_cooldown_seconds + 1)
    transfer = decide(seeded, sim_settings, after_cooldown)
    assert transfer is not None and transfer.destination_hub_id == FORUM  # one still unserved


def test_a_pair_is_left_alone_within_the_cooldown_in_either_direction(
    seeded: Session, make_order: MakeOrder, sim_settings: Settings
) -> None:
    shortage_at_forum(seeded, make_order)
    record_heartbeat(seeded, NOW)
    start_relocation(seeded, "DRN-012", FORUM, NOW, sim_settings)
    cooldown = timedelta(seconds=sim_settings.rebalance_pair_cooldown_seconds)

    assert _cooling_pairs(seeded, NOW + cooldown - timedelta(seconds=1), sim_settings) == {
        frozenset((BALTYCKA, FORUM))
    }
    assert _cooling_pairs(seeded, NOW + cooldown + timedelta(seconds=1), sim_settings) == set()


def test_plan_transfer_skips_a_cooling_pair(
    seeded: Session, make_order: MakeOrder, sim_settings: Settings
) -> None:
    shortage_at_forum(seeded, make_order)
    _, active_drones = active_claims(seeded)

    def plan(cooling: set[frozenset[str]]) -> Transfer | None:
        return plan_transfer(
            result=recommend_for_session(seeded, sim_settings),
            drones=drone_repository.list_drones(seeded),
            hubs=mission_repository.list_hubs(seeded),
            active_drone_ids=active_drones,
            incoming=Counter(),
            cooling_pairs=cooling,
            dock_proximity_m=sim_settings.hub_dock_proximity_m,
        )

    assert plan(set()) is not None
    assert plan({frozenset((FORUM, BALTYCKA))}) is None  # reverse direction counts too


# --- inside the Auto Dispatch pass --------------------------------------------------------------


def test_with_auto_dispatch_off_nothing_is_relocated(
    seeded: Session, session_factory: Factory, make_order: MakeOrder, sim_settings: Settings
) -> None:
    shortage_at_forum(seeded, make_order)
    record_heartbeat(seeded, NOW)

    for _ in range(3):
        assert auto.run_dispatch_pass(session_factory, sim_settings, NOW) is None

    assert relocations(seeded) == []


def test_a_pass_starts_one_automatic_relocation_and_explains_it(
    seeded: Session, session_factory: Factory, make_order: MakeOrder, sim_settings: Settings
) -> None:
    shortage_at_forum(seeded, make_order)
    record_heartbeat(seeded, NOW)
    turn_on(session_factory, sim_settings)
    orders_before = seeded.scalar(select(DeliveryOrder.id).limit(1))

    outcome = auto.run_dispatch_pass(session_factory, sim_settings, NOW)

    assert outcome is not None and "Relocating DRN-010" in outcome
    [mission] = relocations(seeded)
    assert (mission.drone_id, mission.origin_hub_id, mission.return_hub_id) == (
        "DRN-010",
        BALTYCKA,
        FORUM,
    )
    assert mission.order_id is None  # no fake order
    assert seeded.scalar(select(DeliveryOrder.id).limit(1)) == orders_before
    event = seeded.scalars(
        select(OperationalEvent).where(OperationalEvent.mission_id == mission.id)
    ).one()
    assert event.origin == EventOrigin.AUTOMATIC.value
    assert event.reason is not None and "automatic rebalancing" in event.reason
    assert "no available drone" in event.reason
    drone = seeded.get(Drone, "DRN-010")
    assert drone is not None and drone.hub_id == BALTYCKA  # the Hub changes only on landing


def test_repeated_passes_and_a_restart_never_send_a_second_drone(
    seeded: Session, session_factory: Factory, make_order: MakeOrder, sim_settings: Settings
) -> None:
    shortage_at_forum(seeded, make_order, orders=1)
    record_heartbeat(seeded, NOW)
    turn_on(session_factory, sim_settings)

    for second in range(5):
        auto.run_dispatch_pass(session_factory, sim_settings, NOW + timedelta(seconds=second))
    assert len(relocations(seeded)) == 1

    # Even with more demand, the pair is cooling down, so there is no back-and-forth or second hop.
    only_orders(seeded, make_order, FORUM=3)
    auto.run_dispatch_pass(session_factory, sim_settings, NOW + timedelta(seconds=10))
    assert len(relocations(seeded)) == 1

    # A restarted worker resets the mode to OFF and reads the cooldown from the stored flights.
    with session_factory() as session:
        auto.reset_to_off(session, NOW + timedelta(seconds=20))
    assert auto.run_dispatch_pass(session_factory, sim_settings, NOW) is None
    turn_on(session_factory, sim_settings)
    auto.run_dispatch_pass(session_factory, sim_settings, NOW + timedelta(seconds=30))
    assert len(relocations(seeded)) == 1


def test_turning_the_mode_off_stops_a_transfer_that_was_not_yet_started(
    seeded: Session, session_factory: Factory, make_order: MakeOrder, sim_settings: Settings
) -> None:
    shortage_at_forum(seeded, make_order)
    record_heartbeat(seeded, NOW)

    assert run_rebalancing(session_factory, sim_settings, NOW, lambda: False) is None

    assert relocations(seeded) == []


def test_a_stale_worker_or_a_changed_state_is_quiet_not_an_error(
    seeded: Session, session_factory: Factory, make_order: MakeOrder, sim_settings: Settings
) -> None:
    shortage_at_forum(seeded, make_order)  # no heartbeat: start_relocation refuses

    assert run_rebalancing(session_factory, sim_settings, NOW, lambda: True) is None

    assert relocations(seeded) == []


def test_manual_relocation_does_not_depend_on_auto_dispatch(
    seeded: Session, sim_settings: Settings
) -> None:
    record_heartbeat(seeded, NOW)  # the mode is OFF (no row at all)

    mission = start_relocation(seeded, "DRN-010", FORUM, NOW, sim_settings)

    assert mission.purpose == MissionPurpose.RELOCATION.value

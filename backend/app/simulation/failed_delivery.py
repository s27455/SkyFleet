"""Recipient unavailable incident (Feature 018D): the one backend behavior behind every trigger.

`trigger_recipient_unavailable` is what the manual control calls today and what a future automatic
trigger will call: one request, the backend chooses an eligible delivery, stores the *pending*
outcome and returns, or reports `NoEligibleTargetError` and changes nothing.

The trigger only stamps `mission_flights.recipient_unavailable_at`. Nothing else changes: the
drone keeps its route and reaches the destination. At the delivery milestone the simulation engine
(`engine._fail_handover`) turns the pending outcome into the real one: the order becomes
DELIVERY_FAILED, the drone flies back loaded to the nearest reachable Hub, and the one
`RECIPIENT_UNAVAILABLE` event is written. The event is therefore recorded at the failed handover,
never at the trigger, so the timeline cannot claim a failure that has not happened.

Eligible: an OUTBOUND or DELIVERING flight of an OUT_FOR_DELIVERY order, with an IN_FLIGHT mission
and drone, that is not recalled (018B), failed (018C) or already pending, whose delivery milestone
the worker has not reached yet, and from whose destination a Hub is reachable with the parcel
(missions keep a battery reserve, so this is a defensive check). Locks are taken in the engine's
order (flight, mission, order, drone); a candidate that changed in the meantime is skipped.
"""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.clock import as_utc
from app.config import Settings
from app.drones.models import Drone, DroneStatus
from app.events.models import EventOrigin
from app.missions import repository as mission_repository
from app.missions.energy import consumption_rates
from app.missions.models import Mission, MissionStatus
from app.missions.routing import nearest_reachable_hub
from app.orders.models import DeliveryOrder, OrderStatus
from app.simulation.failure import NoEligibleTargetError
from app.simulation.flight import delivery_leg, leg_from_dict, state_at
from app.simulation.models import FlightPhase, MissionFlight

ELIGIBLE_PHASES: tuple[str, ...] = (FlightPhase.OUTBOUND.value, FlightPhase.DELIVERING.value)

_rng = random.Random()


@dataclass(frozen=True)
class RecipientUnavailableResult:
    drone_id: str
    mission_id: str
    order_id: str
    attempt_at: datetime  # when the drone reaches the destination: the failure becomes real


def eligible_mission_ids(session: Session) -> list[str]:
    """Mission ids of the flights that look eligible, in id order (rechecked under locks)."""
    statement = (
        select(MissionFlight.mission_id)
        .join(Mission, Mission.id == MissionFlight.mission_id)
        .join(Drone, Drone.id == Mission.drone_id)
        .join(DeliveryOrder, DeliveryOrder.id == Mission.order_id)
        .where(
            MissionFlight.phase.in_(ELIGIBLE_PHASES),
            MissionFlight.failed_at.is_(None),
            MissionFlight.recalled_at.is_(None),
            MissionFlight.delivered_at.is_(None),
            MissionFlight.recipient_unavailable_at.is_(None),
            Mission.status == MissionStatus.IN_FLIGHT.value,
            Drone.status == DroneStatus.IN_FLIGHT.value,
            DeliveryOrder.status == OrderStatus.OUT_FOR_DELIVERY.value,
        )
        .order_by(MissionFlight.mission_id)
    )
    return list(session.scalars(statement))


def trigger_recipient_unavailable(
    session: Session,
    now: datetime,
    settings: Settings,
    *,
    origin: EventOrigin = EventOrigin.MANUAL,
    rng: random.Random | None = None,
) -> RecipientUnavailableResult:
    """Mark one eligible delivery; raises `NoEligibleTargetError`, changing nothing, if none."""
    chooser = rng or _rng
    candidates = eligible_mission_ids(session)
    session.rollback()  # end the read transaction; each candidate is rechecked under its locks
    chooser.shuffle(candidates)
    for mission_id in candidates:
        result = _mark_flight(session, mission_id, now, settings, origin)
        if result is not None:
            return result
    raise NoEligibleTargetError(
        "No drone is on its way to a delivery that could still fail at the handover"
    )


def _mark_flight(
    session: Session, mission_id: str, now: datetime, settings: Settings, origin: EventOrigin
) -> RecipientUnavailableResult | None:
    try:
        flight = session.scalars(
            select(MissionFlight)
            .where(MissionFlight.mission_id == mission_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one_or_none()
        mission = mission_repository.get_mission_for_update(session, mission_id)
        if flight is None or mission is None or mission.order_id is None:
            session.rollback()
            return None  # a relocation (Feature 019A) has no delivery to fail
        order = mission_repository.get_order(session, mission.order_id, lock=True)
        drone = mission_repository.get_drone(session, mission.drone_id, lock=True)
        if order is None or drone is None:
            session.rollback()
            return None
        if (
            flight.phase not in ELIGIBLE_PHASES
            or flight.failed_at is not None
            or flight.recalled_at is not None
            or flight.delivered_at is not None
            or flight.recipient_unavailable_at is not None
            or mission.status != MissionStatus.IN_FLIGHT.value
            or drone.status != DroneStatus.IN_FLIGHT.value
            or order.status != OrderStatus.OUT_FOR_DELIVERY.value
        ):
            session.rollback()
            return None  # it changed since the candidate list was read

        started = as_utc(flight.started_at)
        elapsed = max((now - started).total_seconds(), 0.0)
        legs = [leg_from_dict(entry) for entry in flight.legs]
        stop = delivery_leg(legs)
        if stop is None:
            session.rollback()
            return None  # no delivery stop left in this schedule
        attempt_s = stop.end_s
        if elapsed >= attempt_s:
            session.rollback()
            return None  # the worker is about to deliver; leave this flight to it

        empty, loaded = consumption_rates(
            weight_kg=order.package_weight_kg,
            model=drone.model,
            payload_energy_factor=settings.mission_payload_energy_factor,
        )
        at_stop = state_at(
            legs,
            attempt_s,
            start_battery=flight.start_battery_pct,
            empty_rate=empty,
            loaded_rate=loaded,
        )
        hubs = list(mission_repository.list_hubs(session))
        if (
            nearest_reachable_hub(
                stop.target,
                hubs,
                at_stop.battery_pct,
                loaded,
                settings.sim_critical_battery_pct,
            )
            is None
        ):
            session.rollback()
            return None  # no Hub is reachable with the parcel: never start a failed delivery

        flight.recipient_unavailable_at = now
        flight.recipient_unavailable_origin = origin.value
        session.commit()
        return RecipientUnavailableResult(
            drone_id=drone.id,
            mission_id=mission.id,
            order_id=order.id,
            attempt_at=started + timedelta(seconds=attempt_s),
        )
    except BaseException:
        session.rollback()
        raise

"""Order cancellation and drone recall (Feature 018B).

Cancellation is a business transition, not deletion: the order stays in the database with the
`CANCELLED` status, a `cancelled_at` time and an `ORDER_CANCELLED` event, all in one transaction.

What happens depends on how far the order got (checked under row locks, nothing partially applied):

* no active mission (`CREATED`, `AWAITING_HANDOVER`, `READY_FOR_PICKUP`): the order is cancelled;
* an `ASSIGNED` mission (not airborne): the mission is cancelled too, which releases the drone;
* an in-flight mission whose parcel has not been handed over: the order is cancelled and the drone
  is recalled. The flight's remaining legs are replaced by one loaded RECALL leg to the nearest
  reachable Hub, so the drone keeps flying from where it is (no teleport) and the simulation
  engine lands it with the normal landing logic, using the loaded consumption rate. The mission
  stays `IN_FLIGHT` until it lands; `drone.hub_id` changes only then (Feature 017C);
* `DELIVERED`: rejected, history is never rewritten;
* already `CANCELLED`: idempotent, the current order is returned and nothing else happens.

Cancellation never changes a drone's health: a drone that is not flying normally is not recalled.
Locks are taken in the engine's order (flight, mission, order, drone) so a cancel, a worker tick
and a takeoff cannot deadlock. A cancel that finds a mission it did not lock the flight for
(takeoff just committed) starts over with the flight lock first.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.drones.models import Drone, DroneStatus
from app.events.models import EventOrigin, EventType
from app.events.service import append_event
from app.hubs.models import Hub
from app.missions import repository as mission_repository
from app.missions.energy import consumption_rates
from app.missions.models import ACTIVE_MISSION_STATUSES, Mission, MissionStatus
from app.missions.routing import hub_point, hubs_by_distance
from app.orders import repository
from app.orders.models import DeliveryOrder, OrderStatus
from app.orders.service import OrderManagementError, OrderNotFoundError
from app.simulation.clock import as_utc
from app.simulation.engine import write_snapshot
from app.simulation.flight import leg_from_dict, leg_to_dict, recall_legs, state_at
from app.simulation.models import FlightPhase, MissionFlight

MAX_ATTEMPTS = 3

_PRE_FLIGHT = (
    OrderStatus.CREATED.value,
    OrderStatus.AWAITING_HANDOVER.value,
    OrderStatus.READY_FOR_PICKUP.value,
)
_ACTIVE = [status.value for status in ACTIVE_MISSION_STATUSES]


class OrderAlreadyDeliveredError(OrderManagementError):
    def __init__(self, order_id: str) -> None:
        super().__init__(f"Order '{order_id}' is already delivered and cannot be cancelled")


class OrderNotCancellableError(OrderManagementError):
    def __init__(self, order_id: str, status: str) -> None:
        super().__init__(f"Order '{order_id}' is {status} and cannot be cancelled in this state")


class DroneNotRecallableError(OrderManagementError):
    def __init__(self, order_id: str, drone_id: str) -> None:
        super().__init__(
            f"The delivery of order '{order_id}' cannot be recalled: drone '{drone_id}' is not "
            "flying normally; its state is left unchanged"
        )


class RecallNotPossibleError(OrderManagementError):
    """Defensive only: planned missions keep a reserve, so a reachable Hub is expected."""

    def __init__(self, order_id: str) -> None:
        super().__init__(
            f"Order '{order_id}' was not cancelled: no Hub is reachable for the recall; "
            "nothing was changed"
        )


class _RetryError(Exception):
    """The locks were taken in the wrong order for the state found; start over."""


def cancel_order(
    session: Session, order_id: str, now: datetime, settings: Settings
) -> DeliveryOrder:
    """Cancel an order, recalling its drone if it is flying with the parcel. Idempotent."""
    for _ in range(MAX_ATTEMPTS):
        try:
            return _cancel_once(session, order_id, now, settings)
        except _RetryError:
            continue
    raise OrderManagementError(f"Order '{order_id}' could not be cancelled; try again")


def _active_mission_id(session: Session, order_id: str) -> str | None:
    statement = select(Mission.id).where(Mission.order_id == order_id, Mission.status.in_(_ACTIVE))
    return session.scalars(statement.limit(1)).first()


def _cancel_once(
    session: Session, order_id: str, now: datetime, settings: Settings
) -> DeliveryOrder:
    try:
        peek = repository.get_order(session, order_id)
        if peek is None:
            raise OrderNotFoundError(order_id)
        mission_id = _active_mission_id(session, order_id)
        session.rollback()  # end the read transaction; everything is re-read under the locks

        flight: MissionFlight | None = None
        if mission_id is not None:
            flight = session.scalars(
                select(MissionFlight)
                .where(MissionFlight.mission_id == mission_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ).one_or_none()
        mission = (
            mission_repository.get_mission_for_update(session, mission_id) if mission_id else None
        )
        order = mission_repository.get_order(session, order_id, lock=True)
        if order is None:
            raise OrderNotFoundError(order_id)

        if order.status == OrderStatus.CANCELLED.value:
            session.rollback()
            return order  # idempotent: no second event, no second recall
        if order.status == OrderStatus.DELIVERED.value:
            raise OrderAlreadyDeliveredError(order_id)

        if mission is None:
            if _active_mission_id(session, order_id) is not None:
                raise _RetryError  # a mission was created after the first look
            if order.status not in _PRE_FLIGHT:
                raise OrderNotCancellableError(order_id, order.status)
            _cancel_order(session, order, now)
            append_event(
                session,
                event_type=EventType.ORDER_CANCELLED,
                origin=EventOrigin.MANUAL,
                order_id=order.id,
                reason="Order cancelled before dispatch",
                dedupe_key=f"{EventType.ORDER_CANCELLED.value}:{order.id}",
                occurred_at=now,
            )
            session.commit()
            return order

        drone = mission_repository.get_drone(session, mission.drone_id, lock=True)
        if drone is None:
            raise OrderNotCancellableError(order_id, order.status)

        if mission.status == MissionStatus.ASSIGNED.value and flight is None:
            mission.status = MissionStatus.CANCELLED.value
            mission.updated_at = now
            _cancel_order(session, order, now)
            append_event(
                session,
                event_type=EventType.ORDER_CANCELLED,
                origin=EventOrigin.MANUAL,
                order_id=order.id,
                mission_id=mission.id,
                drone_id=drone.id,
                reason=f"Order cancelled before takeoff; mission {mission.id} cancelled",
                dedupe_key=f"{EventType.ORDER_CANCELLED.value}:{order.id}",
                occurred_at=now,
            )
            session.commit()
            return order

        if mission.status != MissionStatus.IN_FLIGHT.value:
            raise OrderNotCancellableError(order_id, order.status)
        if flight is None:
            raise _RetryError  # takeoff committed between the first look and the locks
        _recall(session, settings, order, mission, flight, drone, now)
        session.commit()
        return order
    except BaseException:
        session.rollback()
        raise


def _cancel_order(session: Session, order: DeliveryOrder, now: datetime) -> None:
    order.status = OrderStatus.CANCELLED.value
    order.cancelled_at = now
    order.updated_at = now


def _recall(
    session: Session,
    settings: Settings,
    order: DeliveryOrder,
    mission: Mission,
    flight: MissionFlight,
    drone: Drone,
    now: datetime,
) -> None:
    started = as_utc(flight.started_at)
    elapsed = max((now - started).total_seconds(), 0.0)
    legs = [leg_from_dict(entry) for entry in flight.legs]
    already_handed_over = flight.delivered_at is not None or elapsed >= legs[1].end_s
    if already_handed_over:
        raise OrderAlreadyDeliveredError(order.id)  # the next tick delivers it; do not race it
    if (
        flight.recalled_at is not None
        or flight.phase not in (FlightPhase.OUTBOUND.value, FlightPhase.DELIVERING.value)
        or order.status != OrderStatus.OUT_FOR_DELIVERY.value
        or drone.status != DroneStatus.IN_FLIGHT.value
    ):
        raise DroneNotRecallableError(order.id, drone.id)

    empty, loaded = consumption_rates(
        weight_kg=order.package_weight_kg,
        model=drone.model,
        payload_energy_factor=settings.mission_payload_energy_factor,
    )
    here = state_at(
        legs, elapsed, start_battery=flight.start_battery_pct, empty_rate=empty, loaded_rate=loaded
    )
    hubs: list[Hub] = list(mission_repository.list_hubs(session))
    # The parcel is still on board, so the loaded rate decides what is reachable.
    reachable = [
        (hub, km)
        for hub, km in hubs_by_distance(here.position, hubs)
        if here.battery_pct - loaded * km >= settings.sim_critical_battery_pct
    ]
    if not reachable:
        raise RecallNotPossibleError(order.id)
    target, _ = reachable[0]

    new_legs = recall_legs(legs, elapsed, here.position, hub_point(target), flight.pace_s_per_km)
    flight.legs = [leg_to_dict(leg) for leg in new_legs]
    flight.recalled_at = now
    flight.landing_target_hub_id = target.id
    flight.tried_hub_ids = []
    write_snapshot(
        flight,
        drone,
        state_at(
            new_legs,
            elapsed,
            start_battery=flight.start_battery_pct,
            empty_rate=empty,
            loaded_rate=loaded,
        ),
        now,
    )
    _cancel_order(session, order, now)
    append_event(
        session,
        event_type=EventType.ORDER_CANCELLED,
        origin=EventOrigin.MANUAL,
        order_id=order.id,
        mission_id=mission.id,
        flight_id=flight.mission_id,
        drone_id=drone.id,
        reason=f"Order cancelled in flight; drone {drone.id} recalled to {target.name} with parcel",
        details={"recall_hub_id": target.id},
        dedupe_key=f"{EventType.ORDER_CANCELLED.value}:{order.id}",
        occurred_at=now,
    )

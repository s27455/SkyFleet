"""Mission use cases: read-only preview, confirmation and cancellation.

Confirmation and cancellation run in one transaction each. Confirmation locks the order row and
then the drone row (a fixed order, so concurrent confirmations cannot deadlock), recomputes the plan
with the same rules as the preview, and inserts the mission. The partial unique indexes on
`missions` are the final guarantee against two active missions for one order or one drone. There
are no Hub locks and no capacity reservations: Hub occupancy is physical presence only.

Planning, confirmation and cancellation never write the order, the drone or any Hub.
"""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.drones.models import Drone
from app.missions import repository
from app.missions.models import Mission, MissionStatus, new_mission_id
from app.missions.planning import evaluate_plan
from app.missions.schemas import PlanResponse
from app.orders.models import DeliveryOrder

MAX_ID_ATTEMPTS = 5


class MissionError(Exception):
    """Base class for expected mission use-case failures."""


class OrderNotFoundError(MissionError):
    def __init__(self, order_id: str) -> None:
        super().__init__(f"Order '{order_id}' not found")


class DroneNotFoundError(MissionError):
    def __init__(self, drone_id: str) -> None:
        super().__init__(f"Drone '{drone_id}' not found")


class MissionNotFoundError(MissionError):
    def __init__(self, mission_id: str) -> None:
        super().__init__(f"Mission '{mission_id}' not found")


class PlanRejectedError(MissionError):
    """The order and drone cannot be assigned; `plan` lists every reason."""

    def __init__(self, plan: PlanResponse) -> None:
        super().__init__("The order and drone cannot be assigned")
        self.plan = plan


class MissionNotCancellableError(MissionError):
    def __init__(self, mission_id: str, status: str) -> None:
        super().__init__(
            f"Mission '{mission_id}' is {status}; only ASSIGNED missions can be cancelled"
        )
        self.status = status


class _IdCollisionError(Exception):
    """A generated mission id already exists (astronomically rare); retry with a new id."""


def _plan(session: Session, order: DeliveryOrder, drone: Drone, settings: Settings) -> PlanResponse:
    return evaluate_plan(
        order=order,
        drone=drone,
        hubs=repository.list_hubs(session),
        drones=repository.list_drones(session),
        order_has_active_mission=repository.order_has_active_mission(session, order.id),
        drone_has_active_mission=repository.drone_has_active_mission(session, drone.id),
        payload_energy_factor=settings.mission_payload_energy_factor,
        dock_proximity_m=settings.hub_dock_proximity_m,
    )


def _load(
    session: Session, order_id: str, drone_id: str, *, lock: bool
) -> tuple[DeliveryOrder, Drone]:
    order = repository.get_order(session, order_id, lock=lock)
    if order is None:
        raise OrderNotFoundError(order_id)
    drone = repository.get_drone(session, drone_id, lock=lock)
    if drone is None:
        raise DroneNotFoundError(drone_id)
    return order, drone


def preview_plan(
    session: Session, order_id: str, drone_id: str, settings: Settings
) -> PlanResponse:
    """Read-only: evaluates the plan and changes nothing."""
    order, drone = _load(session, order_id, drone_id, lock=False)
    return _plan(session, order, drone, settings)


def _insert_mission(session: Session, mission: Mission) -> None:
    session.add(mission)
    session.flush()


def _confirm_once(session: Session, order_id: str, drone_id: str, settings: Settings) -> Mission:
    mission_id: str | None = None
    try:
        order, drone = _load(session, order_id, drone_id, lock=True)
        plan = _plan(session, order, drone, settings)
        if not plan.eligible or plan.route.return_hub_id is None:
            raise PlanRejectedError(plan)
        mission_id = new_mission_id()
        mission = Mission(
            id=mission_id,
            order_id=order.id,
            drone_id=drone.id,
            origin_hub_id=plan.route.origin_hub_id,
            return_hub_id=plan.route.return_hub_id,
            status=MissionStatus.ASSIGNED.value,
            origin_to_destination_km=plan.route.origin_to_destination_km,
            destination_to_return_km=plan.route.destination_to_return_km,
            total_km=plan.route.total_km,
            expected_energy_pct=plan.energy.expected_pct,
            worst_case_energy_pct=plan.energy.worst_case_pct,
        )
        _insert_mission(session, mission)
        session.commit()
        return mission
    except IntegrityError:
        # Either a concurrent confirmation won (unique index) or the generated id collided. Start
        # from a clean transaction, look again, and only retry a genuine id collision.
        session.rollback()
        plan = preview_plan(session, order_id, drone_id, settings)
        id_taken = (
            mission_id is not None and repository.get_mission(session, mission_id) is not None
        )
        session.rollback()  # end the read transaction so the next attempt re-reads after locking
        if not plan.eligible:
            raise PlanRejectedError(plan) from None
        if id_taken:
            raise _IdCollisionError from None
        raise  # an unexpected integrity error is a server error, not something to retry
    except BaseException:
        session.rollback()  # also releases the row locks
        raise


def confirm_mission(session: Session, order_id: str, drone_id: str, settings: Settings) -> Mission:
    """Revalidate the plan and create an ASSIGNED mission atomically."""
    for _ in range(MAX_ID_ATTEMPTS):
        try:
            return _confirm_once(session, order_id, drone_id, settings)
        except _IdCollisionError:
            continue
    raise MissionError("Could not allocate a unique mission id")


def cancel_mission(session: Session, mission_id: str) -> Mission:
    """Cancel an ASSIGNED mission before takeoff. Releases the order and the drone."""
    try:
        mission = repository.get_mission_for_update(session, mission_id)
        if mission is None:
            raise MissionNotFoundError(mission_id)
        if mission.status != MissionStatus.ASSIGNED.value:
            raise MissionNotCancellableError(mission.id, mission.status)
        mission.status = MissionStatus.CANCELLED.value
        mission.updated_at = datetime.now(UTC)
        session.commit()
        return mission
    except BaseException:
        session.rollback()
        raise

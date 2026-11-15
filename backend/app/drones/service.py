"""Administrative drone management: create, update and delete.

Occupancy is the physical model of `app/missions/presence.py` (drones docked at a Hub by status and
position), never `Drone.hub_id`. Mutations lock the drone row and, where capacity matters, the
target Hub row, so concurrent requests cannot overfill a Hub. Nothing here moves a flying drone
or edits mission history.
"""

import re
from collections import Counter
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.drones import repository
from app.drones.models import Drone, DroneStatus
from app.drones.schemas import DroneCreateRequest, DroneUpdateRequest
from app.drones.seed import SF1_MODEL_ID
from app.hubs.models import Hub
from app.missions.presence import docked_hub, hub_occupancy
from app.missions.routing import distance_km, hub_point

# Statuses in which a drone is operationally active and must not be edited or deleted.
BUSY_STATUSES = frozenset({DroneStatus.IN_FLIGHT.value, DroneStatus.CHARGING.value})


class DroneManagementError(Exception):
    """Base class; each subclass maps to one HTTP error in the route layer."""


class DroneNotFoundError(DroneManagementError):
    def __init__(self, drone_id: str) -> None:
        super().__init__(f"Drone '{drone_id}' not found")


class HubNotFoundError(DroneManagementError):
    def __init__(self, hub_id: str) -> None:
        super().__init__(f"Hub '{hub_id}' not found")


class DuplicateDroneError(DroneManagementError):
    def __init__(self, drone_id: str) -> None:
        super().__init__(f"Drone '{drone_id}' already exists")


class HubFullError(DroneManagementError):
    def __init__(self, hub: Hub) -> None:
        super().__init__(f"Hub '{hub.id}' has no free place (capacity {hub.drone_capacity})")


class DroneBusyError(DroneManagementError):
    """The drone is in flight, charging, or claimed by an active mission."""


class InvalidChangeError(DroneManagementError):
    """The requested change is not valid for the drone's current state or position."""


class DroneHasHistoryError(DroneManagementError):
    def __init__(self, drone_id: str) -> None:
        super().__init__(
            f"Drone '{drone_id}' has mission history and cannot be deleted; "
            "set it to MAINTENANCE to take it out of service"
        )


def _occupancy(session: Session, settings: Settings) -> tuple[Counter[str], Sequence[Hub]]:
    drones = repository.list_drones(session)
    hubs = repository.list_all_hubs(session)
    return hub_occupancy(drones, hubs, settings.hub_dock_proximity_m), hubs


def _hub_at_position(drone: Drone, hubs: Sequence[Hub], radius_m: float) -> Hub | None:
    """The nearest Hub whose docking radius contains the drone, whatever its status."""
    position = (drone.longitude, drone.latitude)
    best: tuple[float, str, Hub] | None = None
    for hub in hubs:
        distance_m = distance_km(position, hub_point(hub)) * 1000
        if distance_m <= radius_m and (best is None or (distance_m, hub.id) < best[:2]):
            best = (distance_m, hub.id, hub)
    return best[2] if best else None


def _ensure_not_busy(session: Session, drone: Drone) -> None:
    if drone.status in BUSY_STATUSES:
        raise DroneBusyError(f"Drone '{drone.id}' is {drone.status} and cannot be changed")
    if repository.has_missions(session, drone.id, active_only=True):
        raise DroneBusyError(f"Drone '{drone.id}' has an active mission and cannot be changed")


_DRONE_ID = re.compile(r"DRN-(\d{3,})")
INITIAL_BATTERY_PCT = 100
MAX_ID_ATTEMPTS = 3  # the lock below serialises creators; this only covers an unexpected conflict


def _next_drone_id(session: Session) -> str:
    """`DRN-NNN` one above the highest existing number (numeric, so DRN-999 < DRN-1000)."""
    numbers = [
        int(match.group(1))
        for drone_id in session.scalars(select(Drone.id))
        if (match := _DRONE_ID.fullmatch(drone_id))
    ]
    return f"DRN-{max(numbers, default=0) + 1:03d}"


def create_drone(session: Session, data: DroneCreateRequest, settings: Settings) -> Drone:
    """Add an IDLE SF-1 drone, fully charged, docked at an existing Hub that has a free place.

    The operator chooses only the Hub. The id and the 100 % battery are decided here. Creators are
    serialised by a lock on the SF-1 model row (taken after the Hub row, always in that order), so
    the "highest number + 1" each one reads includes every earlier creator's committed drone. The
    primary key stays the last guard: a conflict rolls back and tries again with a fresh number.
    """
    for _ in range(MAX_ID_ATTEMPTS):
        drone_id = ""
        try:
            hub = repository.get_hub_for_update(session, data.hub_id)
            if hub is None:
                raise HubNotFoundError(data.hub_id)
            occupancy, _ = _occupancy(session, settings)
            if occupancy[hub.id] >= hub.drone_capacity:
                raise HubFullError(hub)
            if repository.get_model_for_update(session, SF1_MODEL_ID) is None:
                raise InvalidChangeError(f"Drone model '{SF1_MODEL_ID}' is not configured")
            drone_id = _next_drone_id(session)
            session.add(
                Drone(
                    id=drone_id,
                    model_id=SF1_MODEL_ID,
                    hub_id=hub.id,
                    status=DroneStatus.IDLE.value,
                    battery_pct=INITIAL_BATTERY_PCT,
                    longitude=hub.longitude,
                    latitude=hub.latitude,
                )
            )
            session.commit()
        except IntegrityError:
            session.rollback()
            if drone_id and repository.get_drone(session, drone_id) is not None:
                continue  # another creator took this number: read the numbers again
            raise
        except BaseException:
            session.rollback()
            raise
        created = repository.get_drone(session, drone_id)
        assert created is not None
        return created
    raise DuplicateDroneError(drone_id)


def update_drone(
    session: Session, drone_id: str, data: DroneUpdateRequest, settings: Settings
) -> Drone:
    """Apply whitelisted changes atomically; see the module docstring for the safety rules."""
    changes = data.model_dump(exclude_unset=True)
    try:
        drone = repository.get_drone_for_update(session, drone_id)
        if drone is None:
            raise DroneNotFoundError(drone_id)
        _ensure_not_busy(session, drone)
        _apply_changes(session, drone, changes, settings)
        session.commit()
    except BaseException:
        session.rollback()
        raise
    updated = repository.get_drone(session, drone_id)
    assert updated is not None
    return updated


def _apply_changes(
    session: Session, drone: Drone, changes: dict[str, object], settings: Settings
) -> None:
    radius = settings.hub_dock_proximity_m
    requested_status = changes.get("status")
    new_status = DroneStatus(str(requested_status)).value if requested_status else drone.status
    new_hub_id = changes.get("hub_id")
    relocate = new_hub_id is not None and new_hub_id != drone.hub_id

    becoming_idle = new_status == DroneStatus.IDLE.value and drone.status != new_status
    hubs = repository.list_all_hubs(session)

    # Lock order: the drone row (already held), then the one Hub whose capacity is at stake. The
    # lock is taken before occupancy is read so concurrent requests queue behind each other.
    target_hub: Hub | None = None
    final_hub: Hub | None = None
    if relocate:
        target_hub = repository.get_hub_for_update(session, str(new_hub_id))
        if target_hub is None:
            raise HubNotFoundError(str(new_hub_id))
        final_hub = target_hub
    elif becoming_idle:
        here = _hub_at_position(drone, hubs, radius)
        if here is None:
            raise InvalidChangeError(
                f"Drone '{drone.id}' is not at a Hub and cannot be set to IDLE"
            )
        final_hub = repository.get_hub_for_update(session, here.id)

    counted_at = docked_hub(drone, hubs, radius)  # where it counts now (None in maintenance)
    if relocate and (drone.status != DroneStatus.IDLE.value or counted_at is None):
        raise InvalidChangeError(
            f"Drone '{drone.id}' must be IDLE and docked at a Hub to be reassigned"
        )

    if final_hub is not None and new_status == DroneStatus.IDLE.value:
        occupancy = hub_occupancy(repository.list_drones(session), hubs, radius)
        newly_counted = counted_at is None or counted_at.id != final_hub.id
        if newly_counted and occupancy[final_hub.id] >= final_hub.drone_capacity:
            raise HubFullError(final_hub)

    if target_hub is not None:
        drone.hub_id = target_hub.id
        drone.longitude, drone.latitude = target_hub.longitude, target_hub.latitude
    drone.status = new_status
    battery = changes.get("battery_pct")
    if isinstance(battery, int):
        drone.battery_pct = battery


def delete_drone(session: Session, drone_id: str) -> None:
    """Physically delete a drone with no mission history; never cascades."""
    try:
        drone = repository.get_drone_for_update(session, drone_id)
        if drone is None:
            raise DroneNotFoundError(drone_id)
        _ensure_not_busy(session, drone)
        if repository.has_missions(session, drone_id, active_only=False):
            raise DroneHasHistoryError(drone_id)
        session.delete(drone)
        session.commit()
    except IntegrityError:
        session.rollback()
        raise DroneHasHistoryError(drone_id) from None
    except BaseException:
        session.rollback()
        raise

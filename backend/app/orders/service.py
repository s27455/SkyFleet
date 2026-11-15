"""Administrative order management: create, update and delete.

Orders are editable or deletable only while `READY_FOR_PICKUP` and never referenced by a mission
(any status), so saved mission plans and history are never invalidated. The order row is locked
for the check and the change; the mission foreign key (`RESTRICT`) is the final safeguard.
Nothing here creates or starts a mission.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.drones.models import DroneModel
from app.events.models import EventOrigin, EventType
from app.events.service import append_event, delete_events_for_order
from app.hubs.models import Hub
from app.orders import feasibility, repository
from app.orders.models import DeliveryOrder, OrderStatus
from app.orders.schemas import OrderCreateRequest, OrderUpdateRequest

ORDER_ID_PREFIX = "ORD-"
MAX_ID_ATTEMPTS = 5


class OrderManagementError(Exception):
    """Base class; each subclass maps to one HTTP error in the route layer."""


class OrderNotFoundError(OrderManagementError):
    def __init__(self, order_id: str) -> None:
        super().__init__(f"Order '{order_id}' not found")


class HubNotFoundError(OrderManagementError):
    def __init__(self, hub_id: str) -> None:
        super().__init__(f"Hub '{hub_id}' not found")


class OrderNotServiceableError(OrderManagementError):
    """No Hub can serve the destination (and parcel) under the planner's rules (HTTP 422)."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"No Hub can serve this order: {reason}")


class OrderHasMissionsError(OrderManagementError):
    def __init__(self, order_id: str) -> None:
        super().__init__(
            f"Order '{order_id}' is referenced by a mission (any status) and cannot be changed"
        )


class OrderNotEditableError(OrderManagementError):
    def __init__(self, order_id: str, status: str) -> None:
        super().__init__(
            f"Order '{order_id}' is {status}; only READY_FOR_PICKUP orders can be changed"
        )


def new_order_id() -> str:
    """`ORD-` plus 8 hexadecimal characters; the primary key guarantees uniqueness."""
    return f"{ORDER_ID_PREFIX}{uuid.uuid4().hex[:8].upper()}"


def _require_hub(session: Session, hub_id: str) -> Hub:
    hub = session.get(Hub, hub_id)
    if hub is None:
        raise HubNotFoundError(hub_id)
    return hub


def _ensure_modifiable(session: Session, order: DeliveryOrder) -> None:
    if repository.has_missions(session, order.id):
        raise OrderHasMissionsError(order.id)
    if order.status != OrderStatus.READY_FOR_PICKUP.value:
        raise OrderNotEditableError(order.id, order.status)


def _choose_origin_hub(
    session: Session, data: OrderCreateRequest, payload_energy_factor: float | None
) -> str:
    """The nearest Hub that can serve the destination and parcel, or `OrderNotServiceableError`."""
    hubs = list(session.scalars(select(Hub).order_by(Hub.id)))
    model = session.scalars(select(DroneModel).order_by(DroneModel.id)).first()
    if not hubs:
        raise OrderNotServiceableError("no Hub exists")
    if model is None:
        raise OrderNotServiceableError(
            "no drone model is configured, so the route cannot be checked"
        )
    factor = (
        get_settings().mission_payload_energy_factor
        if payload_energy_factor is None
        else payload_energy_factor
    )
    hub, reason = feasibility.choose_origin_hub(
        hubs,
        model,
        (data.destination_longitude, data.destination_latitude),
        data.package_weight_kg,
        factor,
    )
    if hub is None:
        raise OrderNotServiceableError(reason or "no Hub can reach the destination")
    return hub.id


def create_order(
    session: Session,
    data: OrderCreateRequest,
    origin: EventOrigin = EventOrigin.MANUAL,
    *,
    payload_energy_factor: float | None = None,
) -> DeliveryOrder:
    """Insert a `READY_FOR_PICKUP` order and its `ORDER_CREATED` event in one transaction.

    The destination is stored as given. `origin` is `MANUAL` for orders created through the API
    and `AUTOMATIC` for simulated ones. Without an `origin_hub_id` the origin Hub is the nearest
    Hub that can serve the destination (`feasibility.choose_origin_hub`); it is stored on the order
    and never reassigned. An explicit Hub is used as given.
    """
    origin_hub_id = data.origin_hub_id or _choose_origin_hub(session, data, payload_energy_factor)
    for _ in range(MAX_ID_ATTEMPTS):
        order_id = new_order_id()
        try:
            _require_hub(session, origin_hub_id)
            session.add(
                DeliveryOrder(
                    id=order_id,
                    origin_hub_id=origin_hub_id,
                    destination_address=data.destination_address,
                    destination_longitude=data.destination_longitude,
                    destination_latitude=data.destination_latitude,
                    package_weight_kg=data.package_weight_kg,
                    status=OrderStatus.READY_FOR_PICKUP.value,
                )
            )
            append_event(
                session,
                event_type=EventType.ORDER_CREATED,
                origin=origin,
                order_id=order_id,
                reason="Order created as READY_FOR_PICKUP",
                dedupe_key=f"{EventType.ORDER_CREATED.value}:{order_id}",
            )
            session.commit()
        except IntegrityError:
            session.rollback()
            if session.get(Hub, origin_hub_id) is None:
                raise HubNotFoundError(origin_hub_id) from None
            if repository.get_order(session, order_id) is not None:
                continue  # the generated id collided; try another
            raise
        except BaseException:
            session.rollback()
            raise
        created = repository.get_order(session, order_id)
        assert created is not None
        return created
    raise OrderManagementError("Could not allocate a unique order id")


def update_order(session: Session, order_id: str, data: OrderUpdateRequest) -> DeliveryOrder:
    """Apply whitelisted edits atomically to a mission-free `READY_FOR_PICKUP` order."""
    changes = data.model_dump(exclude_unset=True)
    try:
        order = repository.get_order_for_update(session, order_id)
        if order is None:
            raise OrderNotFoundError(order_id)
        _ensure_modifiable(session, order)
        if "origin_hub_id" in changes:
            _require_hub(session, str(changes["origin_hub_id"]))
        for field, value in changes.items():
            setattr(order, field, value)
        session.commit()
    except IntegrityError:
        session.rollback()
        if repository.has_missions(session, order_id):
            raise OrderHasMissionsError(order_id) from None
        raise
    except BaseException:
        session.rollback()
        raise
    updated = repository.get_order(session, order_id)
    assert updated is not None
    return updated


def delete_order(session: Session, order_id: str) -> None:
    """Physically delete a mission-free `READY_FOR_PICKUP` order; never cascades.

    This is a technical maintenance operation, not cancellation. The order's events are deleted
    explicitly, in the same transaction, after the eligibility checks have passed.
    """
    try:
        order = repository.get_order_for_update(session, order_id)
        if order is None:
            raise OrderNotFoundError(order_id)
        _ensure_modifiable(session, order)
        delete_events_for_order(session, order_id)
        session.delete(order)
        session.commit()
    except IntegrityError:
        session.rollback()
        raise OrderHasMissionsError(order_id) from None
    except BaseException:
        session.rollback()
        raise

"""Delivery order endpoints: reads plus administrative create, update and delete."""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.routes.missions import SettingsDep
from app.config import get_settings
from app.db.session import get_session
from app.orders import cancellation, generator, repository, service
from app.orders.models import DeliveryOrder
from app.orders.schemas import OrderCreateRequest, OrderResponse, OrderUpdateRequest
from app.simulation import clock

router = APIRouter(prefix="/orders", tags=["orders"])

SessionDep = Annotated[Session, Depends(get_session)]


def _http_error(error: service.OrderManagementError) -> HTTPException:
    """Map a domain error to a response with a stable machine-readable code."""
    if isinstance(error, service.OrderNotFoundError):
        return HTTPException(
            status_code=404, detail={"code": "ORDER_NOT_FOUND", "message": str(error)}
        )
    if isinstance(error, service.HubNotFoundError):
        return HTTPException(
            status_code=404, detail={"code": "HUB_NOT_FOUND", "message": str(error)}
        )
    if isinstance(error, service.OrderNotServiceableError):
        return HTTPException(
            status_code=422, detail={"code": "ORDER_NOT_SERVICEABLE", "message": str(error)}
        )
    codes: dict[type[service.OrderManagementError], str] = {
        service.OrderHasMissionsError: "ORDER_HAS_MISSIONS",
        service.OrderNotEditableError: "ORDER_NOT_EDITABLE",
        cancellation.OrderAlreadyDeliveredError: "ORDER_ALREADY_DELIVERED",
        cancellation.OrderNotCancellableError: "ORDER_NOT_CANCELLABLE",
        cancellation.DroneNotRecallableError: "DRONE_NOT_RECALLABLE",
        cancellation.RecallNotPossibleError: "RECALL_NOT_POSSIBLE",
        cancellation.DroneFailedError: "DRONE_FAILED",
    }
    code = codes.get(type(error))
    if code is None:
        return HTTPException(status_code=500, detail={"code": "ORDER_ERROR", "message": str(error)})
    return HTTPException(status_code=409, detail={"code": code, "message": str(error)})


@router.get("", response_model=list[OrderResponse])
def list_orders(session: SessionDep, active: bool = False) -> Sequence[DeliveryOrder]:
    """All orders (full history), or with `?active=true` only those for the operational views.

    The active view hides a `DELIVERED` order once its visibility window has passed (Feature 017A).
    """
    if not active:
        return repository.list_orders(session)
    return repository.list_active_orders(
        session, clock.utcnow(), get_settings().order_delivered_visibility_seconds
    )


@router.post("/generate", response_model=OrderResponse, status_code=201)
def generate_order(session: SessionDep) -> DeliveryOrder:
    """Create one simulated `READY_FOR_PICKUP` order from the prevalidated route catalog."""
    try:
        return generator.generate_one_order(session)
    except service.OrderManagementError as error:
        raise _http_error(error) from error


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(order_id: str, session: SessionDep) -> DeliveryOrder:
    order = repository.get_order(session, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found")
    return order


@router.post("", response_model=OrderResponse, status_code=201)
def create_order(
    body: OrderCreateRequest, session: SessionDep, settings: SettingsDep
) -> DeliveryOrder:
    """Create an order. Without `origin_hub_id` the nearest Hub that can serve the destination is
    chosen (422 `ORDER_NOT_SERVICEABLE` if none can); an explicit Hub is used as given."""
    try:
        return service.create_order(
            session, body, payload_energy_factor=settings.mission_payload_energy_factor
        )
    except service.OrderManagementError as error:
        raise _http_error(error) from error


@router.post("/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(order_id: str, session: SessionDep, settings: SettingsDep) -> DeliveryOrder:
    """Cancel an order (a business transition, not deletion). Idempotent: an already cancelled
    order is returned as it is, with no second event.

    A flying drone that has not yet handed over the parcel is recalled to the nearest reachable
    Hub with the parcel on board; a delivered order is rejected (409). MVP/demo control.
    """
    try:
        return cancellation.cancel_order(session, order_id, clock.utcnow(), settings)
    except service.OrderManagementError as error:
        raise _http_error(error) from error


@router.patch("/{order_id}", response_model=OrderResponse)
def update_order(order_id: str, body: OrderUpdateRequest, session: SessionDep) -> DeliveryOrder:
    try:
        return service.update_order(session, order_id, body)
    except service.OrderManagementError as error:
        raise _http_error(error) from error


@router.delete("/{order_id}", status_code=204)
def delete_order(order_id: str, session: SessionDep) -> Response:
    try:
        service.delete_order(session, order_id)
    except service.OrderManagementError as error:
        raise _http_error(error) from error
    return Response(status_code=204)

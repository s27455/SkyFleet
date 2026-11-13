"""Delivery order endpoints: reads plus administrative create, update and delete."""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.orders import generator, repository, service
from app.orders.models import DeliveryOrder
from app.orders.schemas import OrderCreateRequest, OrderResponse, OrderUpdateRequest

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
    codes: dict[type[service.OrderManagementError], str] = {
        service.OrderHasMissionsError: "ORDER_HAS_MISSIONS",
        service.OrderNotEditableError: "ORDER_NOT_EDITABLE",
    }
    code = codes.get(type(error))
    if code is None:
        return HTTPException(status_code=500, detail={"code": "ORDER_ERROR", "message": str(error)})
    return HTTPException(status_code=409, detail={"code": code, "message": str(error)})


@router.get("", response_model=list[OrderResponse])
def list_orders(session: SessionDep) -> Sequence[DeliveryOrder]:
    return repository.list_orders(session)


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
def create_order(body: OrderCreateRequest, session: SessionDep) -> DeliveryOrder:
    try:
        return service.create_order(session, body)
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

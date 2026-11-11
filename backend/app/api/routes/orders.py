"""Read-only delivery order endpoints."""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.orders import repository
from app.orders.models import DeliveryOrder
from app.orders.schemas import OrderResponse

router = APIRouter(prefix="/orders", tags=["orders"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[OrderResponse])
def list_orders(session: SessionDep) -> Sequence[DeliveryOrder]:
    return repository.list_orders(session)


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(order_id: str, session: SessionDep) -> DeliveryOrder:
    order = repository.get_order(session, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found")
    return order

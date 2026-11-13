"""Operational events (Feature 018A): append, read API, ORDER_CREATED and technical deletion."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.events import repository
from app.events.models import EventOrigin, EventType, OperationalEvent
from app.events.service import MAX_DETAILS_JSON_CHARS, append_event
from app.orders import generator, service
from app.orders.models import DeliveryOrder

VALID = {
    "origin_hub_id": "hub-forum-gdansk",
    "destination_address": "ul. Testowa 1, Gdańsk",
    "destination_longitude": 18.65,
    "destination_latitude": 54.35,
    "package_weight_kg": 1.5,
}


def _count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(OperationalEvent)) or 0


# --- append and read --------------------------------------------------------------------------


def test_append_and_read_round_trip(seeded: Session) -> None:
    moment = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)
    created = append_event(
        seeded,
        event_type=EventType.ORDER_CREATED,
        origin=EventOrigin.SYSTEM,
        order_id="ORD-001",
        reason="why",
        details={"k": 1},
        occurred_at=moment,
    )
    seeded.commit()

    assert created is True
    (event,) = repository.list_events(seeded, order_id="ORD-001")
    assert (event.event_type, event.origin, event.reason, event.details) == (
        "ORDER_CREATED",
        "SYSTEM",
        "why",
        {"k": 1},
    )
    assert event.occurred_at.replace(tzinfo=UTC) == moment
    assert event.mission_id is None and event.drone_id is None


def test_events_are_ordered_by_time_then_id(seeded: Session) -> None:
    base = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)
    for minutes, reason in ((5, "late"), (0, "first"), (0, "second")):
        append_event(
            seeded,
            event_type=EventType.ORDER_CREATED,
            origin=EventOrigin.SYSTEM,
            order_id="ORD-001",
            reason=reason,
            occurred_at=base + timedelta(minutes=minutes),
        )
    seeded.commit()

    reasons = [e.reason for e in repository.list_events(seeded, order_id="ORD-001")]

    assert reasons == ["first", "second", "late"]


def test_limit_keeps_the_newest_events_oldest_first(seeded: Session) -> None:
    base = datetime(2026, 11, 13, 10, 0, tzinfo=UTC)
    for minute in range(5):
        append_event(
            seeded,
            event_type=EventType.ORDER_CREATED,
            origin=EventOrigin.SYSTEM,
            order_id="ORD-001",
            reason=str(minute),
            occurred_at=base + timedelta(minutes=minute),
        )
    seeded.commit()

    events = repository.list_events(seeded, order_id="ORD-001", limit=2)

    assert [e.reason for e in events] == ["3", "4"]


def test_filter_is_required_and_unrelated_events_are_excluded(seeded: Session) -> None:
    append_event(
        seeded, event_type=EventType.ORDER_CREATED, origin=EventOrigin.SYSTEM, order_id="ORD-001"
    )
    append_event(
        seeded, event_type=EventType.ORDER_CREATED, origin=EventOrigin.SYSTEM, order_id="ORD-002"
    )
    seeded.commit()

    with pytest.raises(ValueError):
        repository.list_events(seeded)
    assert [e.order_id for e in repository.list_events(seeded, order_id="ORD-002")] == ["ORD-002"]


def test_oversized_details_are_rejected(seeded: Session) -> None:
    with pytest.raises(ValueError):
        append_event(
            seeded,
            event_type=EventType.ORDER_CREATED,
            origin=EventOrigin.SYSTEM,
            details={"x": "a" * MAX_DETAILS_JSON_CHARS},
        )


def test_duplicate_dedupe_key_is_ignored_and_the_transaction_stays_usable(seeded: Session) -> None:
    kwargs = {
        "event_type": EventType.ORDER_CREATED,
        "origin": EventOrigin.SYSTEM,
        "order_id": "ORD-001",
        "dedupe_key": "same",
    }

    first = append_event(seeded, **kwargs)  # type: ignore[arg-type]
    second = append_event(seeded, **kwargs)  # type: ignore[arg-type]
    third = append_event(  # same transaction still works after the duplicate
        seeded,
        **{**kwargs, "dedupe_key": "other"},  # type: ignore[arg-type]
    )
    seeded.commit()

    assert (first, second, third) == (True, False, True)
    assert _count(seeded) == 2


def test_rollback_leaves_no_event(seeded: Session) -> None:
    append_event(
        seeded, event_type=EventType.ORDER_CREATED, origin=EventOrigin.SYSTEM, order_id="ORD-001"
    )
    seeded.rollback()

    assert _count(seeded) == 0


# --- API --------------------------------------------------------------------------------------


def test_api_requires_a_filter_and_bounds_the_limit(client: TestClient, seeded: Session) -> None:
    missing = client.get("/api/events")
    too_big = client.get("/api/events", params={"order_id": "ORD-001", "limit": 201})

    assert missing.status_code == 422
    assert missing.json()["detail"]["code"] == "EVENT_FILTER_REQUIRED"
    assert too_big.status_code == 422


def test_api_empty_state_for_an_order_without_events(client: TestClient, seeded: Session) -> None:
    response = client.get("/api/events", params={"order_id": "ORD-001"})

    assert response.status_code == 200
    assert response.json() == []


# --- ORDER_CREATED ----------------------------------------------------------------------------


def test_api_created_order_has_a_manual_created_event(client: TestClient, seeded: Session) -> None:
    order_id = client.post("/api/orders", json=VALID).json()["id"]

    (event,) = client.get("/api/events", params={"order_id": order_id}).json()

    assert event["event_type"] == "ORDER_CREATED"
    assert event["origin"] == "MANUAL"
    assert event["occurred_at"].endswith("Z") or "+00:00" in event["occurred_at"]


def test_generated_order_has_an_automatic_created_event(seeded: Session) -> None:
    order = generator.generate_one_order(seeded)

    (event,) = repository.list_events(seeded, order_id=order.id)

    assert (event.event_type, event.origin) == ("ORDER_CREATED", "AUTOMATIC")


def test_failed_create_leaves_no_orphan_event(
    client: TestClient, seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _count(seeded)
    response = client.post("/api/orders", json={**VALID, "origin_hub_id": "hub-nowhere"})

    assert response.status_code == 404
    assert _count(seeded) == before


# --- technical deletion -----------------------------------------------------------------------


def test_deleting_an_order_removes_its_events_only(client: TestClient, seeded: Session) -> None:
    keep = client.post("/api/orders", json=VALID).json()["id"]
    gone = client.post("/api/orders", json=VALID).json()["id"]

    assert client.delete(f"/api/orders/{gone}").status_code == 204

    assert client.get("/api/events", params={"order_id": gone}).json() == []
    assert len(client.get("/api/events", params={"order_id": keep}).json()) == 1


def test_rejected_delete_keeps_the_events(client: TestClient, seeded: Session) -> None:
    order = seeded.get(DeliveryOrder, "ORD-001")
    assert order is not None
    order.status = "DELIVERED"
    append_event(
        seeded, event_type=EventType.ORDER_CREATED, origin=EventOrigin.SYSTEM, order_id="ORD-001"
    )
    seeded.commit()

    response = client.delete("/api/orders/ORD-001")

    assert response.status_code == 409
    assert len(client.get("/api/events", params={"order_id": "ORD-001"}).json()) == 1


def test_failed_delete_rolls_back_event_removal(
    seeded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    order = service.create_order(seeded, service.OrderCreateRequest(**VALID))  # type: ignore[attr-defined]

    def boom() -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(seeded, "commit", boom)
    with pytest.raises(RuntimeError):
        service.delete_order(seeded, order.id)
    monkeypatch.undo()

    assert seeded.get(DeliveryOrder, order.id) is not None
    assert len(repository.list_events(seeded, order_id=order.id)) == 1


def test_drone_with_events_cannot_be_deleted(client: TestClient, seeded: Session) -> None:
    append_event(
        seeded, event_type=EventType.DRONE_FAILURE, origin=EventOrigin.SYSTEM, drone_id="DRN-001"
    )
    seeded.commit()

    response = client.delete("/api/drones/DRN-001")

    assert response.status_code == 409
    assert len(client.get("/api/events", params={"drone_id": "DRN-001"}).json()) == 1

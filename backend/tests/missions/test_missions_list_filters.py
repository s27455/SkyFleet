"""`GET /api/missions` filters: `status` (repeatable) and `limit` (most recent N), applied in SQL.

The dashboard polls the live missions every 2 s, so it must not download the whole history.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.missions import repository
from app.missions.models import Mission, MissionStatus

START = datetime(2026, 11, 12, 10, 0, 0, tzinfo=UTC)
LIVE = ["ASSIGNED", "IN_FLIGHT", "EMERGENCY"]


def add_mission(
    session: Session, number: int, status: MissionStatus, *, order: str, drone: str
) -> str:
    mission_id = f"MIS-{number:08X}"
    session.add(
        Mission(
            id=mission_id,
            order_id=order,
            drone_id=drone,
            origin_hub_id="hub-galeria-baltycka",
            return_hub_id="hub-galeria-baltycka",
            status=status.value,
            origin_to_destination_km=0.7,
            destination_to_return_km=0.7,
            total_km=1.4,
            expected_energy_pct=7.0,
            worst_case_energy_pct=7.5,
            created_at=START + timedelta(minutes=number),
        )
    )
    return mission_id


@pytest.fixture
def history(seeded: Session) -> dict[str, str]:
    """Six missions, oldest first. The two active ones use different drones (a database rule)."""
    ids = {
        "completed_old": add_mission(
            seeded, 1, MissionStatus.COMPLETED, order="ORD-001", drone="DRN-010"
        ),
        "cancelled": add_mission(
            seeded, 2, MissionStatus.CANCELLED, order="ORD-001", drone="DRN-010"
        ),
        "emergency": add_mission(
            seeded, 3, MissionStatus.EMERGENCY, order="ORD-002", drone="DRN-011"
        ),
        "completed_new": add_mission(
            seeded, 4, MissionStatus.COMPLETED, order="ORD-003", drone="DRN-010"
        ),
        "assigned": add_mission(
            seeded, 5, MissionStatus.ASSIGNED, order="ORD-004", drone="DRN-007"
        ),
        "in_flight": add_mission(
            seeded, 6, MissionStatus.IN_FLIGHT, order="ORD-005", drone="DRN-008"
        ),
    }
    seeded.commit()
    return ids


def listed(client: TestClient, **params: str | int | list[str]) -> list[str]:
    response = client.get("/api/missions", params=params)
    assert response.status_code == 200
    return [mission["id"] for mission in response.json()]


def test_without_filters_the_whole_history_is_returned_oldest_first(
    client: TestClient, history: dict[str, str]
) -> None:
    assert listed(client) == list(history.values())


def test_a_single_status_filter_keeps_only_that_status(
    client: TestClient, history: dict[str, str]
) -> None:
    assert listed(client, status="ASSIGNED") == [history["assigned"]]


def test_repeated_status_filters_keep_the_live_missions_and_drop_the_history(
    client: TestClient, history: dict[str, str]
) -> None:
    assert listed(client, status=LIVE) == [
        history["emergency"],
        history["assigned"],
        history["in_flight"],
    ]


def test_an_unknown_status_is_rejected(client: TestClient, history: dict[str, str]) -> None:
    assert client.get("/api/missions", params={"status": "FLYING"}).status_code == 422


def test_limit_keeps_the_most_recent_missions_still_oldest_first(
    client: TestClient, history: dict[str, str]
) -> None:
    assert listed(client, limit=3) == [
        history["completed_new"],
        history["assigned"],
        history["in_flight"],
    ]


def test_limit_is_applied_after_the_status_filter(
    client: TestClient, history: dict[str, str]
) -> None:
    assert listed(client, status="COMPLETED", limit=1) == [history["completed_new"]]


@pytest.mark.parametrize("limit", [0, -1, repository.MAX_LIST_LIMIT + 1])
def test_a_limit_outside_the_allowed_range_is_rejected(client: TestClient, limit: int) -> None:
    assert client.get("/api/missions", params={"limit": limit}).status_code == 422


def test_the_status_filter_runs_in_sql_not_in_python(
    seeded: Session, history: dict[str, str]
) -> None:
    """The repository returns only the matching rows, so nothing else is loaded or serialised."""
    rows = repository.list_missions(seeded, statuses=["ASSIGNED"])

    assert [mission.id for mission in rows] == [history["assigned"]]


def test_a_listed_live_mission_has_the_same_fields_as_in_the_full_list(
    client: TestClient, history: dict[str, str]
) -> None:
    full = {m["id"]: m for m in client.get("/api/missions").json()}
    live = client.get("/api/missions", params={"status": LIVE}).json()

    assert live
    assert all(mission == full[mission["id"]] for mission in live)

"""Concurrency tests against real PostgreSQL, in a uniquely named temporary database.

Opt-in (`uv run pytest -m postgres`): the default suite is hermetic and runs on SQLite. This module
creates `skyfleet_test_<random>` on the same server as the development database, runs the real
migrations there, races real sessions in threads, and drops the temporary database afterwards. It
refuses to touch any database that is not its own temporary one. The development database, its
volume and port 5432 are never used. If the server is unreachable the tests are skipped.
"""

import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.missions import service
from app.missions.models import ACTIVE_MISSION_STATUSES, Mission, MissionStatus

pytestmark = pytest.mark.postgres

BACKEND_DIR = Path(__file__).resolve().parents[2]
TEMP_PREFIX = "skyfleet_test_"
# Only the local Docker PostgreSQL may be used; never the Windows instance on 5432 or a remote host.
ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"}
DOCKER_POSTGRES_PORT = 55432
SETTINGS = Settings(mission_payload_energy_factor=0.5, hub_dock_proximity_m=50)


@dataclass(frozen=True)
class Outcome:
    kind: str  # "created", "cancelled", "rejected" or "not-cancellable"
    detail: str = ""


@pytest.fixture
def factory(temp_engine: Engine) -> Iterator[sessionmaker[Session]]:
    with temp_engine.begin() as connection:
        connection.execute(text("DELETE FROM missions"))
    yield sessionmaker(bind=temp_engine, expire_on_commit=False)


def race(actions: list[Callable[[], Outcome]]) -> list[Outcome]:
    """Run all actions at the same moment in separate threads and collect their outcomes."""
    barrier = threading.Barrier(len(actions))

    def run(action: Callable[[], Outcome]) -> Outcome:
        barrier.wait(timeout=10)
        return action()

    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        return [future.result(timeout=30) for future in [pool.submit(run, a) for a in actions]]


def confirm_action(
    factory: sessionmaker[Session], order_id: str, drone_id: str
) -> Callable[[], Outcome]:
    def action() -> Outcome:
        with factory() as session:
            try:
                mission = service.confirm_mission(session, order_id, drone_id, SETTINGS)
            except service.PlanRejectedError as error:
                return Outcome("rejected", ",".join(r.code for r in error.plan.reasons))
            return Outcome("created", mission.id)

    return action


def cancel_action(factory: sessionmaker[Session], mission_id: str) -> Callable[[], Outcome]:
    def action() -> Outcome:
        with factory() as session:
            try:
                service.cancel_mission(session, mission_id)
            except service.MissionNotCancellableError as error:
                return Outcome("not-cancellable", error.status)
            return Outcome("cancelled")

    return action


def kinds(outcomes: list[Outcome]) -> list[str]:
    return sorted(outcome.kind for outcome in outcomes)


def active_count(factory: sessionmaker[Session], column: str, value: str) -> int:
    active = [status.value for status in ACTIVE_MISSION_STATUSES]
    with factory() as session:
        statement = (
            select(func.count())
            .select_from(Mission)
            .where(getattr(Mission, column) == value, Mission.status.in_(active))
        )
        return session.scalar(statement) or 0


def test_the_active_mission_indexes_are_partial_unique_indexes(temp_engine: Engine) -> None:
    with temp_engine.connect() as connection:
        rows = connection.execute(
            text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'missions'")
        ).all()
    definitions: dict[str, str] = {row[0]: row[1] for row in rows}

    for name in ("uq_missions_active_order", "uq_missions_active_drone"):
        assert "UNIQUE" in definitions[name]
        assert "WHERE" in definitions[name]


def test_two_confirmations_for_the_same_order_create_exactly_one_mission(
    factory: sessionmaker[Session],
) -> None:
    outcomes = race(
        [
            confirm_action(factory, "ORD-001", "DRN-010"),
            confirm_action(factory, "ORD-001", "DRN-011"),
        ]
    )

    assert kinds(outcomes) == ["created", "rejected"]
    rejected = next(o for o in outcomes if o.kind == "rejected")
    assert "ORDER_ALREADY_ASSIGNED" in rejected.detail
    assert active_count(factory, "order_id", "ORD-001") == 1


def test_two_confirmations_for_the_same_drone_create_exactly_one_mission(
    factory: sessionmaker[Session],
) -> None:
    outcomes = race(
        [
            confirm_action(factory, "ORD-001", "DRN-010"),
            confirm_action(factory, "ORD-002", "DRN-010"),
        ]
    )

    assert kinds(outcomes) == ["created", "rejected"]
    rejected = next(o for o in outcomes if o.kind == "rejected")
    assert "DRONE_ALREADY_ASSIGNED" in rejected.detail
    assert active_count(factory, "drone_id", "DRN-010") == 1


def test_many_identical_confirmations_create_exactly_one_mission(
    factory: sessionmaker[Session],
) -> None:
    outcomes = race([confirm_action(factory, "ORD-001", "DRN-010") for _ in range(8)])

    assert kinds(outcomes) == ["created"] + ["rejected"] * 7
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Mission)) == 1


def test_independent_confirmations_all_succeed(factory: sessionmaker[Session]) -> None:
    outcomes = race(
        [
            confirm_action(factory, "ORD-001", "DRN-010"),
            confirm_action(factory, "ORD-002", "DRN-011"),
            confirm_action(factory, "ORD-004", "DRN-007"),
        ]
    )

    assert kinds(outcomes) == ["created"] * 3


def test_two_concurrent_cancellations_cancel_exactly_once(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        mission = service.confirm_mission(session, "ORD-001", "DRN-010", SETTINGS)

    outcomes = race([cancel_action(factory, mission.id), cancel_action(factory, mission.id)])

    assert kinds(outcomes) == ["cancelled", "not-cancellable"]
    with factory() as session:
        stored = session.get(Mission, mission.id)
        assert stored is not None
        assert stored.status == MissionStatus.CANCELLED


def test_assigning_while_cancelling_never_leaves_two_active_missions(
    factory: sessionmaker[Session],
) -> None:
    with factory() as session:
        first = service.confirm_mission(session, "ORD-001", "DRN-010", SETTINGS)

    outcomes = race(
        [cancel_action(factory, first.id), confirm_action(factory, "ORD-001", "DRN-011")]
    )

    assert "cancelled" in kinds(outcomes)  # the cancellation always succeeds
    assert active_count(factory, "order_id", "ORD-001") <= 1
    created = [o for o in outcomes if o.kind == "created"]
    assert active_count(factory, "order_id", "ORD-001") == len(created)
    with factory() as session:
        assert session.get(Mission, first.id).status == MissionStatus.CANCELLED  # type: ignore[union-attr]

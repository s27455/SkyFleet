"""The snapshot on a real PostgreSQL database (opt-in: `pytest -m postgres`).

These run on the temporary database of the `temp_engine` fixture (the development database is never
touched) and prove what SQLite cannot: the transaction really is REPEATABLE READ and READ ONLY, a
write is refused by the database itself, the snapshot stays consistent while another connection
commits, it never blocks the writers, and a slow query fails closed.
"""

import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from app.ai import models as ai_models  # noqa: F401  (registers the AI tables)
from app.ai.budget import SqlBudgetStore
from app.ai.errors import AiError, ConcurrencyLimitError, TooSoonError
from app.ai.gateway import AiGateway
from app.ai.models import AiBudgetState, AiRequestLog
from app.config import Settings
from app.dispatch.service import active_claims
from app.drones.models import Drone
from app.fleet_context import snapshot
from app.fleet_context.errors import FleetContextUnavailableError
from app.fleet_context.service import FleetAnswer, ask_fleet_question
from app.fleet_context.snapshot import build_fleet_context, read_only_snapshot
from app.hubs.repository import list_hubs
from app.missions.models import MissionStatus
from app.orders.models import DeliveryOrder
from app.simulation.models import IncidentAcknowledgement, LprScenario
from app.weather.models import WeatherState

from .helpers import NOW, Clock, FakeTransport, add_flight, add_mission, ai_settings

pytestmark = pytest.mark.postgres

GATEWAY_START = datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)
INSERT_ORDER = text(
    "INSERT INTO orders (id, origin_hub_id, destination_address, destination_longitude, "
    "destination_latitude, package_weight_kg, status, created_at, updated_at) VALUES "
    "('ORD-CONC', 'hub-forum-gdansk', 'x', 18.6, 54.3, 1.0, 'READY_FOR_PICKUP', now(), now())"
)


@pytest.fixture
def factory(temp_engine: Engine) -> Iterator[sessionmaker[Session]]:
    with temp_engine.begin() as connection:  # the AI ledger starts empty in every test
        connection.execute(text("DELETE FROM ai_request_log"))
        connection.execute(text("DELETE FROM ai_budget_state"))
    yield sessionmaker(bind=temp_engine, expire_on_commit=False)


@pytest.fixture
def settings() -> Settings:
    return ai_settings()


def fingerprint(engine: Engine) -> dict[str, str]:
    """A content hash of every table: any write, however small, changes it."""
    with engine.connect() as connection:
        tables = connection.execute(
            text("select table_name from information_schema.tables where table_schema='public'")
        ).scalars()
        hashes: dict[str, str] = {}
        for name in sorted(tables):
            query = (
                "select md5(coalesce(string_agg(t::text, '|' order by t::text), '')) "
                f'from "{name}" t'
            )
            hashes[name] = str(connection.execute(text(query)).scalar())
        return hashes


# --- the transaction ----


def test_the_snapshot_is_repeatable_read_read_only_with_a_timeout(
    factory: sessionmaker[Session],
) -> None:
    with read_only_snapshot(factory) as session:
        assert session.execute(text("show transaction_read_only")).scalar() == "on"
        assert session.execute(text("show transaction_isolation")).scalar() == "repeatable read"
        assert session.execute(text("show statement_timeout")).scalar() == "2s"

    with factory() as ordinary:  # nothing leaked into the pooled connection
        assert ordinary.execute(text("show transaction_read_only")).scalar() == "off"
        assert ordinary.execute(text("show transaction_isolation")).scalar() == "read committed"
        assert ordinary.execute(text("show statement_timeout")).scalar() != "2s"


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE drones SET battery_pct = 1",
        "DELETE FROM orders",
        "INSERT INTO hubs (id, name, address, longitude, latitude, drone_capacity) "
        "VALUES ('h', 'n', 'a', 18, 54, 5)",
        "TRUNCATE TABLE missions CASCADE",
        "CREATE TABLE sneaky (x int)",
        "DROP TABLE weather_state",
        "CREATE TEMP TABLE sneaky_temp (x int)",
    ],
)
def test_the_database_itself_refuses_every_write(
    factory: sessionmaker[Session], temp_engine: Engine, statement: str
) -> None:
    before = fingerprint(temp_engine)

    with pytest.raises(DBAPIError, match="read-only transaction"):
        with read_only_snapshot(factory) as session:
            session.execute(text(statement))

    assert fingerprint(temp_engine) == before


def test_building_a_snapshot_changes_nothing(
    factory: sessionmaker[Session], temp_engine: Engine, settings: Settings
) -> None:
    before = fingerprint(temp_engine)

    build_fleet_context(factory, settings, NOW)
    build_fleet_context(factory, settings, NOW)

    assert fingerprint(temp_engine) == before


def test_the_snapshot_of_a_seeded_postgres_database(
    factory: sessionmaker[Session], settings: Settings
) -> None:
    context = build_fleet_context(factory, settings, NOW)

    assert context.summary.drones_total == 12 and context.summary.drones_docked == 12
    assert context.summary.orders_open.waiting_for_drone == 11
    assert [h.docked for h in context.hubs] == [3, 3, 3, 3]
    assert context.limitations == ["WORKER_NOT_RUNNING"]  # the temporary database has no worker


# --- consistency while the simulation commits ----


def test_a_snapshot_is_consistent_while_another_connection_commits(
    factory: sessionmaker[Session],
    temp_engine: Engine,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with temp_engine.connect() as connection:
        original = connection.execute(
            text("select status, battery_pct from drones where id='DRN-001'")
        ).one()
    real = active_claims
    fired: list[bool] = []

    def commit_in_between(session: Session) -> tuple[set[str], set[str]]:
        # runs after the drones were read and before the orders are counted, like a worker tick
        if not fired:
            fired.append(True)
            with temp_engine.begin() as other:
                other.execute(
                    text("UPDATE drones SET status='MAINTENANCE', battery_pct=5 WHERE id='DRN-001'")
                )
                other.execute(INSERT_ORDER)
        return real(session)

    monkeypatch.setattr(snapshot, "active_claims", commit_in_between)
    try:
        context = build_fleet_context(factory, settings, NOW)
        monkeypatch.undo()
        after = build_fleet_context(factory, settings, NOW)  # a new snapshot does see the change
    finally:
        with temp_engine.begin() as connection:
            connection.execute(text("DELETE FROM orders WHERE id='ORD-CONC'"))
            connection.execute(
                text("UPDATE drones SET status=:s, battery_pct=:b WHERE id='DRN-001'"),
                {"s": original.status, "b": original.battery_pct},
            )

    assert fired == [True]
    # the first snapshot saw the world as it was when it began, in EVERY section
    assert context.summary.drones_by_status["MAINTENANCE"] == 0
    drone = next(d for d in context.drones if d.id == "DRN-001")
    assert (drone.status, drone.battery_pct) == (original.status, original.battery_pct)
    assert context.summary.orders_open.waiting_for_drone == 11
    assert sum(h.waiting_orders for h in context.hubs) == 11  # the hub rows agree with the total
    assert context.active_incidents == []
    # the later snapshot proves the concurrent commit really happened
    assert after.summary.drones_by_status["MAINTENANCE"] == 1
    assert after.summary.orders_open.waiting_for_drone == 12


def test_the_snapshot_never_blocks_the_simulation_and_is_never_blocked_by_it(
    factory: sessionmaker[Session], temp_engine: Engine, settings: Settings
) -> None:
    with read_only_snapshot(factory) as session:  # a snapshot is open ...
        assert session.execute(text("select count(*) from drones")).scalar() == 12
        with temp_engine.begin() as writer:  # ... and a writer commits at once (no waiting)
            writer.execute(text("SET LOCAL lock_timeout = '1s'"))
            writer.execute(text("UPDATE drones SET battery_pct = battery_pct WHERE id='DRN-001'"))
        assert session.execute(text("select count(*) from drones")).scalar() == 12

    writer = temp_engine.connect()  # a writer holds a row lock in an open transaction ...
    transaction = writer.begin()
    try:
        writer.execute(text("UPDATE drones SET battery_pct = battery_pct WHERE id='DRN-001'"))
        context = build_fleet_context(factory, settings, NOW)  # ... the snapshot reads past it
    finally:
        transaction.rollback()
        writer.close()
    assert context.summary.drones_total == 12


# --- failing closed ----


def test_a_slow_query_fails_closed_and_no_provider_is_contacted(
    factory: sessionmaker[Session],
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = list_hubs

    def slow(session: Session):  # type: ignore[no-untyped-def]
        session.execute(text("select pg_sleep(1)"))
        return real(session)

    monkeypatch.setattr(snapshot, "STATEMENT_TIMEOUT_MS", 100)
    monkeypatch.setattr(snapshot, "list_hubs", slow)
    transport = FakeTransport()
    gateway = AiGateway(settings, transport, SqlBudgetStore(factory), clock=Clock(GATEWAY_START))

    with pytest.raises(DBAPIError, match="statement timeout"):
        build_fleet_context(factory, settings, NOW)
    with pytest.raises(FleetContextUnavailableError):
        ask_fleet_question(
            "How many drones are charging?",
            gateway=gateway,
            factory=factory,
            settings=settings,
            now=NOW,
        )

    assert transport.requests == []
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AiRequestLog)) == 0
        assert session.scalar(select(func.count()).select_from(AiBudgetState)) == 0


def test_the_whole_flow_on_postgres_keeps_the_budget_accounting(
    factory: sessionmaker[Session], settings: Settings
) -> None:
    transport = FakeTransport()
    gateway = AiGateway(settings, transport, SqlBudgetStore(factory), clock=Clock(GATEWAY_START))

    result = ask_fleet_question(
        "How many drones are charging?",
        gateway=gateway,
        factory=factory,
        settings=settings,
        now=NOW + timedelta(seconds=1),
    )

    (request,) = transport.requests
    assert len(request.system.encode()) + len(request.user_content.encode()) <= 16 * 1024
    with factory() as session:
        (row,) = session.scalars(select(AiRequestLog)).all()
        state = session.get(AiBudgetState, "anthropic")
    assert row.status == "SUCCEEDED" and row.charged_nano_usd == result.answer.charged_nano_usd
    assert state is not None and (state.reserved_nano_usd, state.halted) == (0, False)


# --- Gate C1: every emergency and warning rule on PostgreSQL, with data ----


def test_emergencies_orders_and_warnings_on_postgres(
    factory: sessionmaker[Session], temp_engine: Engine, settings: Settings
) -> None:
    """The SQLite semantic matrix again on a real server (joins, FILTER counts, EXISTS), with the
    incident counts cross-checked by independent SQL. Everything is removed afterwards."""
    with factory() as session:
        originals = {
            d.id: (d.status, d.battery_pct, d.longitude, d.latitude)
            for d in session.scalars(select(Drone))
        }
    mission_ids = [
        "MIS-QA-APP", "MIS-QA-GND", "MIS-QA-BAT", "MIS-QA-REC", "MIS-QA-OLD", "MIS-QA-DEL",
        "MIS-QA-INT", "MIS-QA-OLDI",
    ]  # fmt: skip
    order_ids = ["ORD-QA-DEL", "ORD-QA-INT", "ORD-QA-OLDI"]
    try:
        with factory() as session:
            _populate(session)
            session.commit()
        context = build_fleet_context(factory, settings, NOW)
        with temp_engine.connect() as raw:
            raw_grounded = raw.execute(text(GROUNDED_SQL)).scalar()
            raw_recovered = raw.execute(text(RECOVERED_SQL)).scalar()
            raw_approach = raw.execute(
                text("select count(*) from mission_flights where phase='EMERGENCY_APPROACH'")
            ).scalar()
    finally:
        with temp_engine.begin() as connection:
            connection.execute(
                text("delete from incident_acknowledgements where mission_id = any(:ids)"),
                {"ids": mission_ids},
            )
            connection.execute(
                text("delete from mission_flights where mission_id = any(:ids)"),
                {"ids": mission_ids},
            )
            connection.execute(
                text("delete from missions where id = any(:ids)"), {"ids": mission_ids}
            )
            connection.execute(text("delete from orders where id = any(:ids)"), {"ids": order_ids})
            connection.execute(text("delete from lpr_scenarios where id = 'LPR-QA'"))
            connection.execute(text("update weather_state set active = false, activated_at = null"))
            for drone_id, (status, battery, lon, lat) in originals.items():
                connection.execute(
                    text(
                        "update drones set status=:s, battery_pct=:b, longitude=:lo, latitude=:la "
                        "where id=:i"
                    ),
                    {"s": status, "b": battery, "lo": lon, "la": lat, "i": drone_id},
                )

    by = {(i.kind.value, i.drone_id): i for i in context.active_incidents}
    assert set(by) == {
        ("EMERGENCY_LANDING_IN_PROGRESS", "DRN-001"),
        ("DRONE_GROUNDED", "DRN-004"),
        ("DRONE_GROUNDED", "DRN-002"),
    }
    assert (raw_approach, raw_grounded, raw_recovered) == (1, 2, 1)  # independent SQL agrees
    assert raw_approach is not None and raw_grounded is not None
    assert context.summary.active_incident_count == raw_approach + raw_grounded
    assert context.summary.recovered_alert_count == raw_recovered == len(context.recovered_alerts)
    assert [a.drone_id for a in context.recovered_alerts] == ["DRN-007"]
    assert by[("DRONE_GROUNDED", "DRN-004")].recovery_pending is True
    assert by[("DRONE_GROUNDED", "DRN-002")].acknowledged is True
    orders = context.summary.orders_open
    history = context.summary.orders_history
    assert orders.in_delivery == 1 and orders.waiting_for_drone == 11
    assert (history.interrupted_all_time, history.interrupted_last_60_min) == (2, 1)
    assert [w.kind.value for w in context.operational_warnings] == [
        "LPR_HELICOPTER_ACTIVE",
        "RAIN_WARNING_ACTIVE",
    ]
    ids = [d.id for d in context.drones]  # roster priority on a real server
    assert ids[:4] == ["DRN-001", "DRN-002", "DRN-004", "DRN-005"]  # flagged, then active
    assert ids[4:] == sorted(ids[4:])  # everyone else by id
    assert context.limitations == ["WORKER_NOT_RUNNING"]  # no mismatch, nothing else degraded
    with factory() as session:  # the temporary database is back to its seeded state
        assert session.scalar(select(func.count()).select_from(DeliveryOrder)) == 11


GROUNDED_JOIN = (
    "from mission_flights f join missions m on m.id = f.mission_id "
    "join drones d on d.id = m.drone_id "
    "left join incident_acknowledgements a on a.mission_id = f.mission_id "
    "where f.phase='EMERGENCY' and f.emergency_at is not null"
)
GROUNDED_HERE = (
    "d.status='MAINTENANCE' and abs(d.longitude-f.longitude) <= 1e-9 "
    "and abs(d.latitude-f.latitude) <= 1e-9"
)
GROUNDED_SQL = f"select count(*) {GROUNDED_JOIN} and {GROUNDED_HERE}"
RECOVERED_SQL = (
    f"select count(*) {GROUNDED_JOIN} and not ({GROUNDED_HERE}) and a.mission_id is null"
)


def _drone(session: Session, drone_id: str) -> Drone:
    found = session.get(Drone, drone_id)
    assert found is not None
    return found


def _order(order_id: str, status: str) -> DeliveryOrder:
    return DeliveryOrder(
        id=order_id,
        origin_hub_id="hub-forum-gdansk",
        destination_address="x",
        destination_longitude=18.6,
        destination_latitude=54.3,
        package_weight_kg=1.0,
        status=status,
    )


def _ago(**kwargs: float) -> datetime:
    return NOW - timedelta(**kwargs)


def _populate(session: Session) -> None:
    _drone(session, "DRN-001").status = "IN_FLIGHT"  # emergency approach
    add_mission(session, "MIS-QA-APP", "DRN-001", status=MissionStatus.IN_FLIGHT)
    add_flight(session, "MIS-QA-APP", phase="EMERGENCY_APPROACH", failed_at=_ago(seconds=30))
    grounded = _drone(session, "DRN-004")  # grounded by a failure, unacknowledged
    grounded.status, grounded.longitude, grounded.latitude = "MAINTENANCE", 18.60, 54.40
    add_mission(session, "MIS-QA-GND", "DRN-004", status=MissionStatus.EMERGENCY)
    add_flight(
        session, "MIS-QA-GND", phase="EMERGENCY", failed_at=NOW, emergency_at=_ago(minutes=5),
        emergency_reason="DRONE_FAILURE", longitude=18.60, latitude=54.40,
    )  # fmt: skip
    battery = _drone(session, "DRN-002")  # grounded by a battery emergency, acknowledged
    battery.status, battery.longitude, battery.latitude = "MAINTENANCE", 18.61, 54.41
    add_mission(session, "MIS-QA-BAT", "DRN-002", status=MissionStatus.EMERGENCY)
    add_flight(
        session, "MIS-QA-BAT", phase="EMERGENCY", emergency_at=_ago(minutes=20),
        emergency_reason="BATTERY_CRITICAL", longitude=18.61, latitude=54.41,
    )  # fmt: skip
    session.add(IncidentAcknowledgement(mission_id="MIS-QA-BAT", acknowledged_at=NOW))
    add_mission(session, "MIS-QA-REC", "DRN-007", status=MissionStatus.EMERGENCY)  # recovered
    add_flight(
        session, "MIS-QA-REC", phase="EMERGENCY", failed_at=NOW, emergency_at=_ago(hours=3),
        emergency_reason="DRONE_FAILURE", longitude=18.62, latitude=54.42,
    )  # fmt: skip
    add_mission(session, "MIS-QA-OLD", "DRN-010", status=MissionStatus.EMERGENCY)  # history
    add_flight(
        session, "MIS-QA-OLD", phase="EMERGENCY", failed_at=NOW, emergency_at=_ago(days=1),
        emergency_reason="DRONE_FAILURE", longitude=18.63, latitude=54.43,
    )  # fmt: skip
    session.add(IncidentAcknowledgement(mission_id="MIS-QA-OLD", acknowledged_at=NOW))
    # orders: one really in delivery, two interrupted (one inside the 60-minute window)
    _drone(session, "DRN-005").status = "IN_FLIGHT"
    session.add_all(
        [
            _order("ORD-QA-DEL", "OUT_FOR_DELIVERY"),
            _order("ORD-QA-INT", "OUT_FOR_DELIVERY"),
            _order("ORD-QA-OLDI", "OUT_FOR_DELIVERY"),
        ]
    )
    session.flush()
    add_mission(
        session, "MIS-QA-DEL", "DRN-005", status=MissionStatus.IN_FLIGHT, order_id="ORD-QA-DEL"
    )
    add_flight(session, "MIS-QA-DEL", phase="OUTBOUND")
    for mission, drone_id, order, ended in (
        ("MIS-QA-INT", "DRN-008", "ORD-QA-INT", _ago(minutes=10)),
        ("MIS-QA-OLDI", "DRN-009", "ORD-QA-OLDI", _ago(hours=2)),
    ):
        add_mission(session, mission, drone_id, status=MissionStatus.EMERGENCY, order_id=order)
        add_flight(
            session, mission, phase="EMERGENCY", failed_at=ended, ended_at=ended,
            emergency_at=ended,
            emergency_reason="DRONE_FAILURE", longitude=18.9, latitude=54.9,
        )  # fmt: skip
        session.add(IncidentAcknowledgement(mission_id=mission, acknowledged_at=NOW))
    session.add(
        LprScenario(
            id="LPR-QA", status="ACTIVE", origin="MANUAL", started_at=_ago(minutes=1),
            ends_at=NOW + timedelta(minutes=2), start_longitude=18.5, start_latitude=54.39,
            end_longitude=18.7, end_latitude=54.39, speed_ms=80.0, radius_m=500.0, margin_m=50.0,
            clear_extra_m=50.0,
        )
    )  # fmt: skip
    weather = session.get(WeatherState, "rain-warning")
    assert weather is not None  # seeded INACTIVE by migration 0016
    weather.active, weather.activated_at = True, _ago(minutes=2)


# --- Gate C1: Feature 024 protections with real concurrency ----


def test_racing_questions_make_exactly_one_provider_request(
    factory: sessionmaker[Session], settings: Settings
) -> None:
    transport = FakeTransport()
    gateway = AiGateway(settings, transport, SqlBudgetStore(factory), clock=Clock(GATEWAY_START))
    barrier = threading.Barrier(8)

    def ask(_: int) -> object:
        barrier.wait(timeout=30)
        try:
            return ask_fleet_question(
                "How many drones are charging?",
                gateway=gateway,
                factory=factory,
                settings=settings,
                now=NOW,
            )
        except AiError as error:
            return error

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(ask, range(8)))

    answers = [r for r in results if isinstance(r, FleetAnswer)]
    refusals = [r for r in results if isinstance(r, AiError)]
    assert len(answers) == 1 and len(transport.requests) == 1  # one provider call in total
    assert len(refusals) == 7
    assert all(isinstance(r, ConcurrencyLimitError | TooSoonError) for r in refusals)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AiRequestLog)) == 1
        state = session.get(AiBudgetState, "anthropic")
    assert state is not None and state.reserved_nano_usd == 0 and not state.halted


# --- Gate C1: a failed snapshot never leaves the pooled connection changed -----------------------


def test_failed_snapshots_do_not_contaminate_the_connection_pool(
    factory: sessionmaker[Session], settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = list_hubs

    def slow(session: Session):  # type: ignore[no-untyped-def]
        session.execute(text("select pg_sleep(1)"))
        return real(session)

    monkeypatch.setattr(snapshot, "STATEMENT_TIMEOUT_MS", 50)
    monkeypatch.setattr(snapshot, "list_hubs", slow)
    for _ in range(25):  # more failures than the pool has connections (20)
        with pytest.raises(DBAPIError):
            build_fleet_context(factory, settings, NOW)
    monkeypatch.undo()

    seen: set[tuple[object, object, object]] = set()
    for _ in range(25):  # every pooled connection is checked, none stayed read-only or timed out
        with factory() as ordinary:
            seen.add(
                (
                    ordinary.execute(text("show transaction_read_only")).scalar(),
                    ordinary.execute(text("show transaction_isolation")).scalar(),
                    ordinary.execute(text("show statement_timeout")).scalar(),
                )
            )
    assert seen == {("off", "read committed", "0")}
    assert build_fleet_context(factory, settings, NOW).summary.drones_total == 12  # still works

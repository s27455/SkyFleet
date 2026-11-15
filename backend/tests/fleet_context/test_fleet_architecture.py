"""Structural rules of Feature 025, checked on the source: read-only by construction, no wiring."""

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
PACKAGE = APP / "fleet_context"

# The ONLY names the package may import from the rest of the application. Everything here reads:
# models, pure functions, or queries. No service that writes, locks or starts anything is listed.
ALLOWED_IMPORTS: dict[str, set[str]] = {
    "app.config": {"Settings"},
    "app.dispatch.models": {"AUTO_DISPATCH", "DispatchAutoState"},
    "app.dispatch.service": {"active_claims", "available_drones_by_hub"},
    "app.drones.models": {"Drone", "DroneModel", "DroneStatus"},
    "app.hubs.repository": {"list_hubs"},
    "app.missions.models": {"ACTIVE_MISSION_STATUSES", "Mission"},
    "app.missions.presence": {"docked_hub", "hub_occupancy"},
    "app.orders.models": {
        "ORDER_SIMULATION",
        "DeliveryOrder",
        "OrderSimulationState",
        "OrderStatus",
    },
    "app.simulation.clock": {"as_utc", "utcnow"},
    "app.simulation.heartbeat": {"is_fresh", "last_heartbeat"},
    "app.simulation.lpr": {"active_scenario", "is_yielding"},
    "app.simulation.models": {
        "RANDOM_INCIDENTS",
        "EmergencyReason",
        "FlightPhase",
        "IncidentAcknowledgement",
        "IncidentSchedulerState",
        "MissionFlight",
    },
    "app.simulation.recovery": {"POSITION_TOLERANCE_DEG"},
    "app.weather.service": {"get_status"},
}
# Only these two modules talk to the AI package, and only through these names.
AI_IMPORTS: dict[str, set[str]] = {
    "app.ai.errors": {"AiError", "AiDisabledError", "InvalidQuestionError"},
    "app.ai.gateway": {"AiGateway"},
    "app.ai.request": {"SYSTEM_PROMPT", "build_user_content", "prepare_request"},
    "app.ai.types": {"AiAnswer"},
}
AI_IMPORTERS = {"errors.py", "question.py", "service.py"}
SQLALCHEMY_ALLOWED = {
    "sqlalchemy": {"and_", "event", "exists", "func", "select", "text"},
    "sqlalchemy.orm": {"Session", "sessionmaker"},
}
# Calls that write or lock. None may appear anywhere in the package.
FORBIDDEN_CALLS = {
    "add",
    "add_all",
    "commit",
    "flush",
    "delete",
    "merge",
    "bulk_save_objects",
    "bulk_insert_mappings",
    "bulk_update_mappings",
    "with_for_update",
    "begin_nested",
}


def python_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def tree_of(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def imports(path: Path) -> list[tuple[str, set[str]]]:
    found: list[tuple[str, set[str]]] = []
    for node in ast.walk(tree_of(path)):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append((node.module, {alias.name for alias in node.names}))
        elif isinstance(node, ast.Import):
            found.extend((alias.name, set()) for alias in node.names)
    return found


def test_the_package_imports_only_reading_code() -> None:
    offenders: list[str] = []
    for path in python_files(PACKAGE):
        for module, names in imports(path):
            if module.startswith("app.fleet_context"):
                continue
            if module in AI_IMPORTS:
                if path.name not in AI_IMPORTERS or not names <= AI_IMPORTS[module]:
                    offenders.append(f"{path.name}: {module} {sorted(names)}")
            elif module in ALLOWED_IMPORTS:
                if not names <= ALLOWED_IMPORTS[module]:
                    offenders.append(
                        f"{path.name}: {module} {sorted(names - ALLOWED_IMPORTS[module])}"
                    )
            elif module in SQLALCHEMY_ALLOWED:
                if not names <= SQLALCHEMY_ALLOWED[module]:
                    offenders.append(
                        f"{path.name}: {module} {sorted(names - SQLALCHEMY_ALLOWED[module])}"
                    )
            elif module.startswith("app."):
                offenders.append(f"{path.name}: {module}")
            elif module.split(".")[0] in {"anthropic", "httpx", "httpx2", "requests", "threading"}:
                offenders.append(f"{path.name}: {module}")

    assert offenders == []


def test_nothing_in_the_package_writes_or_locks() -> None:
    offenders = [
        f"{path.name}:{node.lineno} .{node.func.attr}()"
        for path in python_files(PACKAGE)
        for node in ast.walk(tree_of(path))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in FORBIDDEN_CALLS
    ]

    assert offenders == []


def test_the_only_raw_sql_is_the_statement_timeout() -> None:
    statements: list[str] = []
    for path in python_files(PACKAGE):
        for node in ast.walk(tree_of(path)):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "text"
            ):
                (argument,) = node.args
                assert isinstance(argument, ast.JoinedStr | ast.Constant)
                statements.append(ast.unparse(argument))

    assert len(statements) == 1 and "SET LOCAL statement_timeout" in statements[0]


def test_the_snapshot_transaction_is_read_only_repeatable_read_with_a_timeout() -> None:
    source = (PACKAGE / "snapshot.py").read_text(encoding="utf-8")

    assert '"isolation_level": "REPEATABLE READ"' in source
    assert '"postgresql_readonly": True' in source
    assert "SET LOCAL statement_timeout" in source
    assert ".commit(" not in source and "session.rollback()" in source


def test_only_the_copilot_service_imports_the_package() -> None:
    importers = [
        path.relative_to(APP).as_posix()
        for path in python_files(APP)
        if PACKAGE not in path.parents
        and any(
            m == "app.fleet_context" or m.startswith("app.fleet_context.") for m, _ in imports(path)
        )
    ]

    # Feature 026: the Copilot service is the first caller. No route, no worker, nothing else.
    assert importers == ["copilot/service.py"]


def test_only_the_orchestrator_and_its_errors_talk_to_the_ai_package() -> None:
    importers = {
        path.name
        for path in python_files(PACKAGE)
        if any(m == "app.ai" or m.startswith("app.ai.") for m, _ in imports(path))
    }

    assert importers == AI_IMPORTERS


def test_the_ai_package_still_knows_nothing_about_the_fleet() -> None:
    offenders = [
        path.name
        for path in python_files(APP / "ai")
        if any(m.startswith("app.fleet_context") for m, _ in imports(path))
    ]

    assert offenders == []


def test_the_package_adds_no_route_tool_or_migration() -> None:
    assert not (PACKAGE / "routes.py").exists() and not (PACKAGE / "router.py").exists()
    assert not list((BACKEND / "migrations" / "versions").glob("0020*"))
    assert [p.name for p in (BACKEND / "migrations" / "versions").glob("0019*")] == [
        "0019_ai_budget.py"
    ]


def test_the_orchestrator_calls_the_gateway_exactly_once_and_nothing_else_of_it() -> None:
    tree = tree_of(PACKAGE / "service.py")
    asks = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "ask"
    ]
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
    }
    loops = [n for n in ast.walk(tree) if isinstance(n, ast.For | ast.While | ast.AsyncFor)]

    assert len(asks) == 1  # one gateway request per question: no retry, no second attempt
    assert loops == []
    # it never reaches past the gateway to the transport or the budget (every Feature 024
    # control therefore stays exactly where it was)
    for forbidden in (
        "transport",
        "_transport",
        "store",
        "_store",
        "SqlBudgetStore",
        "build_gateway",
        "AnthropicTransport",
        "reserve",
        "settle_success",
        "settle_rejected",
        "settle_ambiguous",
        "halt",
    ):
        assert forbidden not in names, forbidden

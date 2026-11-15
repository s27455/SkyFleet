"""Structural rules of Feature 026, checked on the source: layers, one call, no secrets."""

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
APP = BACKEND / "app"
PACKAGE = APP / "copilot"
ROUTE = APP / "api" / "routes" / "copilot.py"
MAIN = APP / "main.py"


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


def python_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def modules(path: Path) -> set[str]:
    return {module for module, _ in imports(path)}


# --- layers ------------------------------------------------------------------------------------


def test_the_route_knows_only_the_copilot_layer() -> None:
    offenders = [
        module
        for module in modules(ROUTE)
        if module.startswith(("app.ai", "app.fleet_context", "anthropic", "httpx"))
    ]

    assert offenders == []  # it never reaches the gateway, the snapshot or the provider directly
    assert {m for m in modules(ROUTE) if m.startswith("app.")} == {
        "app.copilot.access",
        "app.copilot.schemas",
        "app.copilot.service",
        "app.db.session",
    }


def test_the_access_module_is_self_contained() -> None:
    allowed_app = {"app.config"}
    app_imports = {m for m in modules(PACKAGE / "access.py") if m.startswith("app.")}

    assert (
        app_imports <= allowed_app
    )  # no AI, no database, no snapshot: it only decides who may ask
    forbidden = {"anthropic", "httpx", "sqlalchemy", "fastapi", "requests"}
    assert not {m.split(".")[0] for m in modules(PACKAGE / "access.py")} & forbidden


def test_the_service_reaches_the_ai_and_the_fleet_context_only_through_known_names() -> None:
    allowed = {
        "app.ai.errors": {
            "AMBIGUOUS_KINDS",
            "AccountingUnavailableError",
            "AiDisabledError",
            "AiError",
            "AiHaltedError",
            "AiMisconfiguredError",
            "BudgetExhaustedError",
            "ConcurrencyLimitError",
            "ErrorBackoffError",
            "InvalidQuestionError",
            "PromptTooLargeError",
            "RateLimitedError",
            "TooSoonError",
            "UpstreamError",
        },
        "app.ai.gateway": {"AiGateway", "build_gateway"},
        "app.ai.readiness": {"config_problems"},
        "app.fleet_context.errors": {"FleetContextTooLargeError", "FleetContextUnavailableError"},
        "app.fleet_context.service": {"ask_fleet_question"},
    }
    for module, names in imports(PACKAGE / "service.py"):
        if module.startswith(("app.ai", "app.fleet_context")):
            assert module in allowed, module
            assert names <= allowed[module], (module, names - allowed[module])
    forbidden = {"anthropic", "httpx", "httpx2", "requests", "threading", "time"}
    assert not {m.split(".")[0] for m in modules(PACKAGE / "service.py")} & forbidden


def test_only_the_route_and_the_app_factory_import_the_copilot_package() -> None:
    importers = sorted(
        path.relative_to(APP).as_posix()
        for path in python_files(APP)
        if PACKAGE not in path.parents
        and any(m == "app.copilot" or m.startswith("app.copilot.") for m in modules(path))
    )

    assert importers == ["api/routes/copilot.py", "main.py"]


def test_no_worker_simulation_or_other_route_imports_the_copilot() -> None:
    offenders = [
        path.relative_to(APP).as_posix()
        for path in python_files(APP)
        if path.name != "copilot.py"
        and (
            path.parent.name in {"routes", "simulation", "dispatch", "missions"}
            or path.name == "worker.py"
        )
        and any(m.startswith("app.copilot") for m in modules(path))
    ]

    assert offenders == []


# --- one call, no loop, no write ---------------------------------------------------------------


def test_the_service_makes_one_fleet_question_call_with_no_loop_or_write() -> None:
    tree = tree_of(PACKAGE / "service.py")
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ask_fleet_question"
    ]
    loops = [n for n in ast.walk(tree) if isinstance(n, ast.For | ast.While | ast.AsyncFor)]
    writes = [
        n.func.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr in {"add", "commit", "flush", "delete", "execute", "sleep"}
    ]

    assert len(calls) == 1  # one question, one gateway call at most: no retry, no fallback
    assert loops == [] and writes == []


def test_the_route_has_one_ask_call_and_no_loop() -> None:
    tree = tree_of(ROUTE)
    asks = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "ask"
    ]
    loops = [n for n in ast.walk(tree) if isinstance(n, ast.For | ast.While | ast.AsyncFor)]

    assert len(asks) == 1 and loops == []


def test_nothing_in_the_copilot_layer_gives_the_model_a_tool_or_an_action() -> None:
    sources = "\n".join(p.read_text(encoding="utf-8") for p in [*python_files(PACKAGE), ROUTE])

    for word in ("tool_choice", "tools=", "function_call", "dispatch", "start_mission", "cancel"):
        assert word not in sources, word


# --- CORS and secrets --------------------------------------------------------------------------


def test_cors_stays_an_explicit_allow_list_with_only_the_authorization_header_added() -> None:
    source = MAIN.read_text(encoding="utf-8")

    assert 'allow_headers=["Content-Type", "Authorization"]' in source
    assert "allow_origins=settings.cors_origins" in source
    assert '"*"' not in source.split("add_middleware")[1].split("app.include_router")[0]


def test_the_token_setting_is_a_secret_that_is_never_a_frontend_variable() -> None:
    config = (APP / "config.py").read_text(encoding="utf-8")
    block = config[config.index("ai_access_token") :].split(")\n", 2)[0]

    assert "SecretStr | None" in block and "repr=False" in block
    assert "SKYFLEET_AI_ACCESS_TOKEN" in block
    frontend_env = (REPO / "frontend" / ".env.example").read_text(encoding="utf-8")
    assert "TOKEN=" not in frontend_env.replace("VITE_MAPBOX_TOKEN=", "")  # only the public map key


def test_the_server_uses_no_cookie_or_session() -> None:
    sources = "\n".join(p.read_text(encoding="utf-8") for p in [*python_files(PACKAGE), ROUTE])

    for word in ("set_cookie", "SessionMiddleware", "Cookie", "localStorage"):
        assert word not in sources, word


# --- the frontend source -----------------------------------------------------------------------

FRONTEND = REPO / "frontend" / "src"


def copilot_sources() -> dict[str, str]:
    paths = [
        FRONTEND / "api" / "copilot.ts",
        FRONTEND / "types" / "copilot.ts",
        *sorted((FRONTEND / "features" / "copilot").glob("*.ts*")),
    ]
    return {
        path.relative_to(FRONTEND).as_posix(): path.read_text(encoding="utf-8")
        for path in paths
        if ".test." not in path.name
    }


def test_the_frontend_never_stores_embeds_or_evaluates_anything_about_the_token() -> None:
    sources = copilot_sources()

    assert set(sources) == {
        "api/copilot.ts",
        "types/copilot.ts",
        "features/copilot/CopilotTab.tsx",
        "features/copilot/limitationText.ts",
        "features/copilot/useCopilot.ts",
    }
    for name, source in sources.items():
        for forbidden in (
            "localStorage",
            "sessionStorage",
            "document.cookie",
            "indexedDB",
            "import.meta.env",
            "VITE_",
            "dangerouslySetInnerHTML",
            "innerHTML",
            "eval(",
            "new Function",
            "window.location",
            "history.pushState",
        ):
            assert forbidden not in source, (name, forbidden)


def test_nothing_in_the_frontend_mentions_the_server_secrets() -> None:
    offenders = [
        path.relative_to(FRONTEND).as_posix()
        for path in FRONTEND.rglob("*")
        if path.is_file()
        and path.suffix in {".ts", ".tsx"}
        and ".test." not in path.name
        and any(
            word in path.read_text(encoding="utf-8")
            for word in ("SKYFLEET_AI_ACCESS_TOKEN", "ANTHROPIC", "sk-ant")
        )
    ]

    assert offenders == []


def test_the_frontend_sends_one_question_from_one_place_with_no_timer_or_retry() -> None:
    sources = copilot_sources()
    asks = {name: source.count("askCopilot(") for name, source in sources.items()}

    # one definition (the api module) and one call (the hook); nothing else may send a question
    assert {name: count for name, count in asks.items() if count} == {
        "api/copilot.ts": 1,
        "features/copilot/useCopilot.ts": 1,
    }
    for name in ("api/copilot.ts", "features/copilot/useCopilot.ts"):
        for forbidden in (
            "setTimeout(",
            "setInterval(",
            "AbortController",
            "requestAnimationFrame",
        ):
            assert forbidden not in sources[name], (name, forbidden)
    assert "inFlightRef" in sources["features/copilot/useCopilot.ts"]  # the double-submit guard

"""Structural rules of Feature 024, checked on the source: isolation, no wiring, no secrets."""

import ast
import re
from pathlib import Path

from app.config import Settings
from app.main import create_app

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
APP = BACKEND / "app"
AI = APP / "ai"

# Everything the AI package may import from the application. No domain module is on the list.
ALLOWED_APP_MODULES = {"ai", "config", "db"}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def python_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def test_the_ai_package_imports_no_domain_module() -> None:
    offenders: dict[str, set[str]] = {}
    for path in python_files(AI):
        bad = {
            module
            for module in imported_modules(path)
            if module.startswith("app.") and module.split(".")[1] not in ALLOWED_APP_MODULES
        }
        if bad:
            offenders[path.name] = bad

    assert (
        offenders == {}
    )  # no drones, orders, missions, simulation, events, ... : no domain access


def test_the_sdk_is_imported_by_exactly_one_module() -> None:
    importers = [
        path.relative_to(APP).as_posix()
        for path in python_files(APP)
        if any(m == "anthropic" or m.startswith("anthropic.") for m in imported_modules(path))
    ]

    assert importers == ["ai/anthropic_transport.py"]


def test_the_gateway_reaches_the_sdk_only_through_the_transport_module() -> None:
    gateway_imports = imported_modules(AI / "gateway.py")

    assert not any(m == "anthropic" or m.startswith("anthropic.") for m in gateway_imports)
    # the one SDK-bound import is deferred into build_gateway, so importing the gateway is free
    source = (AI / "gateway.py").read_text(encoding="utf-8")
    assert "from app.ai.anthropic_transport import AnthropicTransport" in source
    top_level = [
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.ImportFrom) and node.module == "app.ai.anthropic_transport"
    ]
    assert top_level == []


def test_only_the_fleet_context_package_uses_the_ai_package_yet() -> None:
    users = [
        path.relative_to(APP).as_posix()
        for path in python_files(APP)
        if AI not in path.parents
        and any(m == "app.ai" or m.startswith("app.ai.") for m in imported_modules(path))
    ]

    # Features 025 and 026: `app/fleet_context` (orchestrator, errors, question preparation) and
    # the Copilot service are the only permitted users. No route, no worker, nothing else.
    assert sorted(users) == [
        "copilot/service.py",
        "fleet_context/errors.py",
        "fleet_context/question.py",
        "fleet_context/service.py",
    ]


def test_the_application_has_no_ai_route() -> None:
    app = create_app(Settings(_env_file=None))

    paths = [getattr(route, "path", "") for route in app.routes]

    assert not any("/ai" in path or "anthropic" in path.lower() for path in paths)


def test_the_transport_gives_the_model_no_tools() -> None:
    tree = ast.parse((AI / "anthropic_transport.py").read_text(encoding="utf-8"))
    keyword_sets = [
        {keyword.arg for keyword in node.keywords}
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create"
    ]

    assert len(keyword_sets) == 1
    assert keyword_sets[0] == {"model", "max_tokens", "system", "messages", "thinking", "timeout"}


def test_no_key_shaped_secret_is_in_the_repository_sources() -> None:
    pattern = re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}")
    roots = [BACKEND / "app", BACKEND / "tests", BACKEND / "migrations", REPO / "docs"]
    roots += [REPO / "frontend" / "src", REPO / "context"]
    offenders: list[str] = []
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".md", ".ts", ".tsx", ".json"}:
                continue
            if any(part in {"node_modules", "__pycache__", ".venv"} for part in path.parts):
                continue
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if pattern.search(line) and "FAKE" not in line:  # the tests' fake key says FAKE
                    offenders.append(f"{path.relative_to(REPO)}")

    assert offenders == []


def test_the_frontend_never_mentions_the_key_or_the_provider() -> None:
    mentions = [
        path.relative_to(REPO).as_posix()
        for path in (REPO / "frontend" / "src").rglob("*")
        if path.is_file()
        and path.suffix in {".ts", ".tsx"}
        and re.search(r"ANTHROPIC|sk-ant|api\.anthropic", path.read_text(encoding="utf-8"))
    ]

    assert mentions == []


def test_real_environment_files_are_ignored_by_git() -> None:
    lines = {
        line.strip() for line in (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    }

    assert ".env" in lines and ".env.*" in lines and "!.env.example" in lines

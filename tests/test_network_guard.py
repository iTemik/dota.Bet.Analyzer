"""Guards that keep every OpenDota and Liquipedia request on the shared clients and tests offline."""

import ast
from pathlib import Path

import pytest
import requests

BACKEND = Path(__file__).parent.parent / "backend"

# Only these modules send HTTP: opendota.py (OpenDota retries + limiter), matches.py (Liquipedia limiter),
# bookmakers.py (bookmaker lines and the Winline WebSocket, one fetch per button press at most every few minutes)
HTTP_CLIENT_MODULES = {"opendota.py", "matches.py", "bookmakers.py"}
HTTP_LIBRARIES = {"requests", "urllib3", "httpx", "aiohttp", "http.client", "urllib.request", "websocket"}


def _imported_modules(path: Path) -> set[str]:
    """Top-level names of every module a Python file imports."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _http_imports(path: Path) -> set[str]:
    """The HTTP libraries (or their submodules) a Python file imports."""
    return {
        name
        for name in _imported_modules(path)
        if any(name == library or name.startswith(f"{library}.") for library in HTTP_LIBRARIES)
    }


def test_only_shared_clients_import_http_libraries():
    """A new module must call opendota.get_json/opendota_get, so its requests share the limiter and retry rules."""
    offenders = {
        path.name: sorted(_http_imports(path))
        for path in sorted(BACKEND.rglob("*.py"))
        if path.name not in HTTP_CLIENT_MODULES and _http_imports(path)
    }
    assert offenders == {}


def test_shared_clients_are_found_by_the_import_check():
    """The check above would notice requests in the client modules, so it is not passing by accident."""
    for name in HTTP_CLIENT_MODULES:
        assert "requests" in _http_imports(BACKEND / name)


def test_real_http_is_blocked_in_tests(no_real_http):
    """An unmocked request raises and is recorded, so the test fails at teardown."""
    with pytest.raises(RuntimeError, match="Real HTTP request in a test"):
        requests.get("https://api.opendota.com/api/heroes", timeout=1)
    assert no_real_http == ["https://api.opendota.com/api/heroes"]
    no_real_http.clear()  # This test expects the block, so it does not fail at teardown

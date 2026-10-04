"""Required master-export runtime contract, without host services or private data."""

import ast
import importlib.util
from pathlib import Path

from app.routers.sync import router


def test_master_export_contains_installed_worker_entrypoint():
    spec = importlib.util.find_spec("app.trading212_cli")
    assert spec is not None, "Installed unit requires python -m app.trading212_cli"
    assert spec.origin is not None
    source = Path(spec.origin).read_text()
    tree = ast.parse(source)
    functions = {
        node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert {"run", "main"} <= functions
    # The dedicated worker must not silently become the scheduled all-broker CLI.
    forbidden = {"init_db", "run_sync_all", "_run_sync_all_locked", "sync_inbox", "_fetchers"}
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not calls & forbidden


def test_master_exports_isolated_request_and_status_routes():
    routes = {(route.path, method) for route in router.routes for method in route.methods}
    assert ("/api/sync/trading212/request", "POST") in routes
    assert ("/api/sync/trading212/request", "GET") in routes

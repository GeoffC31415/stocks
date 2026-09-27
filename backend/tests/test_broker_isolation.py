"""Isolated broker boundary tests; no lifespan, real database or provider."""
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from fastapi import FastAPI

from app.database import get_session
from app.routers import sync, trading212


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/trading212/sync", "/api/trading212/sync/orders", "/api/trading212/sync/portfolio", "/api/trading212/sync/cash-flows", "/api/sync/all"])
async def test_public_broker_routes_refuse_before_dependencies(path):
    app = FastAPI()
    app.state.web_config = SimpleNamespace(deployment_mode="public", public_origin="https://example.test")
    app.include_router(trading212.router)
    app.include_router(sync.router)
    forbidden = Mock(side_effect=AssertionError("must not resolve DB/provider dependency"))
    def dependency():
        return forbidden()
    app.dependency_overrides[get_session] = dependency
    app.dependency_overrides[trading212.get_trading212_client] = dependency
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://example.test") as client:
        response = await client.post(path, headers={"Origin": "https://example.test"})
    assert response.status_code == 403
    forbidden.assert_not_called()


@pytest.mark.asyncio
async def test_worker_handoff_is_allowlisted_and_independent_of_inbox(tmp_path, monkeypatch):
    import json
    import stat
    from unittest.mock import AsyncMock

    from app.config import Settings
    from app.services import sync_runner as runner
    inbox, status = tmp_path / "private", tmp_path / "status"
    config = Settings(_env_file=None, sync_inbox=inbox, sync_status_dir=status)
    assert config.resolved_sync_status_dir() == status
    monkeypatch.setattr(runner, "settings", config)
    monkeypatch.setattr(runner, "sync_inbox", AsyncMock(return_value=SimpleNamespace(files=[])))
    async def fetch(_):
        return runner.StepResult("Barclays", "failed", "SENTINEL_SECRET")
    await runner.run_sync_all(None, include_trading212=False, fetchers=[("Barclays", fetch)])
    private = (inbox / "last-sync.json").read_text()
    published = (status / "last-sync.json").read_text()
    assert "SENTINEL_SECRET" in private and "SENTINEL_SECRET" not in published
    assert json.loads(published)["steps"][0]["detail"] is None
    assert stat.S_IMODE((status / "last-sync.json").stat().st_mode) == 0o640
    assert runner.read_last_sync() == json.loads(published)


def test_control_writes_web_private_marker_not_worker_status(tmp_path, monkeypatch):
    import json

    from app.services import sync_control as control
    status, private = tmp_path / "status", tmp_path / "web"
    status.mkdir()
    report = {"started_at": "2026-01-01T00:00:00+00:00", "steps": [], "files": []}
    (status / "last-sync.json").write_text(json.dumps(report))
    monkeypatch.setattr(control, "service_snapshot", lambda: ("inactive", None))
    monkeypatch.setattr(control.subprocess, "run", Mock())
    result = control.request_service_sync(private, status_dir=status)
    assert (private / "sync-request.json").exists()
    assert sorted(p.name for p in status.iterdir()) == ["last-sync.json"]
    assert control.service_sync_status(private, status_dir=status)["request_id"] == result["request_id"]


@pytest.mark.asyncio
async def test_public_status_route_uses_status_dir_not_inbox(tmp_path, monkeypatch):
    from app.config import Settings
    config = Settings(_env_file=None, deployment_mode="public", sync_inbox=tmp_path / "forbidden", sync_status_dir=tmp_path / "status", sync_control_dir=tmp_path / "web", sync_service_trigger_enabled=True)
    app = FastAPI()
    app.state.web_config = config
    app.include_router(sync.router)
    poll = Mock(return_value={"state": "inactive"})
    monkeypatch.setattr(sync, "service_sync_status", poll)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://example.test") as client:
        assert (await client.get("/api/sync/request")).status_code == 200
    poll.assert_called_once_with(config.resolved_sync_control_dir(), status_dir=config.resolved_sync_status_dir())

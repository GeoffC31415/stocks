"""Dedicated Trading 212 service: synthetic control, no real systemd/brokers."""

from unittest.mock import Mock

import httpx
import pytest

from app.services import sync_control as control


def test_t212_request_starts_only_fixed_service(tmp_path, monkeypatch):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return Mock(
            stdout="LoadState=loaded\nActiveState=inactive\nSubState=dead\nJob=0\nResult=success\n"
        )

    monkeypatch.setattr(control.subprocess, "run", run)
    result = control.request_service_sync(tmp_path, trading212=True)
    assert result["state"] == "accepted"
    assert calls[-1] == [*control.START_ARGV[:-1], "stocks-t212-sync.service"]
    assert all("stocks-sync.service" not in call for call in calls)


@pytest.mark.asyncio
async def test_t212_public_request_has_no_database_dependency(tmp_path, monkeypatch):
    import app.routers.sync as routes
    from app.config import Settings
    from app.database import get_session
    from app.main import create_app
    from app.security import hash_password

    config = Settings(
        _env_file=None,
        deployment_mode="public",
        public_origin="https://example.test",
        auth_username="owner",
        auth_password_hash=hash_password("test-password"),
        sync_inbox=tmp_path,
        sync_service_trigger_enabled=True,
    )
    controller = Mock(return_value={"state": "accepted", "request_id": "new"})
    monkeypatch.setattr(routes, "request_service_sync", controller)
    app = create_app(config)

    async def forbidden():
        raise AssertionError("must not open database")
        yield

    app.dependency_overrides[get_session] = forbidden
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://example.test",
        auth=("owner", "test-password"),
    ) as client:
        for suffix, body, origin, status in [
            ("", b"", "https://example.test", 202),
            ("?unit=evil", b"", "https://example.test", 400),
            ("", b"{}", "https://example.test", 400),
            ("", b"", "https://evil.test", 403),
        ]:
            response = await client.post(
                "/api/sync/trading212/request" + suffix, content=body, headers={"Origin": origin}
            )
            assert response.status_code == status
        assert (
            await client.post("/api/trading212/sync", headers={"Origin": "https://example.test"})
        ).status_code == 403
        assert (
            await client.post(
                "/api/sync/trading212/request",
                headers=[("Origin", "https://example.test"), ("Origin", "https://example.test")],
            )
        ).status_code == 403
        assert (
            await client.post(
                "/api/sync/trading212/request",
                auth=None,
                headers={"Origin": "https://example.test"},
            )
        ).status_code == 401
    assert config.trading212_api_key is None and config.trading212_api_secret is None
    controller.assert_called_once_with(
        config.resolved_sync_control_dir() / "trading212",
        status_dir=config.resolved_sync_status_dir() / "trading212",
        trading212=True,
    )


@pytest.mark.asyncio
async def test_t212_worker_never_fetches_or_imports_other_brokers(tmp_path, monkeypatch):
    from contextlib import asynccontextmanager

    from app import trading212_cli as worker
    from app.services.sync_freshness import verified_sections
    from app.services.sync_runner import StepResult

    monkeypatch.setattr(worker.settings, "sync_inbox", tmp_path / "inbox")
    monkeypatch.setattr(worker.settings, "sync_status_dir", tmp_path / "public/trading212")

    @asynccontextmanager
    async def sessions():
        yield Mock()

    monkeypatch.setattr(worker, "SessionLocal", sessions)

    async def step(session, **kwargs):
        return StepResult(
            "Trading 212",
            "unchanged",
            sections=verified_sections(
                {
                    "holdings": "unchanged",
                    "orders": "unchanged",
                    "cash": "unchanged",
                    "transactions": "ok",
                },
                "2026-10-04T12:00:00+00:00",
                "2026-10-04",
                coverage=dict.fromkeys(["holdings", "orders", "cash", "transactions"], "complete"),
            ),
        )

    monkeypatch.setattr(worker, "_trading212_step", step)
    assert await worker.run() == 0
    import json

    report = json.loads((tmp_path / "public/trading212/last-sync.json").read_text())
    assert report["ok"] is True
    assert [step["name"] for step in report["steps"]] == ["Trading 212"]
    assert report["files"] == []
    assert not (tmp_path / "public/last-sync.json").exists()
    # Request/status consumer reads this exact Trading 212 namespace, not the daily report.
    monkeypatch.setattr(control, "service_snapshot", lambda **kwargs: ("inactive", None))
    control_dir = tmp_path / "control/trading212"
    control.atomic_json(
        control_dir / "sync-request.json",
        {
            "request_id": "synthetic-request",
            "requested_at": 1,
            "state": "accepted",
            "target_started_at": report["started_at"],
        },
    )
    status = control.service_sync_status(
        control_dir, status_dir=tmp_path / "public/trading212", trading212=True
    )
    assert status["state"] == "completed"
    assert status["request_id"] == "synthetic-request"
    assert status["last_run"]["steps"][0]["detail"] is None
    with control.file_lock(tmp_path / "inbox/sync-run.lock"):
        assert await worker.run() == 1


@pytest.mark.asyncio
async def test_t212_missing_credentials_is_a_terminal_failure(tmp_path, monkeypatch):
    from contextlib import asynccontextmanager

    from app import trading212_cli as worker
    from app.services.sync_runner import StepResult

    monkeypatch.setattr(worker.settings, "sync_inbox", tmp_path / "inbox")
    monkeypatch.setattr(worker.settings, "sync_status_dir", tmp_path / "public/trading212")

    @asynccontextmanager
    async def sessions():
        yield Mock()

    monkeypatch.setattr(worker, "SessionLocal", sessions)

    async def step(*args, **kwargs):
        return StepResult("Trading 212", "skipped", "no API credentials")

    monkeypatch.setattr(worker, "_trading212_step", step)
    assert await worker.run() == 1
    import json

    assert json.loads((tmp_path / "public/trading212/last-sync.json").read_text())["ok"] is False

"""Synthetic service-control tests: never invoke systemctl or a broker."""

from unittest.mock import Mock

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.security import hash_password


@pytest.fixture
def public_config(tmp_path):
    return Settings(
        _env_file=None,
        deployment_mode="public",
        public_origin="https://example.test",
        auth_username="owner",
        auth_password_hash=hash_password("test-password"),
        sync_inbox=tmp_path,
        sync_service_trigger_enabled=True,
    )


@pytest.mark.asyncio
async def test_authenticated_request_has_no_database_dependency(public_config, monkeypatch):
    import app.routers.sync as routes

    controller = Mock(return_value={"state": "accepted", "request_id": "synthetic"})
    monkeypatch.setattr(routes, "request_service_sync", controller, raising=False)
    app = create_app(public_config)
    from app.database import get_session

    async def forbidden():
        raise AssertionError("no database allowed")
        yield

    app.dependency_overrides[get_session] = forbidden
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://example.test"
    ) as client:
        response = await client.post(
            "/api/sync/request",
            auth=("owner", "test-password"),
            headers={"Origin": "https://example.test"},
        )
    assert response.status_code == 202
    assert response.json()["state"] == "accepted"
    controller.assert_called_once_with(public_config.resolved_sync_inbox())


def test_start_uses_fixed_nonblocking_argv(tmp_path, monkeypatch):
    from app.services import sync_control as control

    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return Mock(
            returncode=0,
            stdout="LoadState=loaded\nActiveState=inactive\nSubState=dead\nJob=0\nResult=success\n",
        )

    monkeypatch.setattr(control.subprocess, "run", run)
    result = control.request_service_sync(tmp_path)
    assert result["state"] == "accepted"
    assert result["request_id"]
    assert calls[-1][0] == [
        "/usr/bin/systemctl",
        "--no-ask-password",
        "--no-block",
        "--job-mode=fail",
        "start",
        "stocks-sync.service",
    ]
    assert all(c[1]["timeout"] <= 5 and not c[1].get("shell") for c in calls)


@pytest.mark.parametrize(
    "active,job,expected",
    [
        ("inactive", "0", "accepted"),
        ("activating", "7", "running"),
        ("active", "0", "running"),
        ("inactive", "7", "running"),
        ("failed", "0", "accepted"),
        ("deactivating", "0", "unknown"),
    ],
)
def test_service_state_and_persistent_cooldown(tmp_path, monkeypatch, active, job, expected):
    from app.services import sync_control as control

    run = Mock(
        return_value=Mock(
            returncode=0,
            stdout=f"LoadState=loaded\nActiveState={active}\nSubState=dead\nJob={job}\nResult=success\n",
        )
    )
    monkeypatch.setattr(control.subprocess, "run", run)
    first = control.request_service_sync(tmp_path)
    assert first["state"] == expected
    second = control.request_service_sync(tmp_path)
    starts = [call for call in run.call_args_list if "start" in call.args[0]]
    assert len(starts) == (1 if expected == "accepted" else 0)
    if expected != "unknown":
        assert first["request_id"] == second["request_id"]


@pytest.mark.parametrize(
    "auth,origin,path,body,enabled,code",
    [
        (None, "https://example.test", "/request", b"", True, 401),
        (("owner", "test-password"), None, "/request", b"", True, 403),
        (("owner", "test-password"), "https://evil.test", "/request", b"", True, 403),
        (("owner", "test-password"), "https://example.test:444", "/request", b"", True, 403),
        (("owner", "test-password"), "https://example.test", "/request", b"", False, 403),
        (("owner", "test-password"), "https://example.test", "/all", b"", True, 403),
        (("owner", "test-password"), "https://example.test", "/request?unit=evil", b"", True, 400),
        (("owner", "test-password"), "https://example.test", "/request", b"{}", True, 400),
    ],
)
@pytest.mark.asyncio
async def test_denied_requests_never_call_controller(
    public_config, monkeypatch, auth, origin, path, body, enabled, code
):
    import app.routers.sync as routes

    public_config.sync_service_trigger_enabled = enabled
    controller = Mock(side_effect=AssertionError("must not call controller"))
    monkeypatch.setattr(routes, "request_service_sync", controller)
    app = create_app(public_config)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://example.test"
    ) as client:
        response = await client.post(
            "/api/sync" + path,
            auth=auth,
            headers={"Origin": origin} if origin else {},
            content=body,
        )
    assert response.status_code == code
    controller.assert_not_called()


def test_active_service_cannot_complete_from_previous_correlated_report(tmp_path, monkeypatch):
    from app.services import sync_control as control

    monkeypatch.setattr(control, "service_state", lambda: "running")
    report = {
        "started_at": "2026-01-01T00:00:00+00:00",
        "finished_at": "2026-01-01T00:01:00+00:00",
        "ok": True,
    }
    control.atomic_json(tmp_path / "last-sync.json", report)
    control.atomic_json(
        tmp_path / "sync-request.json",
        {"request_id": "old", "requested_at": 1, "baseline_started_at": None, "state": "accepted"},
    )
    assert control.service_sync_status(tmp_path)["state"] == "running"


def test_corrupt_cooldown_fails_closed(tmp_path, monkeypatch):
    from app.services import sync_control as control

    monkeypatch.setattr(control, "service_snapshot", lambda: ("inactive", None))
    run = Mock(side_effect=AssertionError("must not start"))
    monkeypatch.setattr(control.subprocess, "run", run)
    (tmp_path / "sync-request.json").write_text("not-json")
    assert control.request_service_sync(tmp_path)["state"] == "unknown"
    run.assert_not_called()


def test_inactive_real_systemd_has_empty_job_property(monkeypatch):
    from app.services import sync_control as control

    monkeypatch.setattr(
        control.subprocess,
        "run",
        Mock(
            return_value=Mock(
                stdout="LoadState=loaded\nActiveState=inactive\nSubState=dead\nJob=\nResult=success\n"
            )
        ),
    )
    assert control.service_state() == "inactive"


def test_running_new_job_does_not_reuse_completed_request(tmp_path, monkeypatch):
    from app.services import sync_control as control

    monkeypatch.setattr(control, "service_snapshot", lambda: ("running", None))
    control.atomic_json(
        tmp_path / "last-sync.json",
        {
            "started_at": "2020-01-01T00:00:00+00:00",
            "finished_at": "2020-01-01T00:01:00+00:00",
            "ok": True,
        },
    )
    control.atomic_json(
        tmp_path / "sync-request.json",
        {"request_id": "old", "requested_at": 1, "baseline_started_at": None, "state": "accepted"},
    )
    requested = control.request_service_sync(tmp_path)
    assert requested["request_id"] != "old"
    monkeypatch.setattr(control, "service_state", lambda: "inactive")
    status = control.service_sync_status(tmp_path)
    assert status["state"] != "completed"
    assert status["last_run"] is None


def test_failed_new_request_does_not_expose_old_success_as_completion(tmp_path, monkeypatch):
    from app.services import sync_control as control

    monkeypatch.setattr(control, "service_state", lambda: "failed")
    control.atomic_json(
        tmp_path / "last-sync.json",
        {
            "started_at": "2020-01-01T00:00:00+00:00",
            "finished_at": "2020-01-01T00:01:00+00:00",
            "ok": True,
        },
    )
    control.atomic_json(
        tmp_path / "sync-request.json",
        {
            "request_id": "new",
            "requested_at": 2000000000,
            "baseline_started_at": "2020-01-01T00:00:00+00:00",
            "state": "accepted",
        },
    )
    status = control.service_sync_status(tmp_path)
    assert status["state"] == "failed"
    assert status["last_run"] is None


@pytest.mark.parametrize("outcome", ["ok", "failed", "no-report"])
def test_running_invocation_finishes_between_service_and_report_reads(
    tmp_path, monkeypatch, outcome
):
    from app.services import sync_control as control

    current_id = "a" * 32
    old = {
        "started_at": "2020-01-01T00:00:00+00:00",
        "finished_at": "2020-01-01T00:01:00+00:00",
        "invocation_id": "b" * 32,
        "ok": True,
    }
    control.atomic_json(tmp_path / "last-sync.json", old)
    calls = []

    def show(argv, **kwargs):
        assert "start" not in argv
        calls.append(argv)
        if len(calls) == 1:
            # Snapshot sees the running job; its report finishes before read_json.
            if outcome != "no-report":
                control.atomic_json(tmp_path / "last-sync.json", {
                    **old,
                    "started_at": "2020-01-02T00:00:00+00:00",
                    "finished_at": "2020-01-02T00:01:00+00:00",
                    "invocation_id": current_id,
                    "ok": outcome == "ok",
                })
            active = "activating"
        else:
            active = "inactive" if outcome == "ok" else "failed"
        return Mock(stdout=(
            f"LoadState=loaded\nActiveState={active}\nJob=0\nInvocationID={current_id}\n"
        ))

    monkeypatch.setattr(control.subprocess, "run", show)
    requested = control.request_service_sync(tmp_path)
    assert requested["state"] == "running"
    status = control.service_sync_status(tmp_path)
    assert status["request_id"] == requested["request_id"]
    assert status["state"] == ("completed" if outcome == "ok" else "failed")
    if outcome == "no-report":
        assert status["last_run"] is None
    else:
        assert status["last_run"]["ok"] is (outcome == "ok")
    assert "invocation_id" not in str(status)
    assert current_id not in str(status)


def test_reused_pending_request_binds_to_observed_invocation(tmp_path, monkeypatch):
    from app.services import sync_control as control

    current_id = "c" * 32
    old = {
        "started_at": "2020-01-01T00:00:00+00:00",
        "finished_at": None,
        "invocation_id": "b" * 32,
        "ok": True,
    }
    control.atomic_json(tmp_path / "last-sync.json", old)
    control.atomic_json(tmp_path / "sync-request.json", {
        "request_id": "pending",
        "requested_at": control.time.time(),
        "baseline_started_at": old["started_at"],
        "target_started_at": old["started_at"],
        "state": "running",
    })
    monkeypatch.setattr(control, "service_snapshot", lambda: ("running", current_id))
    requested = control.request_service_sync(tmp_path)
    assert requested["request_id"] == "pending"
    # A stale, unrelated report finishes while the current job fails before reporting.
    control.atomic_json(tmp_path / "last-sync.json", {
        **old, "finished_at": "2020-01-01T00:01:00+00:00",
    })
    monkeypatch.setattr(control, "service_snapshot", lambda: ("failed", None))
    status = control.service_sync_status(tmp_path)
    assert status["state"] == "failed"
    assert status["last_run"] is None


def test_trigger_defaults_disabled():
    assert Settings(_env_file=None).sync_service_trigger_enabled is False


def test_poll_ignores_previous_report_and_sanitizes_new_report(tmp_path, monkeypatch):
    from app.services import sync_control as control

    monkeypatch.setattr(
        control.subprocess,
        "run",
        Mock(return_value=Mock(stdout="LoadState=loaded\nActiveState=inactive\nJob=0\n")),
    )
    old = {
        "started_at": "2020-01-01T00:00:00+00:00",
        "finished_at": "2020-01-01T00:01:00+00:00",
        "ok": True,
        "steps": [],
        "files": [],
    }
    control.atomic_json(tmp_path / "last-sync.json", old)
    requested = control.request_service_sync(tmp_path)
    status = control.service_sync_status(tmp_path)
    assert status["request_id"] == requested["request_id"]
    assert status["state"] == "accepted"  # never complete based on yesterday's report
    import datetime as dt

    new = {
        **old,
        "started_at": dt.datetime.now(dt.UTC).isoformat(),
        "finished_at": dt.datetime.now(dt.UTC).isoformat(),
        "steps": [{"name": "Barclays", "status": "failed", "detail": "/private/token"}],
        "files": [{"filename": "/private/export.xls", "status": "failed", "detail": "secret"}],
        "ok": False,
    }
    control.atomic_json(tmp_path / "last-sync.json", new)
    status = control.service_sync_status(tmp_path)
    assert status["state"] == "failed"
    assert "/private" not in str(status) and "secret" not in str(status)
    assert status["last_run"]["steps"][0]["status"] == "failed"
    monkeypatch.setattr(control.time, "time", lambda: 9999999999)
    control.atomic_json(tmp_path / "last-sync.json", old)
    assert control.service_sync_status(tmp_path)["state"] == "unknown"


@pytest.mark.parametrize(
    "error", [OSError("private"), __import__("subprocess").TimeoutExpired("private", 5)]
)
def test_command_failures_are_opaque_and_cooldown_survives(tmp_path, monkeypatch, error):
    from app.services import sync_control as control

    show = Mock(stdout="LoadState=loaded\nActiveState=inactive\nJob=0\n")
    run = Mock(side_effect=[show, error, show])
    monkeypatch.setattr(control.subprocess, "run", run)
    result = control.request_service_sync(tmp_path)
    assert result["state"] == "unknown"
    assert "private" not in str(result)
    assert control.request_service_sync(tmp_path)["request_id"] == result["request_id"]
    assert run.call_count == 3


@pytest.mark.asyncio
async def test_poll_has_no_database_dependency(public_config, monkeypatch):
    import app.routers.sync as routes

    poll = Mock(return_value={"state": "unknown", "request_id": None, "last_run": None})
    monkeypatch.setattr(routes, "service_sync_status", poll, raising=False)
    app = create_app(public_config)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://example.test"
    ) as client:
        response = await client.get("/api/sync/request", auth=("owner", "test-password"))
    assert response.status_code == 200
    assert response.json()["state"] == "unknown"
    poll.assert_called_once()

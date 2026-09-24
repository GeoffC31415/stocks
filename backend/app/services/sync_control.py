"""Fixed systemd control; no database, provider configuration or broker imports."""

from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

START_ARGV = [
    "/usr/bin/systemctl",
    "--no-ask-password",
    "--no-block",
    "--job-mode=fail",
    "start",
    "stocks-sync.service",
]
SHOW_ARGV = [
    "/usr/bin/systemctl",
    "--no-ask-password",
    "show",
    "stocks-sync.service",
    "--property=LoadState,ActiveState,SubState,Job,Result,InvocationID",
]
COOLDOWN_SECONDS = 60
PENDING_SECONDS = 20 * 60


class SyncBusy(Exception):
    """Another process owns the stable lock inode."""


@contextmanager
def file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Never unlink or replace this inode, including after a crash.
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SyncBusy("A sync is already running.") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def validated_invocation_id(value: str | None) -> str | None:
    return value if value and re.fullmatch(r"[0-9a-f]{32}", value) else None


def service_snapshot() -> tuple[str, str | None]:
    try:
        result = subprocess.run(SHOW_ARGV, timeout=5, check=True, capture_output=True, text=True)
        props = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        if props.get("LoadState") != "loaded":
            return "unknown", None
        active, job = props.get("ActiveState"), props.get("Job", "")
        if active in {"active", "activating", "reloading"}:
            return "running", validated_invocation_id(props.get("InvocationID"))
        if job.isdigit() and int(job) > 0:
            # An inactive unit with a queued job can still expose the OLD ID.
            return "running", None
        if "Job" not in props or job not in {"", "0"}:
            return "unknown", None
        return (active if active in {"inactive", "failed"} else "unknown"), None
    except (OSError, subprocess.SubprocessError):
        return "unknown", None


def service_state() -> str:
    return service_snapshot()[0]


def _timestamp(value) -> float:
    try:
        return dt.datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError, OverflowError):
        return 0


def public_report(report: dict | None) -> dict | None:
    if not report or not _timestamp(report.get("started_at")):
        return None
    names = {"Barclays", "Hargreaves Lansdown", "Trading 212", "Import files"}
    statuses = {
        "ok",
        "unchanged",
        "skipped",
        "failed",
        "needs_attention",
        "imported",
        "rejected",
        "new",
    }
    return {
        "started_at": dt.datetime.fromtimestamp(
            _timestamp(report["started_at"]), dt.UTC
        ).isoformat(),
        "finished_at": dt.datetime.fromtimestamp(
            _timestamp(report["finished_at"]), dt.UTC
        ).isoformat()
        if _timestamp(report.get("finished_at"))
        else None,
        "ok": report.get("ok") is True,
        "steps": [
            {
                "name": s["name"] if s.get("name") in names else "Sync step",
                "status": s.get("status") if s.get("status") in statuses else "unknown",
                "detail": None,
            }
            for s in report.get("steps", [])
            if isinstance(s, dict)
        ],
        "files": [
            {
                "filename": "Export",
                "kind": None,
                "as_of": None,
                "detail": None,
                "status": f.get("status") if f.get("status") in statuses else "unknown",
            }
            for f in report.get("files", [])
            if isinstance(f, dict)
        ],
    }


def _correlated(marker: dict, report: dict | None) -> bool:
    invocation_id = marker.get("target_invocation_id")
    if invocation_id:
        # Never fall back to timestamps when bound to a specific service run.
        return bool(report and report.get("invocation_id") == invocation_id)
    started = report.get("started_at") if report else None
    return bool(
        started
        and (
            started == marker.get("target_started_at")
            or (
                started != marker.get("baseline_started_at")
                and _timestamp(started) >= marker["requested_at"]
            )
        )
    )


def service_sync_status(inbox: Path) -> dict:
    state = service_state()
    marker = read_json(inbox / "sync-request.json")
    report = read_json(inbox / "last-sync.json")
    result = {
        "state": state,
        "request_id": marker.get("request_id") if marker else None,
        "last_run": public_report(report),
    }
    if not marker:
        return result
    correlated = _correlated(marker, report)
    result["last_run"] = public_report(report) if correlated else None
    if state == "running":
        result["state"] = "running"
    elif correlated and report and report.get("finished_at"):
        result["state"] = "completed" if report.get("ok") is True else "failed"
    elif state == "failed":
        result["state"] = "failed"
    elif (
        state == "unknown"
        or marker["state"] == "unknown"
        or time.time() - marker["requested_at"] > PENDING_SECONDS
    ):
        result["state"] = "unknown"
    else:
        result["state"] = "accepted"
    return result


def request_service_sync(inbox: Path) -> dict:
    try:
        with file_lock(inbox / "sync-request.lock"):
            state, invocation_id = service_snapshot()
            if state == "unknown":
                return {"state": "unknown", "request_id": None}
            path = inbox / "sync-request.json"
            previous = read_json(path)
            if path.exists() and (
                not previous
                or not isinstance(previous.get("requested_at"), (int, float))
                or not previous.get("request_id")
            ):
                return {"state": "unknown", "request_id": None}
            now = time.time()
            report = read_json(inbox / "last-sync.json") or {}
            if previous:
                recent = now - previous["requested_at"] < COOLDOWN_SECONDS
                related = _correlated(previous, report)
                finished_previous = related and bool(report.get("finished_at"))
                same_invocation = (
                    not invocation_id
                    or not previous.get("target_invocation_id")
                    or previous["target_invocation_id"] == invocation_id
                )
                reuse_running = (
                    state == "running" and same_invocation
                    and not finished_previous and (recent or related)
                )
                if reuse_running or (state != "running" and recent):
                    if reuse_running and invocation_id:
                        previous["target_invocation_id"] = invocation_id
                        atomic_json(path, previous)
                    return {
                        "state": "running" if state == "running" else previous["state"],
                        "request_id": previous["request_id"],
                    }
            marker = {
                "request_id": uuid.uuid4().hex,
                "requested_at": now,
                "baseline_started_at": report.get("started_at"),
                "target_invocation_id": invocation_id,
                "target_started_at": report.get("started_at")
                if state == "running" and not report.get("finished_at")
                else None,
                "state": "running" if state == "running" else "accepted",
            }
            # Persist before issuing the command: a timeout is ambiguous and must
            # not let subsequent requests restart the service repeatedly.
            atomic_json(path, marker)
            if state != "running":
                try:
                    subprocess.run(
                        START_ARGV, timeout=5, check=True, capture_output=True, text=True
                    )
                except (OSError, subprocess.SubprocessError):
                    marker["state"] = "unknown"
                    atomic_json(path, marker)
            return {"state": marker["state"], "request_id": marker["request_id"]}
    except SyncBusy:
        return {"state": "busy", "request_id": None}

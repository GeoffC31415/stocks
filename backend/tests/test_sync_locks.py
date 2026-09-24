"""Real flock tests use temporary stable inodes; import/network work is mocked."""

import argparse
import json
import multiprocessing
from unittest.mock import AsyncMock, Mock

import pytest

from app.config import settings
from app.services import sync_control as control
from app.services import sync_runner as runner


def _lock_attempt(path, connection):
    try:
        with control.file_lock(path):
            connection.send("acquired")
    except control.SyncBusy:
        connection.send("busy")
    finally:
        connection.close()


def test_multiprocess_lock_and_crash_release_stable_inode(tmp_path):
    path = tmp_path / "sync-run.lock"
    ctx = multiprocessing.get_context("fork")
    with control.file_lock(path):
        inode = path.stat().st_ino
        parent, child = ctx.Pipe()
        process = ctx.Process(target=_lock_attempt, args=(path, child))
        process.start()
        assert parent.poll(5) and parent.recv() == "busy"
        process.join(5)
        assert process.exitcode == 0
    with control.file_lock(path):
        assert path.stat().st_ino == inode


def _hold_and_crash(path, connection):
    import os

    with control.file_lock(path):
        connection.send("acquired")
        os._exit(1)


def test_crash_releases_lock_without_unlinking(tmp_path):
    path = tmp_path / "sync-run.lock"
    ctx = multiprocessing.get_context("fork")
    parent, child = ctx.Pipe()
    process = ctx.Process(target=_hold_and_crash, args=(path, child))
    process.start()
    assert parent.poll(5) and parent.recv() == "acquired"
    process.join(5)
    assert process.exitcode == 1
    inode = path.stat().st_ino
    with control.file_lock(path):
        assert path.stat().st_ino == inode


@pytest.mark.asyncio
async def test_runner_refuses_locked_run_before_import(tmp_path, monkeypatch):
    importer = AsyncMock(side_effect=AssertionError("no imports"))
    monkeypatch.setattr(runner, "sync_inbox", importer)
    with control.file_lock(tmp_path / "sync-run.lock"), pytest.raises(control.SyncBusy):
        await runner.run_sync_all(None, inbox=tmp_path, include_trading212=False)
    importer.assert_not_called()


@pytest.mark.asyncio
async def test_cli_locks_before_init_db(tmp_path, monkeypatch):
    from app import sync_cli

    monkeypatch.setattr(settings, "sync_inbox", tmp_path)
    init = AsyncMock(side_effect=AssertionError("no init while locked"))
    monkeypatch.setattr(sync_cli, "init_db", init)
    with control.file_lock(tmp_path / "sync-run.lock"):
        assert await sync_cli._run(argparse.Namespace()) == 0
    init.assert_not_called()


@pytest.mark.asyncio
async def test_runner_publishes_started_and_finished_atomically(tmp_path, monkeypatch):
    imported = Mock(files=[])
    monkeypatch.setattr(runner, "sync_inbox", AsyncMock(return_value=imported))
    observed = []
    replace = control.os.replace

    def track(source, target):
        replace(source, target)
        observed.append(json.loads(target.read_text()))

    monkeypatch.setattr(control.os, "replace", track)

    async def fetch(inbox):
        assert json.loads((inbox / "last-sync.json").read_text())["finished_at"] is None
        return runner.StepResult("Barclays", "ok")

    report = await runner.run_sync_all(
        None, inbox=tmp_path, include_trading212=False, fetchers=[("Barclays", fetch)]
    )
    assert len(observed) == 2
    assert observed[0]["finished_at"] is None
    assert observed[1]["finished_at"] is not None
    assert observed[0]["started_at"] == report.started_at
    assert report.steps[0].status == "ok"

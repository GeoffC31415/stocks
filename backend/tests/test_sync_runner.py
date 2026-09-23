"""Scheduler robustness: a stuck or crashing fetcher never blocks the other steps."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.services.sync_runner as runner
from app.models import Base
from app.services.sync_runner import StepResult, run_sync_all


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_hung_and_crashing_fetchers_do_not_block_later_steps(session, tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "FETCH_TIMEOUT_SECONDS", 0.05)

    async def hangs(_inbox):
        await asyncio.sleep(10)

    async def crashes(_inbox):
        raise RuntimeError("boom")

    async def works(_inbox):
        return StepResult("Works", "ok")

    report = await run_sync_all(
        session,
        fetchers=[("Hangs", hangs), ("Crashes", crashes), ("Works", works)],
        include_trading212=False,
        inbox=tmp_path,
    )
    status = {s.name: (s.status, s.detail) for s in report.steps}
    assert status["Hangs"][0] == "failed" and "timed out" in status["Hangs"][1]
    assert status["Crashes"] == ("failed", "RuntimeError")
    assert status["Works"] == ("ok", None)
    assert (tmp_path / "last-sync.json").exists()


@pytest.mark.asyncio
async def test_login_block_markers_stop_further_attempts(tmp_path, monkeypatch):
    from app.config import settings
    from app.fetchers import barclays, hl

    monkeypatch.setattr(settings, "browser_profile", tmp_path)
    for field in ("surname", "membership_number", "passcode", "memorable_word"):
        monkeypatch.setattr(settings, f"barclays_{field}", SecretStr("x"))

    def no_browser(*args, **kwargs):
        raise AssertionError("a blocked fetcher must not open a browser")

    monkeypatch.setattr(hl, "broker_context", no_browser)
    monkeypatch.setattr(barclays, "broker_context", no_browser, raising=False)
    hl._block("test")
    barclays._block("test")
    assert (await hl.fetch(tmp_path)).status == "needs_attention"
    assert (await barclays.fetch(tmp_path)).status == "needs_attention"


@pytest.mark.asyncio
async def test_unconfigured_barclays_is_skipped_without_a_browser(tmp_path, monkeypatch):
    from app.config import settings
    from app.fetchers import barclays

    monkeypatch.setattr(settings, "browser_profile", tmp_path)
    monkeypatch.setattr(settings, "barclays_surname", None)
    monkeypatch.setattr(
        barclays,
        "broker_context",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError),
        raising=False,
    )
    assert (await barclays.fetch(tmp_path)) == StepResult("Barclays", "skipped", "not configured")

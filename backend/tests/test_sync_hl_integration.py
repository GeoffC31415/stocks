"""Real staged HL integration; enabled when integrity-worker helper is merged."""
import datetime as dt

import pytest
from sqlalchemy import func, select

from app.models import HoldingSnapshot, Order
from app.services.sync_runner import run_sync_all

hl = pytest.importorskip("app.services.hl_sync_service")

HOLDINGS = (
    "Spreadsheet created at,29-09-2026 10:00\nStock value:,30\nNumber of holdings:,2\n"
    "Code,Stock,Units held,Price (pence),Value (£),Cost (£),Gain/loss (%)\n"
    "ONE,One,1,1000,10,9,11.11\nTWO,Two,2,1000,20,18,11.11\n,Totals,,,30,27,\n"
).encode()
ACTIVITY = (
    "Trade date,Reference,Description,Unit cost (p),Quantity,Value (£)\n"
    "01/09/2026,B1,One 1 @ 1000,1000,1,-10\n"
).encode()


@pytest.fixture
async def db_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models import Base
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine)() as session:
            yield session
    finally:
        await engine.dispose()


async def test_real_hl_pair_runner_commits_then_observes_unchanged(db_session, tmp_path):
    async def fetch(inbox):
        return hl.FetchedHLPair(HOLDINGS, ACTIVITY, dt.datetime(2026, 9, 29, 11, tzinfo=dt.UTC))
    options = {"inbox": tmp_path, "fetchers": [("Hargreaves Lansdown", fetch)], "include_trading212": False}
    first = await run_sync_all(db_session, **options)
    assert first.outcome == "complete"
    assert first.steps[0].status == "ok"
    before = [await db_session.scalar(select(func.count()).select_from(model)) for model in (HoldingSnapshot, Order)]
    assert before[0] >= 2 and before[1] == 1
    repeated = await run_sync_all(db_session, **options)
    assert repeated.steps[0].status == "unchanged"
    assert repeated.freshness["Hargreaves Lansdown"]["orders"]["verified_at"] == "2026-09-29T11:00:00+00:00"
    assert before == [await db_session.scalar(select(func.count()).select_from(model)) for model in (HoldingSnapshot, Order)]
    assert not list(tmp_path.glob("*.csv"))

import asyncio
import datetime as dt
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_gate_a_hl_parser import ACTIVITY, ACTIVITY_HEADER, HOLDINGS

from app.fetchers import hl
from app.models import (
    AccountAlias,
    Base,
    HoldingSnapshot,
    ImportBatch,
    Instrument,
    Order,
    OrderImportBatch,
)
from app.services import hl_sync_service

# Labelled synthetic identity; colon labels preserve historical fingerprints.
IDENTITY = "Client Name:,Synthetic Person\nClient Number:,SYNTHETIC-001\n"
HOLDINGS = IDENTITY + HOLDINGS
ACTIVITY = IDENTITY + ACTIVITY


def service():
    return hl_sync_service


async def enroll_synthetic_hl_owner(session, canonical="HL Fund & Share Account"):
    from app.services.hl_parser import hl_client_identity_key

    session.add(AccountAlias(
        source="hl-client-identity",
        source_account_name=hl_client_identity_key("Synthetic Person", "SYNTHETIC-001"),
        canonical_account_name=canonical,
        created_by="synthetic-test-operator",
    ))
    await session.commit()


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        await enroll_synthetic_hl_owner(session)
        yield session
    await engine.dispose()


async def counts(db):
    return [
        await db.scalar(select(func.count()).select_from(model))
        for model in (ImportBatch, HoldingSnapshot, Instrument, OrderImportBatch, Order)
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RuntimeError, asyncio.CancelledError])
async def test_second_import_failure_rolls_back_whole_pair(db, monkeypatch, error):
    await service().import_pair(
        db, HOLDINGS.encode(), ACTIVITY.encode(), as_of=dt.date(2026, 9, 29)
    )
    before = await counts(db)

    original_ingest = service().ingest_parsed_orders

    async def failure(*args, **kwargs):
        kwargs["commit"] = True
        await original_ingest(*args, **kwargs)
        raise error("synthetic second import failure after internal commit")

    monkeypatch.setattr(service(), "ingest_parsed_orders", failure)
    with pytest.raises(error):
        await service().import_pair(
            db,
            HOLDINGS.replace("One,", "Renamed,").replace("29-09-2026", "30-09-2026").encode(),
            ACTIVITY.replace("B1", "B2").encode(),
            as_of=dt.date(2026, 9, 30),
        )
    assert await counts(db) == before
    assert (
        await db.scalar(select(Instrument.security_name).where(Instrument.identifier == "ONE"))
        == "One"
    )
    # Another broker can still make progress after the failed HL batch.
    from test_gate_a_trading212 import Reader

    from app.services.trading212 import sync_portfolio_snapshot

    await sync_portfolio_snapshot(db, Reader(), account_name="Independent broker")
    assert (
        await db.scalar(
            select(func.count())
            .select_from(Instrument)
            .where(Instrument.account_name == "Independent broker")
        )
        == 3
    )


@pytest.mark.asyncio
async def test_valid_pair_commits_both_and_repeat_is_unchanged(db):
    first = await service().import_pair(
        db, HOLDINGS.encode(), ACTIVITY.encode(), as_of=dt.date(2026, 9, 29)
    )
    before = await counts(db)
    repeated = await service().import_pair(
        db, HOLDINGS.encode(), ACTIVITY.encode(), as_of=dt.date(2026, 9, 29)
    )
    assert first["snapshot"] == first["orders"] == "imported"
    assert repeated["snapshot"] == repeated["orders"] == "unchanged"
    assert await counts(db) == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "activity",
    [
        "Client Name:,Different person\n" + ACTIVITY_HEADER,
        "Valuation as at,28-09-2026 10:00\n" + ACTIVITY,
        ACTIVITY.replace("01/09/2026", "01/10/2026"),
    ],
)
async def test_incoherent_pair_is_rejected_before_writes(db, activity):
    with pytest.raises(ValueError, match="HL"):
        await service().import_pair(
            db, HOLDINGS.encode(), activity.encode(), as_of=dt.date(2026, 9, 29)
        )
    assert await counts(db) == [0, 0, 0, 0, 0]


@pytest.mark.asyncio
async def test_invalid_activity_leaves_no_holdings(db):
    with pytest.raises(ValueError):
        await service().import_pair(db, HOLDINGS.encode(), b"invalid", as_of=dt.date(2026, 9, 29))
    assert await counts(db) == [0, 0, 0, 0, 0]


@pytest.mark.asyncio
async def test_second_download_failure_never_publishes_partial_inbox(tmp_path, monkeypatch):
    class Locator:
        @property
        def first(self):
            return self

        async def count(self):
            return 1

        async def get_attribute(self, attr):
            return "/account"

    page = SimpleNamespace(locator=lambda selector: Locator(), goto=AsyncMock())
    response = SimpleNamespace(
        status=200, body=AsyncMock(return_value=("HL Fund & Share Account\n" + HOLDINGS).encode())
    )
    request = SimpleNamespace(
        get=AsyncMock(side_effect=[response, RuntimeError("second download failed")])
    )
    page.context = SimpleNamespace(request=request)

    @asynccontextmanager
    async def context(*args, **kwargs):
        yield SimpleNamespace(pages=[page])

    monkeypatch.setattr(hl, "broker_context", context)
    monkeypatch.setattr(hl, "login", AsyncMock())
    monkeypatch.setattr(hl, "block_marker", lambda: tmp_path / "not-blocked")
    with pytest.raises(RuntimeError):
        await hl.fetch(tmp_path)
    assert list(tmp_path.iterdir()) == []

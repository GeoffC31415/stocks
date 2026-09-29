"""Financial integrity regressions; synthetic in-memory data only."""

import copy

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import (
    AccountAlias,
    Base,
    CashFlowCoverage,
    ExternalCashFlow,
    HoldingSnapshot,
    ImportBatch,
    Instrument,
    Order,
    OrderImportBatch,
)
from app.routers.trading212 import run_trading212_sync
from app.services.trading212 import Trading212DataError, sync_portfolio_snapshot


class Reader:
    denied = False
    omit = False

    async def fetch_positions(self):
        return [
            {
                "instrument": {"isin": ident, "name": ident, "currency": "GBP"},
                "quantity": 1,
                "walletImpact": {"currency": "GBP", "currentValue": 10, "totalCost": 9},
            }
            for ident in (["ONE"] if self.omit else ["ONE", "TWO"])
        ]

    async def fetch_account_summary(self):
        if self.denied:
            request = httpx.Request(
                "GET", "https://live.trading212.com/api/v0/equity/account/summary"
            )
            raise httpx.HTTPStatusError(
                "denied", request=request, response=httpx.Response(403, request=request)
            )
        return {
            "currency": "GBP",
            "cash": {"availableToTrade": 25, "inPies": 0, "reservedForOrders": 0},
        }

    async def fetch_historical_orders(self):
        return [
            {
                "order": {"instrument": {"name": "ONE"}, "side": "BUY"},
                "fill": {
                    "id": 1,
                    "type": "TRADE",
                    "filledAt": "2026-01-01T12:00:00Z",
                    "quantity": 1,
                    "walletImpact": {"currency": "GBP", "netValue": -9},
                },
            }
        ]

    async def fetch_transactions(self):
        return [
            {
                "reference": "deposit",
                "type": "DEPOSIT",
                "amount": 10,
                "currency": "GBP",
                "dateTime": "2026-01-01T12:00:00Z",
            }
        ]


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


async def state(db):
    counts = [
        await db.scalar(select(func.count()).select_from(model))
        for model in (
            ImportBatch,
            HoldingSnapshot,
            OrderImportBatch,
            Order,
            ExternalCashFlow,
            CashFlowCoverage,
        )
    ]
    instruments = [
        (i.identifier, i.closed_at) for i in (await db.scalars(select(Instrument))).all()
    ]
    batches = [copy.deepcopy(b.diff_summary) for b in (await db.scalars(select(ImportBatch))).all()]
    return counts, instruments, batches


@pytest.mark.asyncio
async def test_omitted_position_rejects_entire_combined_sync(db):
    await sync_portfolio_snapshot(db, Reader(), account_name="Trading 212")
    before = await state(db)
    client = Reader()
    client.omit = True
    with pytest.raises(Trading212DataError, match="disappeared"):
        await run_trading212_sync(db, client, force=True)
    assert await state(db) == before


@pytest.mark.asyncio
async def test_reviewed_real_closure_is_explicit_and_account_scoped(db):
    db.add(
        AccountAlias(
            source="holdings",
            source_account_name="Reader alias",
            canonical_account_name="Trading 212",
        )
    )
    await db.commit()
    await sync_portfolio_snapshot(db, Reader(), account_name="Trading 212")
    client = Reader()
    client.omit = True
    batch, summary = await sync_portfolio_snapshot(
        db,
        client,
        account_name="Reader alias",
        force=True,
        reviewed_closed_identifiers=frozenset({"TWO"}),
    )
    assert [row["identifier"] for row in summary["closed"]] == ["TWO"]
    assert summary["row_count"] == 2
    assert (
        await db.scalar(
            select(func.count())
            .select_from(HoldingSnapshot)
            .where(HoldingSnapshot.import_batch_id == batch.id)
        )
        == 2
    )
    closed = await db.scalar(select(Instrument).where(Instrument.identifier == "TWO"))
    assert closed.closed_at is not None
    assert closed.account_name == "Trading 212"


@pytest.mark.asyncio
@pytest.mark.parametrize("review", [frozenset({"OTHER"}), frozenset({"CASH"}), {"TWO"}])
async def test_invalid_closure_reviews_cannot_override_guard(db, review):
    await sync_portfolio_snapshot(db, Reader(), account_name="Trading 212")
    before = await state(db)
    client = Reader()
    client.omit = True
    with pytest.raises(Trading212DataError):
        await sync_portfolio_snapshot(
            db, client, account_name="Trading 212", force=True, reviewed_closed_identifiers=review
        )
    assert await state(db) == before


@pytest.mark.asyncio
async def test_denied_summary_rejects_prior_cash_atomically(db):
    await sync_portfolio_snapshot(db, Reader(), account_name="Trading 212")
    before = await state(db)
    client = Reader()
    client.denied = True
    with pytest.raises(Trading212DataError, match="cash"):
        await run_trading212_sync(db, client, force=True)
    assert await state(db) == before

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
    # Combined sync writes through a joined session; read committed DB state,
    # not objects retained in the caller's identity map.
    db.expire_all()
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
@pytest.mark.parametrize("remaining", [["ONE"], []], ids=["partial-sale", "full-sale"])
async def test_complete_snapshot_accepts_sales_and_rebuy_without_review(db, remaining):
    from app.services.trading212 import Trading212Client

    initial_positions = await Reader().fetch_positions()
    positions = initial_positions
    account = await Reader().fetch_account_summary()
    orders = await Reader().fetch_historical_orders()
    transactions = await Reader().fetch_transactions()

    def transport(request):
        payloads = {
            "/api/v0/equity/positions": positions,
            "/api/v0/equity/account/summary": account,
            "/api/v0/equity/history/orders": {"items": orders, "nextPagePath": None},
            "/api/v0/equity/history/transactions": {
                "items": transactions, "nextPagePath": None,
            },
        }
        return httpx.Response(200, json=payloads[request.url.path])

    client = Trading212Client(
        api_key="SYNTHETIC_KEY", api_secret="SYNTHETIC_SECRET",
        transport=httpx.MockTransport(transport), page_delay=0,
    )
    await run_trading212_sync(db, client)
    original_ids = {
        i.identifier: i.id for i in (await db.scalars(select(Instrument))).all()
    }
    original_history = await state(db)
    positions = [p for p in initial_positions if p["instrument"]["isin"] in remaining]
    # Real API current positions are authoritative, even without a SELL fill.
    account["cash"]["availableToTrade"] += 10 * (2 - len(remaining))
    result = await run_trading212_sync(db, client)
    assert result.snapshot == "imported"
    assert result.snapshot_rows == len(remaining) + 1  # includes verified cash
    sold = {"ONE", "TWO"} - set(remaining)
    latest = await db.scalar(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(1))
    assert {row["identifier"] for row in latest.diff_summary["closed"]} == sold
    instruments = (await db.scalars(select(Instrument))).all()
    assert {i.identifier for i in instruments if i.closed_at is not None} == sold
    current = (await db.scalars(
        select(Instrument.identifier).join(HoldingSnapshot)
        .where(HoldingSnapshot.import_batch_id == latest.id)
    )).all()
    assert set(current) == set(remaining) | {"CASH"}
    after_sale = await state(db)
    assert after_sale[0][1] == original_history[0][1] + len(remaining) + 1
    assert after_sale[0][2:] == original_history[0][2:]  # order/cash history retained
    assert after_sale[2][:-1] == original_history[2]  # old snapshot summaries untouched
    assert (await run_trading212_sync(db, client)).snapshot == "unchanged"
    assert await state(db) == after_sale

    # A -> B -> A must import again, reopening the same instruments, not dedupe
    # against a historical hash or require inferred sale/rebuy evidence.
    positions = initial_positions
    account["cash"]["availableToTrade"] = 25
    assert (await run_trading212_sync(db, client)).snapshot == "imported"
    db.expire_all()
    instruments = (await db.scalars(select(Instrument))).all()
    assert {i.identifier: i.id for i in instruments} == original_ids
    assert all(i.closed_at is None for i in instruments)
    after_rebuy = await state(db)
    assert after_rebuy[0][2:] == original_history[0][2:]
    assert (await run_trading212_sync(db, client)).snapshot == "unchanged"
    assert await state(db) == after_rebuy


@pytest.mark.asyncio
@pytest.mark.parametrize("quantity", [-1, 1], ids=["signed-sell", "positive-sell"])
async def test_sell_history_imports_after_complete_snapshot_closes_holding(db, quantity):
    from app.services.trading212 import Trading212Client

    await run_trading212_sync(db, Reader())
    orders = await Reader().fetch_historical_orders()
    sell = copy.deepcopy(orders[0])
    sell["order"]["side"] = "SELL"
    sell["fill"].update(id=2, quantity=quantity)
    sell["fill"]["walletImpact"]["netValue"] = 10
    orders.append(sell)
    payloads = {
        "/api/v0/equity/positions": [],
        "/api/v0/equity/account/summary": await Reader().fetch_account_summary(),
        "/api/v0/equity/history/orders": {"items": orders, "nextPagePath": None},
        "/api/v0/equity/history/transactions": {
            "items": await Reader().fetch_transactions(), "nextPagePath": None,
        },
    }
    client = Trading212Client(
        api_key="SYNTHETIC_KEY", api_secret="SYNTHETIC_SECRET",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payloads[request.url.path])
        ), page_delay=0,
    )
    await run_trading212_sync(db, client)
    db.expire_all()
    instrument = await db.scalar(select(Instrument).where(Instrument.identifier == "ONE"))
    assert instrument.closed_at is not None
    sell_order = await db.scalar(select(Order).where(Order.side == "Sell"))
    assert sell_order.instrument_id == instrument.id
    assert sell_order.quantity == 1
    assert sell_order.cost_proceeds_gbp == 10
    assert (await run_trading212_sync(db, client)).orders == "unchanged"
    assert await db.scalar(select(func.count()).select_from(Order)) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [
    "malformed-positions", "missing-position-values", "duplicate-position",
    "missing-cash", "late-order-fetch", "late-transaction-fetch",
    "invalid-order", "invalid-transaction",
])
async def test_rejected_complete_sync_never_commits_sale_closures(db, failure):
    from app.services.trading212 import Trading212Client

    await run_trading212_sync(db, Reader())
    before = await state(db)
    position = (await Reader().fetch_positions())[0]
    payloads = {
        "/api/v0/equity/positions": [],  # otherwise a valid full sale
        "/api/v0/equity/account/summary": await Reader().fetch_account_summary(),
        "/api/v0/equity/history/orders": {
            "items": await Reader().fetch_historical_orders(), "nextPagePath": None,
        },
        "/api/v0/equity/history/transactions": {
            "items": await Reader().fetch_transactions(), "nextPagePath": None,
        },
    }
    if failure == "malformed-positions":
        payloads["/api/v0/equity/positions"] = {}
    elif failure == "missing-position-values":
        position.pop("quantity")
        payloads["/api/v0/equity/positions"] = [position]
    elif failure == "duplicate-position":
        payloads["/api/v0/equity/positions"] = [position, position]
    elif failure == "missing-cash":
        payloads["/api/v0/equity/account/summary"] = {"currency": "GBP", "cash": {}}
    elif failure in {"late-order-fetch", "late-transaction-fetch"}:
        section = "orders" if failure == "late-order-fetch" else "transactions"
        cursor = "123" if section == "orders" else "opaque-cursor"
        payloads[f"/api/v0/equity/history/{section}"]["nextPagePath"] = (
            f"/api/v0/equity/history/{section}?cursor={cursor}&limit=50"
        )
    elif failure == "invalid-order":
        items = payloads["/api/v0/equity/history/orders"]["items"]
        valid_sell = copy.deepcopy(items[0])
        valid_sell["order"]["side"] = "SELL"
        valid_sell["fill"].update(id=2, quantity=-1)
        valid_sell["fill"]["walletImpact"]["netValue"] = 10
        invalid_fill = copy.deepcopy(valid_sell)
        invalid_fill["fill"]["id"] = 3
        invalid_fill["fill"].pop("quantity")
        items.extend([valid_sell, invalid_fill])
    else:
        payloads["/api/v0/equity/history/transactions"]["items"][0]["type"] = "UNKNOWN"

    def transport(request):
        if "cursor" in request.url.params:
            return httpx.Response(403)
        return httpx.Response(200, json=payloads[request.url.path])

    client = Trading212Client(
        api_key="SYNTHETIC_KEY", api_secret="SYNTHETIC_SECRET",
        transport=httpx.MockTransport(transport), page_delay=0,
    )
    expected_error = (
        httpx.HTTPStatusError if failure in {"late-order-fetch", "late-transaction-fetch"}
        else Trading212DataError
    )
    with pytest.raises(expected_error) as rejected:
        await run_trading212_sync(db, client)
    if failure in {"invalid-order", "invalid-transaction"}:
        # These fail *after* snapshot closure writes in the joined transaction.
        expected = "orders" if failure == "invalid-order" else "transactions"
        assert rejected.value.t212_endpoint == expected
        assert rejected.value.t212_phase == "import"
        if failure == "invalid-order":
            assert rejected.value.code == "invalid_order_fill_quantity"
    elif failure in {"late-order-fetch", "late-transaction-fetch"}:
        assert rejected.value.t212_phase == "fetch"
    # An accidental inner commit must not survive the owner rollback, even if
    # the caller subsequently commits a new transaction.
    await db.commit()
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
async def test_optional_closure_review_must_cover_exact_missing_set(db, monkeypatch):
    await sync_portfolio_snapshot(db, Reader(), account_name="Trading 212")
    before = await state(db)
    client = Reader()

    async def sold_all():
        return []

    monkeypatch.setattr(client, "fetch_positions", sold_all)
    with pytest.raises(Trading212DataError):
        await sync_portfolio_snapshot(
            db, client, account_name="Trading 212",
            reviewed_closed_identifiers=frozenset({"TWO"}),
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

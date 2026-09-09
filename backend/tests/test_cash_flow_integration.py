import datetime as dt

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, HoldingSnapshot, ImportBatch, Instrument, Order, OrderImportBatch
from app.services import trading212
from app.services.attribution_service import get_snapshot_attribution
from app.services.performance_service import get_portfolio_performance
from app.services.portfolio_service import get_portfolio_return_summary

ACCOUNT = "Trading 212"


class CashClient:
    def __init__(self, items=None):
        self.items = (
            items
            if items is not None
            else [
                event("opening", "DEPOSIT", 1000, "2026-09-01"),
                event("addition", "DEPOSIT", 500, "2026-09-04"),
                event("removal", "WITHDRAW", -100, "2026-09-06"),
                event("after-closing", "DEPOSIT", 70, "2026-09-09"),
            ]
        )

    async def fetch_transactions(self):
        return self.items


def event(reference, kind, amount, day):
    return {
        "reference": reference,
        "type": kind,
        "amount": amount,
        "currency": "GBP",
        "dateTime": day + "T12:00:00Z",
    }


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


async def seed(session, account=ACCOUNT, with_orders=True):
    instrument = Instrument(
        account_name=account, identifier="TEST", security_name="Test", is_cash=False
    )
    session.add(instrument)
    await session.flush()
    for date, value in [(dt.date(2026, 9, 1), 1000), (dt.date(2026, 9, 8), 1450)]:
        batch = ImportBatch(as_of_date=date, file_sha256=f"{account}-{date}")
        session.add(batch)
        await session.flush()
        session.add(
            HoldingSnapshot(
                import_batch_id=batch.id,
                instrument_id=instrument.id,
                investment_label="Test",
                value_gbp=value,
            )
        )
    if with_orders:
        batch = OrderImportBatch(file_sha256=f"{account}-orders", row_count=2)
        session.add(batch)
        await session.flush()
        for side, amount in [("Buy", 450), ("Sell", 20)]:
            session.add(
                Order(
                    order_import_batch_id=batch.id,
                    instrument_id=instrument.id,
                    security_name="Test",
                    account_name=account,
                    side=side,
                    quantity=1,
                    cost_proceeds_gbp=amount,
                    order_date=dt.datetime(2026, 9, 5),
                    order_status="Completed",
                    is_drip=False,
                    order_fingerprint=f"{account}-{side}",
                )
            )
    await session.commit()


@pytest.mark.asyncio
async def test_sync_uses_real_cash_not_trades_across_dashboard_returns_and_attribution(session):
    await seed(session)
    result = await trading212.sync_cash_history(session, CashClient(), account_name=ACCOUNT)
    assert result["imported_count"] == 4
    assert (await trading212.sync_cash_history(session, CashClient(), account_name=ACCOUNT))[
        "imported_count"
    ] == 0
    performance = await get_portfolio_performance(session, account_name=ACCOUNT)
    returns = await get_portfolio_return_summary(session, account_name=ACCOUNT)
    attribution = await get_snapshot_attribution(session, account_name=ACCOUNT)
    for result in (performance["flow_adjusted"], returns, attribution):
        assert result["contributions_gbp"] == 500
        assert result["withdrawals_gbp"] == 100
        assert result["net_external_flow_gbp"] == 400
        assert any("cash" in note.lower() for note in result["notes"])
    assert returns["absolute_gain_after_flows_gbp"] == 50
    assert attribution["residual_market_movement_gbp"] == 50
    assert performance["flow_adjusted"]["total_return_pct"] == pytest.approx(
        returns["modified_dietz_return_pct"], abs=0.001
    )


@pytest.mark.asyncio
async def test_reinvestment_is_not_removed_from_account_gain_with_cash_ledger(session):
    await seed(session)
    order = await session.scalar(select(Order).where(Order.side == "Buy"))
    order.is_drip = True
    await session.commit()
    await trading212.sync_cash_history(session, CashClient(), account_name=ACCOUNT)
    attribution = await get_snapshot_attribution(session, account_name=ACCOUNT)
    assert attribution["net_external_flow_gbp"] == 400
    assert attribution["residual_market_movement_gbp"] == 50
    assert attribution["drip_proxy_gbp"] == 0


@pytest.mark.asyncio
async def test_cash_history_does_not_require_orders(session):
    await seed(session, with_orders=False)
    await trading212.sync_cash_history(session, CashClient(), account_name=ACCOUNT)
    result = await get_snapshot_attribution(session, account_name=ACCOUNT)
    assert result["net_external_flow_gbp"] == 400
    assert result["residual_market_movement_gbp"] == 50


@pytest.mark.asyncio
async def test_empty_successful_cash_history_overrides_trade_proxies(session):
    await seed(session)
    await trading212.sync_cash_history(session, CashClient([]), account_name=ACCOUNT)
    result = await get_portfolio_performance(session, account_name=ACCOUNT)
    assert result["flow_adjusted"]["net_external_flow_gbp"] == 0


@pytest.mark.asyncio
async def test_mixed_accounts_keep_legacy_proxies_without_double_counting(session):
    await seed(session)
    await seed(session, account="HL")
    await trading212.sync_cash_history(session, CashClient(), account_name=ACCOUNT)
    result = await get_portfolio_performance(session)
    assert result["flow_adjusted"]["net_external_flow_gbp"] == 830
    result = await get_portfolio_performance(session, account_name="HL")
    assert result["flow_adjusted"]["net_external_flow_gbp"] == 430


@pytest.mark.asyncio
async def test_conflicting_reimport_is_atomic(session):
    await seed(session)
    await trading212.sync_cash_history(session, CashClient(), account_name=ACCOUNT)
    from app.models import ExternalCashFlow

    before = await session.scalar(select(func.count()).select_from(ExternalCashFlow))
    client = CashClient(
        [event("new", "DEPOSIT", 1, "2026-09-07"), event("addition", "DEPOSIT", 999, "2026-09-04")]
    )
    with pytest.raises(trading212.Trading212DataError):
        await trading212.sync_cash_history(session, client, account_name=ACCOUNT)
    assert await session.scalar(select(func.count()).select_from(ExternalCashFlow)) == before


@pytest.mark.asyncio
async def test_stale_cash_history_makes_all_flow_metrics_unavailable(session):
    from app.models import CashFlowCoverage

    await seed(session)
    await trading212.sync_cash_history(session, CashClient(), account_name=ACCOUNT)
    coverage = await session.get(CashFlowCoverage, ACCOUNT)
    coverage.fetched_at = dt.datetime(2026, 9, 7)
    await session.commit()
    performance = await get_portfolio_performance(session, account_name=ACCOUNT)
    returns = await get_portfolio_return_summary(session, account_name=ACCOUNT)
    attribution = await get_snapshot_attribution(session, account_name=ACCOUNT)
    assert performance["flow_adjusted"]["net_external_flow_gbp"] is None
    assert returns["net_external_flow_gbp"] is None
    assert attribution["net_external_flow_gbp"] is None


@pytest.mark.asyncio
async def test_same_day_cash_sync_must_cover_actual_api_snapshot_time(session):
    from app.models import CashFlowCoverage

    await seed(session)
    batch = await session.scalar(
        select(ImportBatch).where(ImportBatch.as_of_date == dt.date(2026, 9, 8))
    )
    batch.filename = "trading212-api-portfolio.json"
    batch.created_at = dt.datetime(2026, 9, 8, 15)
    await session.commit()
    await trading212.sync_cash_history(session, CashClient(), account_name=ACCOUNT)
    coverage = await session.get(CashFlowCoverage, ACCOUNT)
    coverage.fetched_at = dt.datetime(2026, 9, 8, 8)
    await session.commit()
    result = await get_portfolio_return_summary(session, account_name=ACCOUNT)
    assert result["net_external_flow_gbp"] is None
    coverage.fetched_at = dt.datetime(2026, 9, 8, 16)
    await session.commit()
    result = await get_portfolio_return_summary(session, account_name=ACCOUNT)
    assert result["net_external_flow_gbp"] == 400


@pytest.mark.asyncio
async def test_api_closing_snapshot_excludes_later_same_day_deposits(session):
    await seed(session)
    batch = await session.scalar(
        select(ImportBatch).where(ImportBatch.as_of_date == dt.date(2026, 9, 8))
    )
    batch.filename = "trading212-api-portfolio.json"
    batch.created_at = dt.datetime(2026, 9, 8, 10)
    await session.commit()
    items = CashClient().items + [event("too-late", "DEPOSIT", 999, "2026-09-08")]
    await trading212.sync_cash_history(session, CashClient(items), account_name=ACCOUNT)
    result = await get_portfolio_return_summary(session, account_name=ACCOUNT)
    assert result["net_external_flow_gbp"] == 400


@pytest.mark.asyncio
async def test_attribution_cash_cutoff_respects_explicit_earlier_same_day_batch(session):
    await seed(session)
    selected = await session.scalar(
        select(ImportBatch).where(ImportBatch.as_of_date == dt.date(2026, 9, 8))
    )
    selected.filename = "trading212-api-portfolio.json"
    selected.created_at = dt.datetime(2026, 9, 8, 10)
    later = ImportBatch(
        as_of_date=selected.as_of_date,
        created_at=dt.datetime(2026, 9, 8, 15),
        filename=selected.filename,
        file_sha256="later-same-day",
    )
    session.add(later)
    await session.flush()
    instrument = await session.scalar(select(Instrument))
    session.add(
        HoldingSnapshot(
            import_batch_id=later.id,
            instrument_id=instrument.id,
            investment_label="Test",
            value_gbp=2449,
        )
    )
    await session.commit()
    items = CashClient().items + [event("later-deposit", "DEPOSIT", 999, "2026-09-08")]
    await trading212.sync_cash_history(session, CashClient(items), account_name=ACCOUNT)
    result = await get_snapshot_attribution(session, account_name=ACCOUNT, to_batch_id=selected.id)
    assert result["net_external_flow_gbp"] == 400
    assert result["residual_market_movement_gbp"] == 50


@pytest.mark.asyncio
async def test_permission_denied_does_not_create_coverage_or_cash(session):
    import httpx

    from app.models import CashFlowCoverage, ExternalCashFlow

    class DeniedClient:
        async def fetch_transactions(self):
            request = httpx.Request(
                "GET", "https://live.trading212.com/api/v0/equity/history/transactions"
            )
            raise httpx.HTTPStatusError(
                "denied", request=request, response=httpx.Response(403, request=request)
            )

    with pytest.raises(httpx.HTTPStatusError):
        await trading212.sync_cash_history(session, DeniedClient(), account_name=ACCOUNT)
    assert await session.get(CashFlowCoverage, ACCOUNT) is None
    assert await session.scalar(select(func.count()).select_from(ExternalCashFlow)) == 0


@pytest.mark.asyncio
async def test_cash_sync_route_is_idempotent_and_rejects_hostile_origins(session):
    import httpx

    from app.database import get_session
    from app.main import app
    from app.routers.trading212 import get_trading212_client

    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_trading212_client] = lambda: CashClient()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/trading212/sync/cash-flows", headers={"Origin": "http://localhost:5173"}
            )
            assert response.status_code == 200
            assert response.json()["imported_count"] == 4
            response = await client.post("/api/trading212/sync/cash-flows")
            assert response.json()["imported_count"] == 0
            response = await client.post(
                "/api/trading212/sync/cash-flows", headers={"Origin": "https://hostile.invalid"}
            )
            assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()

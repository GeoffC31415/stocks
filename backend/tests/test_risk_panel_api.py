"""Endpoint tests for the current-portfolio risk analysis (Task 4).

Exercises ``GET /api/portfolio/risk`` against an in-memory database with a
seeded market-price cache. No network: the endpoint only reads cached series
(plus cached FX), so every case is deterministic and offline.
"""

from __future__ import annotations

import datetime as dt

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_session
from app.main import app
from app.models import (
    Base,
    HoldingSnapshot,
    ImportBatch,
    Instrument,
    MarketFxPoint,
    MarketPricePoint,
)
from app.services.market_data_service import SOURCE

VALUATION_DATE = dt.date(2026, 6, 30)


def _series(start: float, daily_return: float, points: int = 25) -> list[tuple[dt.date, float]]:
    """``points`` daily closes ending on VALUATION_DATE -> points-1 returns."""
    rows: list[tuple[dt.date, float]] = []
    price = start
    for i in range(points):
        rows.append((VALUATION_DATE - dt.timedelta(days=points - 1 - i), round(price, 6)))
        price *= 1.0 + daily_return
    return rows


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session = async_sessionmaker(engine, expire_on_commit=False)
    async with session() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def client(db: AsyncSession):
    async def override():
        yield db

    app.dependency_overrides[get_session] = override
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as handle:
            yield handle
    finally:
        app.dependency_overrides.pop(get_session, None)


async def _seed(
    db: AsyncSession,
    *,
    tickers: dict[str, str] | None = None,
    cash_value: float = 500.0,
    add_fx: bool = False,
    benchmark: str | None = None,
    empty: bool = False,
    points: int = 130,
) -> None:
    """Seed one batch. ``tickers`` maps symbol -> currency; values are 4000/3000."""
    if empty:
        return
    db.add(ImportBatch(id=1, as_of_date=VALUATION_DATE, file_sha256="f" * 64))
    specs = [
        (1, "BA", "BAE Systems", "BA.L", 4000.0),
        (2, "ULVR", "Unilever", "ULVR.L", 3000.0),
        (3, "CASH", "Cash", None, cash_value),
    ]
    for iid, ident, name, ticker, value in specs:
        db.add(
            Instrument(
                id=iid,
                account_name="ISA",
                identifier=ident,
                security_name=name,
                is_cash=ticker is None,
                ticker=ticker,
            )
        )
        db.add(
            HoldingSnapshot(
                import_batch_id=1,
                instrument_id=iid,
                investment_label=name,
                value_gbp=value,
            )
        )
    tickers = tickers or {}
    for symbol, currency in tickers.items():
        rows = _series(100.0, 0.001, points) if symbol == "BA.L" else _series(80.0, 0.0004, points)
        for date, close in rows:
            db.add(
                MarketPricePoint(
                    source=SOURCE, symbol=symbol, date=date, close=close, currency=currency
                )
            )
    if add_fx:
        for date, _ in _series(100.0, 0.001, points):
            db.add(MarketFxPoint(source=SOURCE, pair="GBPUSD", date=date, rate=1.27))
    if benchmark:
        for date, close in _series(5000.0, 0.0007, points):
            db.add(
                MarketPricePoint(
                    source=SOURCE, symbol=benchmark, date=date, close=close, currency="USD"
                )
            )
    await db.commit()


@pytest.mark.anyio
async def test_risk_endpoint_available(client, db) -> None:
    await _seed(
        db,
        tickers={"BA.L": "GBP", "ULVR.L": "GBP"},
        cash_value=500.0,
        benchmark="SPX",
        add_fx=True,
    )
    response = await client.get("/api/portfolio/risk", params={"benchmark": "SPX"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["valuation_date"] == VALUATION_DATE.isoformat()
    assert payload["benchmark_symbol"] == "SPX"
    assert payload["coverage"]["gate_met"] is True
    assert payload["coverage"]["observations"] >= 126
    analysis = payload["analysis"]
    assert analysis["status"] == "available"
    assert analysis["annualised_portfolio_volatility_pct"] > 0
    assert analysis["euler_sum_check"]["matches"] is True
    assert "ticker:BA.L" in analysis["factor_weights"]
    assert "cash" in analysis["factor_weights"]
    # A benchmark with enough overlap reports the paired metrics.
    assert analysis["benchmark"]["available"] is True
    assert analysis["benchmark"]["correlation"] is not None


@pytest.mark.anyio
async def test_risk_endpoint_no_cache_unavailable(client, db) -> None:
    # Portfolio has tickers but no cached series at all -> nothing is covered.
    await _seed(db, tickers=None, cash_value=500.0)
    response = await client.get("/api/portfolio/risk")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert not payload["coverage"]["gate_met"]
    assert payload["coverage"]["supported_value_gbp"] == 0.0
    joined = " | ".join(payload["warnings"])
    assert "no cached series" in joined


@pytest.mark.anyio
async def test_risk_endpoint_missing_fx(client, db) -> None:
    # USD series are cached but the GBPUSD FX rate is not -> factor excluded.
    await _seed(db, tickers={"BA.L": "USD", "ULVR.L": "USD"}, add_fx=False)
    response = await client.get("/api/portfolio/risk")
    payload = response.json()
    assert payload["available"] is False
    joined = " | ".join(payload["warnings"])
    assert "missing fx (GBPUSD)" in joined


@pytest.mark.anyio
async def test_risk_endpoint_fx_conversion(client, db) -> None:
    # Same USD series WITH the FX rate -> both factors become covered.
    await _seed(
        db,
        tickers={"BA.L": "USD", "ULVR.L": "USD"},
        cash_value=500.0,
        add_fx=True,
    )
    response = await client.get("/api/portfolio/risk")
    payload = response.json()
    assert payload["available"] is True
    assert payload["coverage"]["gate_met"] is True
    assert not payload["warnings"] or "missing fx" not in " | ".join(payload["warnings"])


@pytest.mark.anyio
async def test_risk_endpoint_no_batches(client, db) -> None:
    await _seed(db, empty=True)
    response = await client.get("/api/portfolio/risk")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert payload["reasons"] == ["no import batches found"]


@pytest.mark.anyio
async def test_risk_endpoint_stale_series_warning(client, db) -> None:
    # A series whose last close is older than STALE_AFTER_DAYS surfaces a warning.
    await _seed(db, empty=True)
    db.add(ImportBatch(id=1, as_of_date=VALUATION_DATE, file_sha256="f" * 64))
    db.add(
        Instrument(
            id=1,
            account_name="ISA",
            identifier="BA",
            security_name="BAE Systems",
            is_cash=False,
            ticker="BA.L",
        )
    )
    db.add(
        HoldingSnapshot(
            import_batch_id=1, instrument_id=1, investment_label="BAE", value_gbp=1000.0
        )
    )
    stale = VALUATION_DATE - dt.timedelta(days=40)
    for i in range(25):
        db.add(
            MarketPricePoint(
                source=SOURCE,
                symbol="BA.L",
                date=stale - dt.timedelta(days=24 - i),
                close=100.0 * (1.001 ** i),
                currency="GBP",
            )
        )
    await db.commit()
    response = await client.get("/api/portfolio/risk")
    payload = response.json()
    assert "BA.L" in payload["stale_factors"]
    joined = " | ".join(payload["warnings"])
    assert "stale market data" in joined


@pytest.mark.anyio
async def test_gbp_history_uses_same_day_fx_not_latest_rate(db):
    from app.services.portfolio_risk_service import _load_gbp_series

    for offset, rate in enumerate([1.0, 2.0, 4.0]):
        date = VALUATION_DATE - dt.timedelta(days=2 - offset)
        db.add(MarketPricePoint(source=SOURCE, symbol="USD", date=date, close=100, currency="USD"))
        db.add(MarketFxPoint(source=SOURCE, pair="GBPUSD", date=date, rate=rate))
    await db.commit()
    rows = await _load_gbp_series(db, "USD", "USD")
    assert rows is not None
    assert [value for _, value in rows] == [100.0, 50.0, 25.0]


@pytest.mark.anyio
async def test_risk_requires_126_observations_and_hides_insufficient_metrics(client, db):
    await _seed(db, tickers={"BA.L": "GBP", "ULVR.L": "GBP"}, points=25)
    payload = (await client.get("/api/portfolio/risk")).json()
    assert payload["coverage"]["min_observations"] == 126
    assert payload["available"] is False
    assert payload["analysis"] is None


@pytest.mark.anyio
async def test_coverage_denominator_excludes_cash(client, db):
    await _seed(db, tickers={"BA.L": "GBP", "ULVR.L": "GBP"}, cash_value=70000.0)
    payload = (await client.get("/api/portfolio/risk")).json()
    assert payload["available"] is True
    assert payload["coverage"]["covered_pct"] == 100.0


@pytest.mark.anyio
@pytest.mark.parametrize("currency,expected", [("GBp", [1.0, 2.0]), ("GBX", [1.0, 2.0]), ("JPY", None), ("UNKNOWN", None)])
async def test_source_currency_is_not_silently_treated_as_pounds(db, currency, expected):
    from app.services.portfolio_risk_service import _load_gbp_series

    for offset, value in enumerate([100.0, 200.0]):
        db.add(MarketPricePoint(source=SOURCE, symbol="A", date=VALUATION_DATE - dt.timedelta(days=1-offset), close=value, currency=currency))
    await db.commit()
    rows = await _load_gbp_series(db, "A", currency)
    assert (None if rows is None else [value for _, value in rows]) == expected


@pytest.mark.anyio
async def test_same_date_account_batches_are_not_dropped(client, db):
    await _seed(db, tickers={"BA.L": "GBP", "ULVR.L": "GBP"})
    db.add(ImportBatch(id=2, as_of_date=VALUATION_DATE, file_sha256="a" * 64))
    db.add(Instrument(id=4, account_name="SIPP", identifier="BA", security_name="BAE Systems", ticker="BA.L", is_cash=False))
    db.add(HoldingSnapshot(import_batch_id=2, instrument_id=4, investment_label="BAE", value_gbp=2500))
    await db.commit()
    payload = (await client.get("/api/portfolio/risk")).json()
    assert payload["coverage"]["total_value_gbp"] == 10000
    assert payload["coverage"]["supported_value_gbp"] == 9500
    assert (await client.get("/api/portfolio/risk", params={"account_name": "ISA"})).json()["coverage"]["total_value_gbp"] == 7500


@pytest.mark.anyio
async def test_usd_benchmark_requires_dated_fx_even_for_gbp_holdings(client, db):
    await _seed(db, tickers={"BA.L": "GBP", "ULVR.L": "GBP"}, benchmark="SPX")
    payload = (await client.get("/api/portfolio/risk", params={"benchmark": "SPX"})).json()
    assert payload["available"] is True
    assert payload["analysis"]["benchmark"]["available"] is False


@pytest.mark.anyio
async def test_cash_only_portfolio_returns_honest_unavailable_response(client, db):
    db.add(ImportBatch(id=1, as_of_date=VALUATION_DATE, file_sha256="c" * 64))
    db.add(Instrument(id=1, account_name="ISA", identifier="CASH", security_name="Cash", is_cash=True))
    db.add(HoldingSnapshot(import_batch_id=1, instrument_id=1, investment_label="Cash", value_gbp=1000))
    await db.commit()
    response = await client.get("/api/portfolio/risk")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert payload["analysis"] is None
    assert payload["coverage"]["cash_value_gbp"] == 1000
    assert any("cash-only" in reason for reason in payload["reasons"])


@pytest.mark.anyio
async def test_zero_value_cached_holdings_do_not_divide_by_zero(client, db):
    from sqlalchemy import update
    await _seed(db, tickers={"BA.L": "GBP", "ULVR.L": "GBP"}, cash_value=0)
    await db.execute(update(HoldingSnapshot).values(value_gbp=0))
    await db.commit()
    response = await client.get("/api/portfolio/risk")
    assert response.status_code == 200
    assert response.json()["available"] is False

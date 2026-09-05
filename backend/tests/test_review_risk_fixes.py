"""Offline review regressions; database writes use the in-memory fixture only."""
import datetime as dt

import pytest
from sqlalchemy import update
from test_risk_panel_api import VALUATION_DATE, _seed

from app.models import HoldingSnapshot, ImportBatch, Instrument

pytest_plugins = ["test_risk_panel_api"]


@pytest.mark.anyio
@pytest.mark.parametrize("label", ["Same display label", "cash"])
async def test_duplicate_display_labels_keep_canonical_factors(client, db, label):
    await _seed(db, tickers={"BA.L": "GBP", "ULVR.L": "GBP"})
    await db.execute(update(Instrument).values(security_name=label))
    await db.execute(update(HoldingSnapshot).where(HoldingSnapshot.instrument_id <= 2).values(value_gbp=4000))
    await db.commit()
    payload = (await client.get("/api/portfolio/risk")).json()
    assert payload["available"] is True
    analysis = payload["analysis"]
    assert set(payload["factor_names"]) == {"ticker:BA.L", "ticker:ULVR.L"}
    assert len(analysis["covariance_annualised"]) == len(payload["factor_names"])
    assert sum(analysis["full_book_weights"].values()) == pytest.approx(1)
    assert sum(analysis["euler_vol_contribution_pct"].values()) == pytest.approx(
        analysis["annualised_portfolio_volatility_pct"]
    )
    assert analysis["factor_details"]["ticker:BA.L"]["constituents"] == [[1, "ISA"]]
    assert analysis["factor_details"]["ticker:BA.L"]["labels"] == [label]


@pytest.mark.anyio
@pytest.mark.parametrize("ticker", [None, "BA.L"])
async def test_different_date_accounts_are_in_denominator_but_unavailable(client, db, ticker):
    await _seed(db, tickers={"BA.L": "GBP", "ULVR.L": "GBP"})
    old_date = VALUATION_DATE - dt.timedelta(days=1)
    db.add(ImportBatch(id=2, as_of_date=old_date, file_sha256="a" * 64))
    db.add(Instrument(id=4, account_name="SIPP", identifier="X", security_name="Unknown", is_cash=False, ticker=ticker))
    db.add(HoldingSnapshot(import_batch_id=2, instrument_id=4, investment_label="X", value_gbp=9000))
    await db.commit()
    payload = (await client.get("/api/portfolio/risk")).json()
    assert payload["valuation_date"] == VALUATION_DATE.isoformat()
    assert payload["coverage"]["total_value_gbp"] == 16500
    assert payload["coverage"]["unsupported_value_gbp"] == (9000 if ticker is None else 0)
    assert payload["coverage"]["covered_pct"] == pytest.approx(7000 / 16000 * 100 if ticker is None else 100)
    assert payload["available"] is False
    assert "inconsistent valuation dates" in " ".join(payload["reasons"])
    assert "SIPP" in " ".join(payload["warnings"])


@pytest.mark.anyio
async def test_historical_backfill_does_not_replace_current_snapshot(client, db):
    await _seed(db, tickers={"BA.L": "GBP", "ULVR.L": "GBP"})
    db.add(ImportBatch(id=2, as_of_date=dt.date(2026, 1, 1), file_sha256="a" * 64))
    db.add(HoldingSnapshot(import_batch_id=2, instrument_id=1, investment_label="BA", value_gbp=1))
    await db.commit()
    payload = (await client.get("/api/portfolio/risk")).json()
    assert payload["valuation_date"] == VALUATION_DATE.isoformat()
    assert payload["coverage"]["total_value_gbp"] == 7500
    assert payload["available"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("problem", ["mixed price basis", "inconsistent currency"])
async def test_inconsistent_cached_series_is_explicitly_excluded(client, db, problem):
    from app.models import MarketPricePoint

    await _seed(db, tickers={"BA.L": "GBP", "ULVR.L": "GBP"})
    if problem == "mixed price basis":
        await db.execute(update(MarketPricePoint).where(MarketPricePoint.date < VALUATION_DATE).values(adjusted_close=50))
    else:
        await db.execute(update(MarketPricePoint).where(MarketPricePoint.date == VALUATION_DATE).values(currency="GBp"))
    await db.commit()
    payload = (await client.get("/api/portfolio/risk")).json()
    assert payload["available"] is False
    assert payload["coverage"]["supported_value_gbp"] == 0
    assert problem in " ".join(payload["warnings"])


@pytest.mark.anyio
@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan"), 1e308])
async def test_nonfinite_allocation_is_controlled_422(client, db, monkeypatch, value):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.services import allocation_service

    instrument = SimpleNamespace(id=1, is_cash=False, account_name="ISA", ticker=None,
                                 security_name="X", identifier="X", asset_class=None)
    snapshots = [SimpleNamespace(instrument=instrument, value_gbp=value,
                                 batch=SimpleNamespace(as_of_date=VALUATION_DATE))] * 2
    monkeypatch.setattr(allocation_service, "get_current_snapshots", AsyncMock(return_value=snapshots))
    response = await client.get("/api/portfolio/allocation")
    assert response.status_code == 422
    assert "non-finite" in response.json()["detail"]


@pytest.mark.anyio
@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan"), 1e308])
async def test_nonfinite_risk_is_json_safe_unavailable(client, db, monkeypatch, value):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.services import portfolio_risk_service

    await _seed(db)
    instrument = SimpleNamespace(id=1, is_cash=False, account_name="ISA", ticker=None,
                                 security_name="X", identifier="X", asset_class=None)
    snapshots = [SimpleNamespace(instrument=instrument, value_gbp=value,
                                 batch=SimpleNamespace(as_of_date=VALUATION_DATE))] * 2
    monkeypatch.setattr(portfolio_risk_service, "_latest_snapshots_for_scope", AsyncMock(return_value=snapshots))
    response = await client.get("/api/portfolio/risk")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert payload["analysis"] is None
    assert "non-finite" in " ".join(payload["reasons"])
    assert payload["coverage"]["covered_pct"] is None


@pytest.mark.anyio
async def test_actual_aligned_window_has_staleness_warning(client, db):
    from app.models import MarketPricePoint
    from app.services.market_data_service import SOURCE

    await _seed(db, tickers={"BA.L": "GBP", "ULVR.L": "GBP"})
    from sqlalchemy import select
    points = (await db.execute(select(MarketPricePoint))).scalars().all()
    for point in points:
        point.date -= dt.timedelta(days=60)
    for symbol, offset in [("BA.L", 0), ("ULVR.L", 1)]:
        db.add(MarketPricePoint(source=SOURCE, symbol=symbol,
                               date=VALUATION_DATE - dt.timedelta(days=offset),
                               close=101, currency="GBP"))
    await db.commit()
    payload = (await client.get("/api/portfolio/risk")).json()
    assert payload["available"] is True
    end = (VALUATION_DATE - dt.timedelta(days=60)).isoformat()
    assert payload["analysis"]["aligned"]["last"] == end
    warning = " ".join(payload["warnings"])
    assert "stale aligned analysis window" in warning
    assert end in warning
    assert VALUATION_DATE.isoformat() in warning


@pytest.mark.anyio
async def test_cache_after_valuation_is_not_used_for_factors_or_benchmark(client, db):
    from app.models import MarketPricePoint
    from app.services.market_data_service import SOURCE

    await _seed(db, tickers={"BA.L": "GBP", "ULVR.L": "GBP"})
    for symbol in ["BA.L", "ULVR.L", "BENCH"]:
        db.add(MarketPricePoint(source=SOURCE, symbol=symbol,
                               date=VALUATION_DATE + dt.timedelta(days=1),
                               close=100, currency="GBP"))
        db.add(MarketPricePoint(source=SOURCE, symbol=symbol,
                               date=VALUATION_DATE + dt.timedelta(days=2),
                               close=110, currency="GBP"))
    await db.commit()
    payload = (await client.get("/api/portfolio/risk", params={"benchmark": "BENCH"})).json()
    assert payload["available"] is True
    assert payload["analysis"]["aligned"]["last"] == VALUATION_DATE.isoformat()
    assert payload["benchmark_symbol"] is None
    assert "after valuation date" in " ".join(payload["warnings"])


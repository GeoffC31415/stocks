"""Provider-contract and cache tests for the market-data foundation.

No test in this module requires the internet: provider behaviour is exercised
through a fake provider and local CSV fixtures under
``tests/fixtures/market_data/``.
"""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, HoldingSnapshot, ImportBatch, Instrument
from app.services.market_data_coverage import to_gbp
from app.services.market_data_service import (
    MarketPricePointOut,
    RefreshResult,
    cached_history,
    fetch_history,
    latest_fx_rate,
    load_points,
    refresh_market_data,
    store_fx_points,
    store_points,
)

FIXTURES = Path(__file__).parent / "fixtures" / "market_data"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _read_fixture(name: str) -> list[dict[str, str]]:
    with open(FIXTURES / name, newline="") as handle:
        return list(csv.DictReader(handle))


def _points_from_fixture(name: str, source: str = "fixture") -> list[MarketPricePointOut]:
    """Parse a fixture into provider-contract rows (no network)."""
    points: list[MarketPricePointOut] = []
    for row in _read_fixture(name):
        points.append(
            MarketPricePointOut(
                symbol=row["symbol"],
                date=dt.date.fromisoformat(row["date"]),
                close=float(row["close"]),
                adjusted_close=None if row["adjusted_close"] in ("", None) else float(row["adjusted_close"]),
                currency=row["currency"],
                source=source,
                fetched_at=dt.datetime.fromisoformat(row["fetched_at"]),
            )
        )
    return points


@pytest.fixture()
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


# ---------------------------------------------------------------------------
# Fake provider (no network)
# ---------------------------------------------------------------------------


class FakeProvider:
    def __init__(self, data: dict[str, list[MarketPricePointOut]], *, fail: dict[str, str] | None = None):
        self.data = data
        self.fail = fail or {}
        self.calls: list[str] = []

    async def fetch_daily(
        self,
        symbol: str,
        *,
        start: dt.date | None = None,
        timeout: float = 20.0,
    ) -> list[MarketPricePointOut]:
        self.calls.append(symbol)
        if symbol in self.fail:
            raise RuntimeError(f"{symbol}: {self.fail[symbol]}")
        rows = self.data.get(symbol, [])
        return [row for row in rows if start is None or row.date >= start]


def _pts(symbol: str, currency: str, values: list[tuple[dt.date, float]]) -> list[MarketPricePointOut]:
    return [
        MarketPricePointOut(symbol=symbol, date=date, close=close, adjusted_close=None, currency=currency)
        for date, close in values
    ]


# ---------------------------------------------------------------------------
# 1. Provider contract from local fixtures
# ---------------------------------------------------------------------------


def test_fixture_rows_carry_the_full_provider_contract() -> None:
    points = _points_from_fixture("ba_l.csv")
    assert len(points) == 5
    point = points[0]
    # symbol, date, close, optional adjusted close, currency, source, fetched timestamp.
    assert point.symbol == "BA.L"
    assert point.date == dt.date(2026, 5, 29)
    assert point.close == 150.0
    assert point.adjusted_close == 148.2
    assert point.currency == "GBP"
    assert point.source == "fixture"
    assert point.fetched_at.tzinfo is not None


def test_fixture_rows_allow_missing_adjusted_close() -> None:
    points = _points_from_fixture("mu_usd.csv")
    assert all(point.adjusted_close is None for point in points)
    assert all(point.currency == "USD" for point in points)


def test_fixture_rows_allow_missing_adjusted_close_for_fx() -> None:
    points = _points_from_fixture("gbp_usd_fx.csv")
    assert points[0].symbol == "GBPUSD=X"
    assert points[0].close == 1.25


# ---------------------------------------------------------------------------
# 2. Cache persistence
# ---------------------------------------------------------------------------


async def test_store_and_load_roundtrip(session) -> None:
    points = _points_from_fixture("ba_l.csv", source="yahoo")
    written = await store_points(session, points)
    assert written == 5
    await session.commit()

    loaded = await load_points(session, "BA.L")
    assert [point.close for point in loaded] == [150.0, 151.5, 153.0, 152.4, 154.0]
    assert all(point.currency == "GBP" for point in loaded)


async def test_store_points_is_upsert(session) -> None:
    points = _points_from_fixture("ba_l.csv", source="yahoo")
    await store_points(session, points)
    await session.commit()

    updated = [
        MarketPricePointOut(
            symbol="BA.L",
            date=dt.date(2026, 5, 29),
            close=155.0,
            adjusted_close=153.2,
            currency="GBP",
        )
    ]
    await store_points(session, updated)
    await session.commit()

    loaded = await load_points(session, "BA.L")
    assert len(loaded) == 5  # overwrite, not duplicate
    assert loaded[0].close == 155.0
    assert loaded[0].adjusted_close == 153.2


async def test_load_points_respects_start_filter(session) -> None:
    points = _points_from_fixture("ba_l.csv", source="yahoo")
    await store_points(session, points)
    await session.commit()

    loaded = await load_points(session, "BA.L", start=dt.date(2026, 5, 31))
    assert [point.date for point in loaded] == [dt.date(2026, 5, 31), dt.date(2026, 6, 1), dt.date(2026, 6, 2)]


# ---------------------------------------------------------------------------
# 3. FX cache + GBP conversion
# ---------------------------------------------------------------------------


async def test_fx_points_roundtrip_and_latest_rate(session) -> None:
    fx = _points_from_fixture("gbp_usd_fx.csv", source="yahoo")
    written = await store_fx_points(session, fx)
    assert written == 5
    await session.commit()

    rate = await latest_fx_rate(session, "GBPUSD")
    assert rate == 1.275

    # as_of bounds the lookup.
    past = await latest_fx_rate(session, "GBPUSD", as_of=dt.date(2026, 6, 1))
    assert past == 1.28


def test_to_gbp_conversions() -> None:
    assert to_gbp(100.0, "GBP", None) == 100.0
    assert to_gbp(127.5, "USD", 1.275) == pytest.approx(100.0)
    # Missing FX must be reported, not converted to a zero/empty value.
    assert to_gbp(127.5, "USD", None) is None
    assert to_gbp(100.0, "JPY", 160.0) is None  # unknown pair


async def test_missing_fx_reported_not_converted(session) -> None:
    rate = await latest_fx_rate(session, "GBPUSD")
    assert rate is None


# ---------------------------------------------------------------------------
# 4. Refresh orchestration (bounded, partial-failure safe)
# ---------------------------------------------------------------------------


async def test_refresh_stores_points_and_fx(session) -> None:
    ba = _pts("BA.L", "GBP", [(dt.date(2026, 6, 1), 150.0), (dt.date(2026, 6, 2), 152.0)])
    fx = _pts("GBPUSD=X", "USD", [(dt.date(2026, 6, 2), 1.275)])
    provider = FakeProvider({"BA.L": ba, "GBPUSD=X": fx})

    result = await refresh_market_data(
        session,
        ["BA.L"],
        provider=provider,
        fx_pairs=["GBPUSD"],
        per_symbol_delay_s=0.0,
    )
    assert result.ok == ["BA.L"]
    assert result.failed == {}
    assert not result.partial
    assert await load_points(session, "BA.L")
    assert await latest_fx_rate(session, "GBPUSD") == 1.275
    assert provider.calls == ["BA.L", "GBPUSD=X"]


async def test_failed_refresh_keeps_cached_rows(session) -> None:
    old = _pts("BA.L", "GBP", [(dt.date(2026, 5, 29), 150.0), (dt.date(2026, 5, 30), 151.0)])
    await store_points(session, old)
    await session.commit()

    provider = FakeProvider({"BA.L": [], "EQQQ.L": []}, fail={"EQQQ.L": "HTTP 429"})
    result = await refresh_market_data(
        session,
        ["BA.L", "EQQQ.L"],
        provider=provider,
        fx_pairs=[],
        per_symbol_delay_s=0.0,
    )
    assert result.ok == ["BA.L"]
    assert "EQQQ.L" in result.failed
    assert result.partial

    # The failure did not delete the cached BA.L rows.
    loaded = await load_points(session, "BA.L")
    assert [point.close for point in loaded] == [150.0, 151.0]


async def test_refresh_partial_failure_reports_every_symbol(session) -> None:
    provider = FakeProvider({}, fail={"EQQQ.L": "rate limited", "MU": "timeout"})
    result = await refresh_market_data(
        session,
        ["EQQQ.L", "MU"],
        provider=provider,
        fx_pairs=[],
        per_symbol_delay_s=0.0,
    )
    assert set(result.failed) == {"EQQQ.L", "MU"}
    assert result.ok == []
    assert isinstance(result, RefreshResult)


# ---------------------------------------------------------------------------
# 5. Cache-first reads (offline acceptance: cache serves without provider)
# ---------------------------------------------------------------------------


async def test_fetch_history_serves_from_cache_without_provider(session) -> None:
    ba = _pts("BA.L", "GBP", [(dt.date(2026, 6, 1), 100.0), (dt.date(2026, 6, 2), 110.0)])
    await store_points(session, ba)
    await session.commit()

    provider = FakeProvider({})  # would raise if called
    rows = await fetch_history(session, "BA.L", provider=provider)
    assert provider.calls == []  # served fully from cache
    assert [row["rebased_value"] for row in rows] == [100.0, pytest.approx(110.0)]


async def test_fetch_history_falls_back_to_provider_and_persists(session) -> None:
    eqqq = _pts("EQQQ.L", "GBP", [(dt.date(2026, 6, 1), 200.0), (dt.date(2026, 6, 2), 220.0)])
    provider = FakeProvider({"EQQQ.L": eqqq})

    rows = await fetch_history(session, "EQQQ.L", provider=provider)
    assert provider.calls == ["EQQQ.L"]
    assert [row["rebased_value"] for row in rows] == [100.0, pytest.approx(110.0)]

    # Now cached: a second read needs no network.
    again = await fetch_history(session, "EQQQ.L", provider=provider)
    assert provider.calls == ["EQQQ.L"]
    assert again == rows


async def test_empty_cache_and_failed_provider_yields_empty_list(session) -> None:
    provider = FakeProvider({}, fail={"XDN0.L": "HTTP 429"})
    with pytest.raises(RuntimeError):
        await fetch_history(session, "XDN0.L", provider=provider)


async def test_cached_history_prefers_adjusted_close(session) -> None:
    points = [
        MarketPricePointOut(symbol="BA.L", date=dt.date(2026, 6, 1), close=100.0, adjusted_close=90.0, currency="GBP"),
        MarketPricePointOut(symbol="BA.L", date=dt.date(2026, 6, 2), close=110.0, adjusted_close=99.0, currency="GBP"),
    ]
    await store_points(session, points)
    await session.commit()
    rows = await cached_history(session, "BA.L")
    assert [row["rebased_value"] for row in rows] == [100.0, pytest.approx(100.0 * 99 / 90)]


# ---------------------------------------------------------------------------
# 6. Coverage report
# ---------------------------------------------------------------------------


async def _seed_instruments(session, specs: list[tuple[str, str | None, float]]) -> None:
    """Seed an instrument + one snapshot batch; specs are (identifier, ticker, value_gbp)."""
    batch = ImportBatch(as_of_date=dt.date(2026, 6, 2), file_sha256="coverage-test")
    session.add(batch)
    await session.flush()
    for identifier, ticker, value_gbp in specs:
        instrument = Instrument(
            account_name="Test",
            identifier=identifier,
            security_name=identifier,
            is_cash=False,
            ticker=ticker,
        )
        session.add(instrument)
        await session.flush()
        session.add(
            HoldingSnapshot(
                import_batch_id=batch.id,
                instrument_id=instrument.id,
                investment_label=identifier,
                value_gbp=value_gbp,
            )
        )
    await session.commit()


async def test_coverage_report_reports_gaps_not_zeros(session) -> None:
    from app.services.market_data_coverage import coverage_report

    await _seed_instruments(
        session,
        [
            ("alpha", "BA.L", 500.0),
            ("beta", "MU", 300.0),
            ("gamma", None, 100.0),
        ],
    )
    # BA.L has a fresh GBP series; MU has a USD series but no FX rate.
    ba = _pts("BA.L", "GBP", [(dt.date(2026, 6, 1), 150.0), (dt.date(2026, 6, 2), 152.0)])
    mu = _pts("MU", "USD", [(dt.date(2026, 6, 1), 80.0), (dt.date(2026, 6, 2), 85.0)])
    await store_points(session, ba + mu)
    await session.commit()

    report = await coverage_report(session)
    by_status = {entry["identifier"]: entry for entry in report["instruments"]}

    assert by_status["alpha"]["status"] == "covered"
    assert by_status["gamma"]["status"] == "uncovered"
    assert by_status["gamma"]["reason"] == "no ticker"
    assert by_status["beta"]["status"] == "uncovered"
    assert by_status["beta"]["reason"] == "missing fx (GBPUSD)"
    assert report["covered_value_gbp"] == 500.0
    assert report["uncovered_value_gbp"] == 400.0
    assert report["coverage_pct"] == pytest.approx(500.0 / 900.0 * 100.0)
    assert report["gate"]["met"] is False


async def test_coverage_gate_met_with_fx_available(session) -> None:
    from app.services.market_data_coverage import coverage_report

    await _seed_instruments(
        session,
        [
            ("alpha", "BA.L", 500.0),
            ("beta", "MU", 300.0),
        ],
    )
    ba = _pts("BA.L", "GBP", [(dt.date(2026, 6, 1), 150.0), (dt.date(2026, 6, 2), 152.0)])
    mu = _pts("MU", "USD", [(dt.date(2026, 6, 1), 80.0), (dt.date(2026, 6, 2), 85.0)])
    fx = _pts("GBPUSD=X", "USD", [(dt.date(2026, 6, 2), 1.275)])
    await store_points(session, ba + mu)
    await store_fx_points(session, fx)
    await session.commit()

    report = await coverage_report(session)
    assert report["coverage_pct"] == 100.0
    assert report["gate"]["met"] is True
    assert report["fx"]["GBPUSD"]["rate"] == 1.275


async def test_coverage_report_flags_stale_series(session) -> None:
    from app.services.market_data_coverage import coverage_report

    await _seed_instruments(session, [("alpha", "BA.L", 500.0)])
    ba = _pts("BA.L", "GBP", [(dt.date(2026, 5, 1), 150.0), (dt.date(2026, 5, 2), 152.0)])
    await store_points(session, ba)
    await session.commit()

    report = await coverage_report(session, stale_after_days=14)
    entry = report["instruments"][0]
    assert entry["stale"] is True
    assert [row["instrument_id"] for row in report["stale_series"]] == [entry["instrument_id"]]


async def test_coverage_report_flags_duplicate_tickers(session) -> None:
    from app.services.market_data_coverage import coverage_report

    await _seed_instruments(
        session,
        [
            ("isa-eqqq", "EQQQ.L", 400.0),
            ("sipp-eqqq", "EQQQ.L", 200.0),
        ],
    )
    report = await coverage_report(session)
    assert report["duplicates"] == {"EQQQ.L": [1, 2]}


async def test_coverage_report_aligned_dates(session) -> None:
    from app.services.market_data_coverage import coverage_report

    await _seed_instruments(
        session,
        [
            ("alpha", "BA.L", 100.0),
            ("beta", "VWRL.L", 100.0),
        ],
    )
    ba = _pts("BA.L", "GBP", [(dt.date(2026, 6, 1), 1.0), (dt.date(2026, 6, 2), 1.0), (dt.date(2026, 6, 3), 1.0)])
    vwrl = _pts("VWRL.L", "GBP", [(dt.date(2026, 6, 2), 1.0), (dt.date(2026, 6, 3), 1.0), (dt.date(2026, 6, 4), 1.0)])
    await store_points(session, ba + vwrl)
    await session.commit()

    report = await coverage_report(session)
    assert report["aligned_dates"] == {"count": 2, "first": dt.date(2026, 6, 2), "last": dt.date(2026, 6, 3)}


# ---------------------------------------------------------------------------
# 7. Quote helper keeps source currency explicit
# ---------------------------------------------------------------------------


async def test_quote_payload_keeps_source_currency(monkeypatch) -> None:
    import app.services.market_data_service as mds

    provider = FakeProvider({"MU": _pts("MU", "USD", [(dt.date(2026, 6, 2), 85.0)])})
    monkeypatch.setattr(mds, "make_provider", lambda: provider)

    from app.services.market_data_service import fetch_latest_quote

    payload = await fetch_latest_quote("MU")
    assert payload is not None
    assert payload["price"] == 85.0
    assert payload["price_ccy"] == "USD"
    # A USD close must never be labelled GBP.
    assert payload["price_ccy"] != "GBP"

from __future__ import annotations

import datetime as dt

import pytest

from app.services.performance_service import (
    _annualisation_factor,
    compute_performance_metrics,
    resolve_period_start,
)

D0 = dt.date(2026, 4, 1)


def _pts(values: list[float], daily: bool = True) -> list[tuple[dt.date, float]]:
    return [(D0 + dt.timedelta(days=i), v) for i, v in enumerate(values)]


def test_empty_series_reports_no_data() -> None:
    result = compute_performance_metrics([])
    assert result["total_return_pct"] is None
    assert result["num_periods"] == 0
    assert any("No dated" in note for note in result["notes"])


def test_single_point_has_no_return() -> None:
    result = compute_performance_metrics([(D0, 100.0)])
    assert result["total_return_pct"] is None
    assert result["max_drawdown_pct"] is None
    assert result["start_value_gbp"] == 100.0
    assert any("two dated" in note for note in result["notes"])


def test_flat_series_zero_return_and_zero_vol() -> None:
    result = compute_performance_metrics(_pts([100.0, 100.0, 100.0]))
    assert result["total_return_pct"] == 0.0
    assert result["annualised_return_pct"] == 0.0
    assert result["max_drawdown_pct"] == 0.0
    assert result["annualised_volatility_pct"] == 0.0
    # Zero variance -> Sharpe undefined.
    assert result["sharpe_ratio"] is None
    # No downside periods -> Sortino undefined.
    assert result["sortino_ratio"] is None
    assert result["best_period_return_pct"] == 0.0
    assert result["worst_period_return_pct"] == 0.0


def test_rising_then_dipping_metrics() -> None:
    # 100 -> 120 (+20%), -> 110 (-8.33%)
    result = compute_performance_metrics(_pts([100.0, 120.0, 110.0]))
    assert result["total_return_pct"] == pytest.approx(10.0, abs=1e-6)
    assert result["max_drawdown_pct"] == pytest.approx(-8.3333, abs=1e-3)
    assert result["best_period_return_pct"] == pytest.approx(20.0, abs=1e-6)
    assert result["worst_period_return_pct"] == pytest.approx(-8.3333, abs=1e-3)
    assert result["num_periods"] == 2

    # Hand-check: per-period returns [0.20, -0.08333]; sample stdev ~0.20034.
    ann_factor = _annualisation_factor([D0, D0 + dt.timedelta(days=1), D0 + dt.timedelta(days=2)])
    assert ann_factor == pytest.approx(365.25, abs=1e-6)
    import math

    assert result["annualised_volatility_pct"] == pytest.approx(
        0.20034 * math.sqrt(365.25) * 100.0, rel=1e-3
    )
    assert result["sharpe_ratio"] is not None and result["sharpe_ratio"] > 0
    assert result["sortino_ratio"] is not None and result["sortino_ratio"] > result["sharpe_ratio"]


def test_monotonic_up_has_no_drawdown() -> None:
    result = compute_performance_metrics(_pts([100.0, 105.0, 112.0, 120.0]))
    assert result["max_drawdown_pct"] == 0.0
    assert result["total_return_pct"] == pytest.approx(20.0, abs=1e-6)


def test_risk_free_shifts_sharpe_negative() -> None:
    points = _pts([100.0, 110.0, 120.0])
    base = compute_performance_metrics(points)
    assert base["sharpe_ratio"] is not None and base["sharpe_ratio"] > 0
    # A very high risk-free rate flips the numerator negative.
    high_rf = compute_performance_metrics(points, risk_free_annual_pct=4000.0)
    assert high_rf["sharpe_ratio"] is not None and high_rf["sharpe_ratio"] < 0


def test_annualised_return_matches_cagr() -> None:
    # One year of +21% total should annualise to ~21%.
    dates = [
        dt.date(2025, 8, 1),
        dt.date(2025, 11, 1),
        dt.date(2026, 8, 1),
    ]
    points = [(dates[0], 100.0), (dates[1], 105.0), (dates[2], 121.0)]
    result = compute_performance_metrics(points)
    assert result["total_return_pct"] == pytest.approx(21.0, abs=1e-6)
    # ~333 days span -> annualised close to 21%.
    assert result["annualised_return_pct"] == pytest.approx(21.0, abs=1.5)


def test_resolve_period_start() -> None:
    assert resolve_period_start("ALL", D0) is None
    assert resolve_period_start("YTD", dt.date(2026, 6, 15)) == dt.date(2026, 1, 1)
    assert resolve_period_start("1M", D0) == D0 - dt.timedelta(days=30)
    assert resolve_period_start("6M", D0) == D0 - dt.timedelta(days=183)
    with pytest.raises(ValueError):
        resolve_period_start("BOGUS", D0)


async def test_get_performance_windows_by_period(monkeypatch) -> None:
    from app.services import performance_service

    async def fake_build_value_series(session, *, account_name=None):
        return (
            [
                {"as_of_date": dt.date(2026, 1, 5), "value_gbp": 100.0},
                {"as_of_date": dt.date(2026, 6, 5), "value_gbp": 110.0},
                {"as_of_date": dt.date(2026, 8, 15), "value_gbp": 120.0},
            ],
            None,  # single-account series -> no coverage anchor
        )

    monkeypatch.setattr(performance_service, "build_value_series", fake_build_value_series)

    full = await performance_service.get_portfolio_performance(None, period="ALL")
    assert full["start_value_gbp"] == 100.0
    assert len(full["growth_curve"]) == 3
    assert full["growth_curve"][0]["normalized_value"] == pytest.approx(100.0)
    assert full["growth_curve"][-1]["normalized_value"] == pytest.approx(120.0)

    # 6M window from 2026-08-15 starts 2026-02-13 -> only the last two points.
    recent = await performance_service.get_portfolio_performance(None, period="6M")
    assert recent["start_value_gbp"] == 110.0
    assert len(recent["growth_curve"]) == 2
    assert recent["growth_curve"][0]["normalized_value"] == pytest.approx(100.0)


async def test_coverage_start_anchors_all_account_window(monkeypatch) -> None:
    from app.services import performance_service

    # Account A from Jan, account B only from Jun. All-account value is only
    # complete from Jun, so growth must anchor to 2026-06-05 regardless of period.
    async def fake_build_value_series(session, *, account_name=None):
        return (
            [
                {"as_of_date": dt.date(2026, 1, 5), "value_gbp": 100.0},  # A only
                {"as_of_date": dt.date(2026, 6, 5), "value_gbp": 150.0},  # A + B
                {"as_of_date": dt.date(2026, 8, 15), "value_gbp": 160.0},
            ],
            dt.date(2026, 6, 5),  # coverage_start
        )

    monkeypatch.setattr(performance_service, "build_value_series", fake_build_value_series)

    six_month = await performance_service.get_portfolio_performance(None, period="6M")
    assert six_month["start_value_gbp"] == 150.0  # anchored to coverage, not raw 6M
    assert six_month["total_return_pct"] == pytest.approx(6.6667, abs=1e-3)
    assert any("coverage" in note for note in six_month["notes"])


async def test_get_performance_no_benchmarks_is_safe(monkeypatch) -> None:
    from app.services import performance_service

    async def fake_build_value_series(session, *, account_name=None):
        return (
            [
                {"as_of_date": dt.date(2026, 7, 1), "value_gbp": 100.0},
                {"as_of_date": dt.date(2026, 8, 1), "value_gbp": 110.0},
            ],
            None,
        )

    async def fake_fetch_history(symbol, *, start=None, base_value=100.0):
        raise RuntimeError("network down")

    monkeypatch.setattr(performance_service, "build_value_series", fake_build_value_series)
    monkeypatch.setattr(performance_service, "fetch_history", fake_fetch_history, raising=False)

    result = await performance_service.get_portfolio_performance(
        None, period="ALL", benchmark_symbols=["spx.us"]
    )
    assert result["total_return_pct"] == pytest.approx(10.0, abs=1e-6)
    assert result["benchmarks"] == []
    assert len(result["growth_curve"]) == 2

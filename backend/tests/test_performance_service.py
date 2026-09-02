from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from app.services.performance_service import (
    _annualisation_factor,
    build_drawdown_curve,
    build_flow_adjusted_curve,
    compute_flow_adjusted_metrics,
    compute_performance_metrics,
    max_flow_adjusted_drawdown,
    resolve_period_start,
)
from app.services.portfolio_service import classify_external_flows

D0 = dt.date(2026, 4, 1)


def _order(side: str, gbp: float, date: dt.date, *, is_drip: bool = False):
    return SimpleNamespace(
        side=side,
        cost_proceeds_gbp=gbp,
        order_date=dt.datetime.combine(date, dt.time.max),
        is_drip=is_drip,
    )


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


async def test_performance_payload_exposes_flow_adjusted_curves(monkeypatch) -> None:
    from types import SimpleNamespace

    from app.services import performance_service

    async def fake_build_value_series(session, *, account_name=None):
        return (
            [
                {"as_of_date": dt.date(2026, 1, 1), "value_gbp": 100.0},
                {"as_of_date": dt.date(2026, 2, 1), "value_gbp": 200.0},
            ],
            None,
        )

    async def fake_fetch_history(symbol, *, start=None, base_value=100.0):
        return []

    # A single non-DRIP buy on Jan 15 = a 100 contribution mid-interval, so
    # the flow-adjusted index is flat while the raw value doubles.
    fake_order = SimpleNamespace(
        side="buy",
        cost_proceeds_gbp=100.0,
        order_date=dt.datetime(2026, 1, 15),
        is_drip=False,
    )

    class _FakeScalars:
        def all(self):
            return [fake_order]

    class _FakeResult:
        def scalars(self):
            return _FakeScalars()

    class _FakeSession:
        async def execute(self, query):
            return _FakeResult()

    monkeypatch.setattr(performance_service, "build_value_series", fake_build_value_series)
    monkeypatch.setattr(performance_service, "fetch_history", fake_fetch_history)

    result = await performance_service.get_portfolio_performance(
        _FakeSession(), period="ALL"
    )
    # Top-level curve + drawdown arrays are present and non-empty.
    assert len(result["flow_adjusted_curve"]) == 2
    assert len(result["drawdown_curve"]) == 2
    assert result["flow_adjusted_curve"][0]["index"] == 100.0
    # A pure contribution (no market gain) keeps the flow-adjusted index flat,
    # so its max drawdown is 0; the raw value only rose, so its is 0 too — but
    # the two are now distinct, named fields.
    assert result["flow_adjusted"]["contributions_gbp"] == 100.0
    assert result["max_drawdown_pct"] == 0.0
    assert result["max_drawdown_raw_pct"] == 0.0
    assert result["flow_adjusted"]["flow_adjusted_curve"] == result["flow_adjusted_curve"]


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


# --- Flow classification (shared with the returns card) ---------------------


def test_classify_external_flows_contribs_withdrawals_drip() -> None:
    orders = [
        _order("buy", 1000.0, dt.date(2026, 5, 10)),  # manual cash -> contribution
        _order("buy", 500.0, dt.date(2026, 5, 12), is_drip=True),  # DRIP -> excluded
        _order("sell", 300.0, dt.date(2026, 5, 20)),  # sale -> withdrawal
    ]
    contributions, withdrawals, signed = classify_external_flows(orders)
    assert contributions == 1000.0
    assert withdrawals == 300.0
    assert signed == [
        (dt.date(2026, 5, 10), 1000.0),
        (dt.date(2026, 5, 20), -300.0),
    ]


def test_classify_external_flows_skips_missing_gbp() -> None:
    orders = [_order("buy", 0.0, dt.date(2026, 5, 1)), _order("buy", 999.0, dt.date(2026, 5, 2))]
    orders[0].cost_proceeds_gbp = None  # unmatched / missing price
    contributions, withdrawals, signed = classify_external_flows(orders)
    assert contributions == 999.0
    assert withdrawals == 0.0
    assert len(signed) == 1


# --- Flow-adjusted (Modified Dietz) metrics ---------------------------------


def test_flow_adjusted_no_flows_matches_plain() -> None:
    points = _pts([100.0, 110.0, 120.0])
    fa = compute_flow_adjusted_metrics(points, [], contributions=0.0, withdrawals=0.0)
    # No flows -> Dietz return == simple return.
    assert fa["total_return_pct"] == pytest.approx(20.0, abs=1e-6)
    assert fa["contributions_gbp"] == 0.0
    assert fa["withdrawals_gbp"] == 0.0
    assert fa["num_periods"] == 2


def test_flow_adjusted_nets_out_contribution() -> None:
    # 100 -> (contribute 100 mid-interval) -> 200. The ending value is entirely
    # the injected cash; there is no market gain, so the real return is ~0%
    # (a raw value view would naively report +100%).
    points = [(dt.date(2026, 1, 1), 100.0), (dt.date(2026, 2, 1), 200.0)]
    flows = [(dt.date(2026, 1, 15), 100.0)]  # contribution mid-interval
    fa = compute_flow_adjusted_metrics(points, flows, contributions=100.0, withdrawals=0.0)
    # weighted flow = 100 * (17/31) = 54.84 ; numerator 200-(100+100)=0
    assert fa["total_return_pct"] is not None
    assert fa["total_return_pct"] == pytest.approx(0.0, abs=1e-6)
    assert fa["contributions_gbp"] == 100.0


def test_flow_adjusted_withdrawal_not_a_loss() -> None:
    # 100 -> (withdraw 50 mid-interval) -> 50. The drop is the withdrawal, not
    # a market loss, so the real return is ~0% (a raw value view would naively
    # report -50%).
    points = [(dt.date(2026, 1, 1), 100.0), (dt.date(2026, 2, 1), 50.0)]
    flows = [(dt.date(2026, 1, 15), -50.0)]
    fa = compute_flow_adjusted_metrics(points, flows, contributions=0.0, withdrawals=50.0)
    # weighted flow = -50 * (17/31) = -27.42 ; numerator 50-(100-50)=0
    assert fa["total_return_pct"] is not None
    assert fa["total_return_pct"] == pytest.approx(0.0, abs=1e-6)
    assert fa["withdrawals_gbp"] == 50.0


def test_flow_adjusted_real_gain_still_counts() -> None:
    # 100 -> (contribute 100) -> 250. The extra 50 over (base+flow) is genuine
    # market gain, so the real return is positive (raw view would say +150%).
    points = [(dt.date(2026, 1, 1), 100.0), (dt.date(2026, 2, 1), 250.0)]
    flows = [(dt.date(2026, 1, 15), 100.0)]
    fa = compute_flow_adjusted_metrics(points, flows, contributions=100.0, withdrawals=0.0)
    assert fa["total_return_pct"] is not None
    assert fa["total_return_pct"] > 10.0
    assert fa["total_return_pct"] < 150.0  # far below the raw +150%


def test_flow_adjusted_exposes_flows_in_block() -> None:
    points = [(dt.date(2026, 1, 1), 100.0), (dt.date(2026, 3, 1), 140.0)]
    flows = [(dt.date(2026, 2, 1), 20.0), (dt.date(2026, 2, 15), -10.0)]
    fa = compute_flow_adjusted_metrics(
        points, flows, contributions=20.0, withdrawals=10.0
    )
    assert fa["contributions_gbp"] == 20.0
    assert fa["withdrawals_gbp"] == 10.0
    assert fa["net_external_flow_gbp"] == 10.0
    assert "flow" in fa["method"].lower() or "dietz" in fa["method"].lower()
    assert any("flow" in n.lower() for n in fa["notes"])


def test_flow_adjusted_single_point_has_no_return() -> None:
    fa = compute_flow_adjusted_metrics(
        [(dt.date(2026, 1, 1), 100.0)], [], contributions=0.0, withdrawals=0.0
    )
    assert fa["total_return_pct"] is None
    assert any("two dated" in n for n in fa["notes"])


def test_flow_adjusted_risk_uses_interval_dietz_returns() -> None:
    # Two intervals with different returns -> non-zero variance -> Sharpe/Sortino defined.
    points = [(dt.date(2026, 1, 1), 100.0), (dt.date(2026, 2, 1), 110.0), (dt.date(2026, 3, 1), 105.0)]
    fa = compute_flow_adjusted_metrics(points, [], contributions=0.0, withdrawals=0.0)
    assert fa["num_periods"] == 2
    assert fa["annualised_volatility_pct"] is not None and fa["annualised_volatility_pct"] > 0
    assert fa["sharpe_ratio"] is not None
    assert fa["sortino_ratio"] is not None


def test_flow_adjusted_interval_dietz_hand_check() -> None:
    # Single interval, contribution at the exact start of the interval is
    # excluded (it is in the start value). Contribution at the end has zero
    # weight in the denominator but full weight in the numerator.
    points = [(dt.date(2026, 1, 1), 100.0), (dt.date(2026, 1, 31), 200.0)]
    # contribute 100 at Jan 31 (end of interval): weight (31-31)/30 = 0.
    flows = [(dt.date(2026, 1, 31), 100.0)]
    fa = compute_flow_adjusted_metrics(points, flows, contributions=100.0, withdrawals=0.0)
    # numerator 200-(100+100)=0 -> 0% real return despite doubling value.
    assert fa["total_return_pct"] == pytest.approx(0.0, abs=1e-9)


# --- Flow-adjusted wealth index + drawdown curve (Task 1) -------------------


def test_flow_adjusted_curve_starts_at_100_and_chains() -> None:
    # 100 -> 110 -> 105 (no flows): interval returns [0.10, -0.0454545].
    # index: 100 -> 110 -> 110 * (1 - 0.0454545) = 105.0
    points = [(dt.date(2026, 1, 1), 100.0), (dt.date(2026, 2, 1), 110.0), (dt.date(2026, 3, 1), 105.0)]
    curve = build_flow_adjusted_curve(points, [])
    assert [p["index"] for p in curve] == [100.0, pytest.approx(110.0, abs=1e-6), pytest.approx(105.0, abs=1e-3)]
    assert [p["date"] for p in curve] == [dt.date(2026, 1, 1), dt.date(2026, 2, 1), dt.date(2026, 3, 1)]


def test_flow_adjusted_curve_flat_on_pure_contribution() -> None:
    # 100 -> (contribute 100 mid-interval) -> 200. No market gain, so the
    # flow-adjusted index stays flat at 100 even though the raw value doubled.
    points = [(dt.date(2026, 1, 1), 100.0), (dt.date(2026, 2, 1), 200.0)]
    flows = [(dt.date(2026, 1, 15), 100.0)]
    curve = build_flow_adjusted_curve(points, flows)
    assert [p["index"] for p in curve] == [100.0, pytest.approx(100.0, abs=1e-6)]
    # Contrast: the raw value index would read 200.
    raw_last = 200.0 / 100.0 * 100.0
    assert raw_last == pytest.approx(200.0)


def test_flow_adjusted_curve_real_gain_moves_index() -> None:
    # 100 -> (contribute 100 on Jan 15) -> 250 on Feb 1. Hold-weighted flow =
    # 100 * (17/31) = 54.84; dietz = (250 - 200) / (100 + 54.84) = 32.29% ->
    # index 100 * 1.3229 = 132.29. The raw value index would read 250.
    points = [(dt.date(2026, 1, 1), 100.0), (dt.date(2026, 2, 1), 250.0)]
    flows = [(dt.date(2026, 1, 15), 100.0)]
    curve = build_flow_adjusted_curve(points, flows)
    assert curve[-1]["index"] == pytest.approx(132.2917, abs=1e-3)


def test_flow_adjusted_curve_single_point_empty() -> None:
    assert build_flow_adjusted_curve([(dt.date(2026, 1, 1), 100.0)], []) == []


def test_drawdown_curve_known_peak_trough_recovery() -> None:
    # index 100 -> 120 -> 108: peak 120, trough 108 => -10% drawdown;
    # recovery to 120 (new peak) resets to 0%.
    curve = [
        {"date": dt.date(2026, 1, 1), "index": 100.0},
        {"date": dt.date(2026, 2, 1), "index": 120.0},
        {"date": dt.date(2026, 3, 1), "index": 108.0},
        {"date": dt.date(2026, 4, 1), "index": 120.0},
    ]
    dd = build_drawdown_curve(curve)
    assert dd[0]["drawdown_pct"] == 0.0
    assert dd[1]["drawdown_pct"] == 0.0
    assert dd[1]["at_peak"] is True
    assert dd[2]["drawdown_pct"] == pytest.approx(-10.0, abs=1e-6)
    assert dd[2]["at_peak"] is False
    assert dd[3]["drawdown_pct"] == pytest.approx(0.0, abs=1e-6)  # recovered to a new peak
    assert dd[3]["at_peak"] is True


def test_max_flow_adjusted_drawdown_matches_curve_trough() -> None:
    curve = [
        {"date": dt.date(2026, 1, 1), "index": 100.0},
        {"date": dt.date(2026, 2, 1), "index": 120.0},
        {"date": dt.date(2026, 3, 1), "index": 108.0},
    ]
    assert max_flow_adjusted_drawdown(curve) == pytest.approx(-10.0, abs=1e-6)


def test_max_flow_adjusted_drawdown_monotonic_is_zero() -> None:
    curve = [
        {"date": dt.date(2026, 1, 1), "index": 100.0},
        {"date": dt.date(2026, 2, 1), "index": 110.0},
        {"date": dt.date(2026, 3, 1), "index": 120.0},
    ]
    assert max_flow_adjusted_drawdown(curve) == 0.0


def test_max_flow_adjusted_drawdown_empty_is_none() -> None:
    assert max_flow_adjusted_drawdown([]) is None


def test_pure_contribution_yields_zero_flow_adjusted_drawdown() -> None:
    # Pure cash contribution with no market gain: index is flat at 100, so the
    # flow-adjusted max drawdown is 0 even though the raw value moved.
    points = [(dt.date(2026, 1, 1), 100.0), (dt.date(2026, 2, 1), 200.0)]
    flows = [(dt.date(2026, 1, 15), 100.0)]
    assert max_flow_adjusted_drawdown(build_flow_adjusted_curve(points, flows)) == 0.0

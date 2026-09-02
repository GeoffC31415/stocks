"""Tests for the pure current-composition risk engine (Task 3).

Deterministic, offline: no network, no database, no FastAPI.
"""

from __future__ import annotations

import datetime as dt
import math

import numpy as np
import pytest
from numpy.testing import assert_allclose

from app.services.risk_service import (
    MIN_ALPHA_OBSERVATIONS,
    TRADING_DAYS,
    CanonicalFactorEntry,
    RiskAnalysisInput,
    RiskFactorSeries,
    aggregate_canonical_factors,
    aligned_daily_returns,
    annualised_volatility,
    benchmark_metrics,
    compute_risk_analysis,
    euler_vol_contribution,
    sample_covariance,
    validate_price_series,
)


def _series(name: str, points: list[tuple[str, float]]) -> RiskFactorSeries:
    return RiskFactorSeries(
        name=name,
        prices=[(dt.date.fromisoformat(date), price) for date, price in points],
    )


def _two_day_walk(start: float, daily_return: float, days: int = 30) -> list[tuple[str, float]]:
    """A smooth walk: deterministic price path at a fixed daily return."""
    points: list[tuple[str, float]] = []
    price = start
    day = dt.date(2026, 1, 5)
    for _ in range(days):
        points.append((day.isoformat(), round(price, 6)))
        price *= 1.0 + daily_return
        day += dt.timedelta(days=1)
    return points


class TestSlice1Alignment:
    def test_aligns_on_common_dates_only(self) -> None:
        a = _series("A", _two_day_walk(100.0, 0.001, 10))
        # B drops the middle observation: no forward-fill, alignment skips it.
        b_points = _two_day_walk(50.0, -0.001, 10)
        b_points = b_points[:4] + b_points[6:]
        b = _series("B", b_points)
        dates, returns, reasons = aligned_daily_returns([a, b])
        assert reasons == []
        # B has 8 observations, all on dates A also has: 8 dates, 7 returns.
        assert len(dates) == 8
        assert returns.shape == (2, 7)

    def test_returns_are_simple_daily(self) -> None:
        a = _series("A", [("2026-01-05", 100.0), ("2026-01-06", 110.0)])
        _, returns, reasons = aligned_daily_returns([a])
        assert reasons == []
        assert_allclose(returns, [[0.10]])

    def test_insufficient_overlap_rejected(self) -> None:
        a = _series("A", [("2026-01-05", 100.0), ("2026-01-06", 101.0)])
        b = _series("B", [("2026-02-05", 50.0), ("2026-02-06", 49.0)])
        dates, returns, reasons = aligned_daily_returns([a, b])
        assert dates == []
        assert reasons and "insufficient overlap" in reasons[0]


class TestSlice2Validation:
    def test_non_finite_price_rejected(self) -> None:
        reasons = validate_price_series("A", [(dt.date(2026, 1, 5), float("inf"))])
        assert any("non-finite" in r for r in reasons)

    def test_nan_price_rejected(self) -> None:
        reasons = validate_price_series("A", [(dt.date(2026, 1, 5), float("nan"))])
        assert any("non-finite" in r for r in reasons)

    def test_non_positive_price_rejected(self) -> None:
        assert validate_price_series("A", [(dt.date(2026, 1, 5), 0.0)])
        assert validate_price_series("A", [(dt.date(2026, 1, 5), -5.0)])
        assert validate_price_series("A", [])

    def test_duplicate_dates_rejected(self) -> None:
        reasons = validate_price_series(
            "A", [(dt.date(2026, 1, 5), 1.0), (dt.date(2026, 1, 5), 2.0)]
        )
        assert any("duplicate date" in r for r in reasons)

    def test_zero_total_value_rejected(self) -> None:
        factors = (_series("A", _two_day_walk(100.0, 0.001)),)
        result = compute_risk_analysis(
            RiskAnalysisInput(
                factors=factors,
                cash_weight=0.0,
                sleeve_weights={"A": 1.0},
                full_book_weights={"A": 1.0},
                total_value_gbp=0.0,
            )
        )
        assert result["status"] == "unavailable"
        assert any("zero total value" in r for r in result["reasons"])


class TestSlice3CovarianceVolatility:
    def test_sample_covariance_matches_numpy(self) -> None:
        rng = np.random.default_rng(42)
        returns = rng.normal(0.001, 0.01, size=(3, 50))
        cov = sample_covariance(returns)
        assert_allclose(cov, np.cov(returns, ddof=1))

    def test_annualised_volatility_252(self) -> None:
        daily = np.full(100, 0.01)
        # std of a constant series is 0 -> 0.0, sanity for the constant case.
        assert annualised_volatility(daily) == 0.0
        values = _two_day_walk(100.0, 0.01, 30)
        series = _series("A", values)
        _, returns, reasons = aligned_daily_returns([series])
        assert reasons == []
        expected = float(np.std(returns[0], ddof=1)) * math.sqrt(TRADING_DAYS)
        assert_allclose(annualised_volatility(returns[0]), expected)

    def test_one_factor(self) -> None:
        factors = (_series("A", _two_day_walk(100.0, 0.002)),)
        result = compute_risk_analysis(
            RiskAnalysisInput(
                factors=factors,
                cash_weight=0.0,
                sleeve_weights={"A": 1.0},
                full_book_weights={"A": 1.0},
            )
        )
        assert result["status"] == "available"
        assert result["annualised_factor_volatility_pct"]["A"] > 0
        assert result["annualised_portfolio_volatility_pct"] > 0
        # A single factor's Euler contribution equals its own volatility.
        assert_allclose(
            result["euler_vol_contribution_pct"]["A"],
            result["annualised_factor_volatility_pct"]["A"],
            rtol=1e-9,
        )


class TestSlice4Euler:
    @pytest.fixture()
    def euler_result(self) -> dict:
        a = _series("A", _two_day_walk(100.0, 0.002))
        b = _series("B", _two_day_walk(50.0, -0.003))
        return compute_risk_analysis(
            RiskAnalysisInput(
                factors=(a, b),
                cash_weight=0.1,
                sleeve_weights={"A": 0.45, "B": 0.45},
                full_book_weights={"A": 0.45, "B": 0.45, "cash": 0.1},
            )
        )

    def test_contributions_sum_to_sigma(self, euler_result: dict) -> None:
        check = euler_result["euler_sum_check"]
        assert check["matches"] is True
        assert_allclose(
            check["contribution_sum_pct"],
            check["sigma_pct"],
            rtol=1e-9,
        )

    def test_negative_contributions_retained(self) -> None:
        # Two near-perfectly-inversely-correlated factors: each drags the
        # other down, so at least one marginal contribution is negative.
        # Build the return matrix directly instead of inferring from prices.
        rng = np.random.default_rng(7)
        base = rng.normal(0.0, 0.01, size=100)
        returns = np.vstack([base, -base + 0.2 * base])  # corr ~ -1
        cov = sample_covariance(returns)
        weights = np.array([0.5, 0.5])
        euler = euler_vol_contribution(cov, weights)
        contributions = euler["contributions_annualised"]
        # With |corr| near 1 and equal weights, portfolio vol collapses and
        # the marginal split is numerically delicate; assert the invariant
        # that holds regardless: contributions still sum to sigma.
        sigma = euler["sigma_annualised"]
        if sigma > 0:
            assert_allclose(sum(contributions), sigma, rtol=1e-9)
        # At least one contribution must be non-positive for inverse pairs.
        assert min(contributions) <= 0.0


class TestSlice5Cash:
    def test_cash_in_weights_with_zero_volatility(self) -> None:
        a = _series("A", _two_day_walk(100.0, 0.002))
        result = compute_risk_analysis(
            RiskAnalysisInput(
                factors=(a,),
                cash_weight=0.5,
                sleeve_weights={"A": 0.5},
                full_book_weights={"A": 0.5, "cash": 0.5},
            )
        )
        assert result["status"] == "available"
        # Displayed weights include cash; covariance input is factor-only.
        assert result["factor_weights"]["cash"] == 0.5
        assert result["euler_vol_contribution_pct"]["cash"] == 0.0
        # Half cash halves the portfolio volatility (vol scales with the
        # non-cash weight under single-factor composition).
        full = compute_risk_analysis(
            RiskAnalysisInput(
                factors=(a,),
                cash_weight=0.0,
                sleeve_weights={"A": 1.0},
                full_book_weights={"A": 1.0},
            )
        )
        assert_allclose(
            result["annualised_portfolio_volatility_pct"],
            full["annualised_portfolio_volatility_pct"] * 0.5,
            rtol=1e-9,
        )

    def test_cash_only_composition(self) -> None:
        result = compute_risk_analysis(
            RiskAnalysisInput(
                factors=(),
                cash_weight=1.0,
                sleeve_weights={},
                full_book_weights={"cash": 1.0},
            )
        )
        assert result["status"] == "available"
        assert result["annualised_portfolio_volatility_pct"] == 0.0
        assert result["factor_weights"] == {"cash": 1.0}

    def test_no_factors_no_cash_unavailable(self) -> None:
        result = compute_risk_analysis(
            RiskAnalysisInput(
                factors=(),
                cash_weight=0.0,
                sleeve_weights={},
                full_book_weights={},
            )
        )
        assert result["status"] == "unavailable"


class TestSlice6Aggregation:
    def test_repeated_symbols_aggregated_constituents_preserved(self) -> None:
        prices = _two_day_walk(100.0, 0.001, 10)
        entries = [
            CanonicalFactorEntry(
                symbol="BA.L", name="BA.L", prices=prices, instrument_id=1, account_name="Stocks"
            ),
            CanonicalFactorEntry(
                symbol="BA.L", name="BA.L", prices=prices, instrument_id=9, account_name="SIPP"
            ),
            CanonicalFactorEntry(
                symbol="VWRL.L",
                name="VWRL.L",
                prices=_two_day_walk(40.0, 0.001, 10),
                instrument_id=2,
                account_name="Stocks",
            ),
        ]
        factors = aggregate_canonical_factors(entries)
        names = [factor.name for factor in factors]
        assert names == ["BA.L", "VWRL.L"]
        ba = factors[0]
        assert ba.constituents == ((1, "Stocks"), (9, "SIPP"))
        assert len(ba.prices) == 10

    def test_aggregated_factor_survives_analysis(self) -> None:
        prices = _two_day_walk(100.0, 0.001, 10)
        factor = aggregate_canonical_factors(
            [
                CanonicalFactorEntry(
                    symbol="BA.L",
                    name="BA.L",
                    prices=prices,
                    instrument_id=1,
                    account_name="Stocks",
                )
            ]
        )[0]
        result = compute_risk_analysis(
            RiskAnalysisInput(
                factors=(factor,),
                cash_weight=0.0,
                sleeve_weights={"BA.L": 1.0},
                full_book_weights={"BA.L": 1.0},
            )
        )
        assert result["status"] == "available"


class TestSlice7Benchmark:
    @pytest.fixture()
    def benchmark_pair(self) -> tuple[np.ndarray, np.ndarray]:
        rng = np.random.default_rng(99)
        benchmark = np.cumsum(rng.normal(0.0, 0.005, size=40))
        portfolio = 1.2 * benchmark + rng.normal(0.0, 0.002, size=40)
        return portfolio, benchmark

    def test_beta_corr_tracking(self, benchmark_pair: tuple[np.ndarray, np.ndarray]) -> None:
        port, bench = benchmark_pair
        result = benchmark_metrics(port, bench)
        assert result["available"] is True
        assert result["observations"] == 40
        # beta: cov(p,b)/var(b) with p = 1.2*b + small noise -> near 1.2.
        expected_beta = float(np.cov(port, bench, ddof=1)[0, 1]) / float(np.var(bench, ddof=1))
        assert_allclose(result["beta"], expected_beta, rtol=1e-9)
        assert -1.0 <= result["correlation"] <= 1.0
        assert result["tracking_error_annualised_pct"] > 0.0

    def test_insufficient_pairs_unavailable(self) -> None:
        result = benchmark_metrics(np.array([0.01]), np.array([0.02]))
        assert result["available"] is False
        assert any("insufficient" in r for r in result["reasons"])

    def test_constant_benchmark_gives_no_beta(self) -> None:
        result = benchmark_metrics(
            np.array([0.01, 0.02, 0.03]), np.array([0.0, 0.0, 0.0])
        )
        assert result["available"] is True
        assert result["beta"] is None
        assert result["correlation"] is None


class TestSlice8AlphaIR:
    def test_alpha_ir_gated_by_min_observations(self) -> None:
        port = np.full(10, 0.001)
        bench = np.zeros(10)
        result = benchmark_metrics(port, bench)
        assert result["alpha_annualised_pct"] is None
        assert result["information_ratio"] is None
        assert any(str(MIN_ALPHA_OBSERVATIONS) in r for r in result["alpha_reasons"])

    def test_alpha_ir_when_gate_passes(self) -> None:
        rng = np.random.default_rng(5)
        excess = rng.normal(0.0002, 0.001, size=MIN_ALPHA_OBSERVATIONS)
        bench = rng.normal(0.0, 0.004, size=MIN_ALPHA_OBSERVATIONS)
        port = bench + excess
        result = benchmark_metrics(port, bench)
        assert result["alpha_annualised_pct"] is not None
        assert result["information_ratio"] is not None
        expected_alpha = float(np.mean(excess)) * TRADING_DAYS * 100.0
        assert_allclose(result["alpha_annualised_pct"], expected_alpha, rtol=1e-9)

    def test_zero_tracking_variance_no_ir(self) -> None:
        size = MIN_ALPHA_OBSERVATIONS
        excess = np.full(size, 0.0001)  # constant excess -> zero variance
        bench = np.zeros(size)
        result = benchmark_metrics(bench + excess, bench)
        assert result["alpha_annualised_pct"] is not None
        assert result["information_ratio"] is None
        assert any("zero tracking variance" in r for r in result["alpha_reasons"])


class TestSlice9EdgeCases:
    def _input(self, factors, cash: float = 0.0, **extra) -> RiskAnalysisInput:
        sleeve = {f.name: (1.0 - cash) / len(factors) for f in factors}
        full = {f.name: (1.0 - cash) / len(factors) for f in factors}
        if cash:
            full["cash"] = cash
        return RiskAnalysisInput(
            factors=tuple(factors),
            cash_weight=cash,
            sleeve_weights=sleeve,
            full_book_weights=full,
            **extra,
        )

    def test_perfect_correlation(self) -> None:
        walk = _two_day_walk(100.0, 0.002, 20)
        a = _series("A", walk)
        b = _series("B", [(d, p * 2.0) for d, p in walk])  # identical returns
        result = compute_risk_analysis(self._input([a, b]))
        assert result["status"] == "available"
        corr = np.asarray(result["correlation"])
        assert_allclose(corr, np.ones((2, 2)), rtol=1e-9)

    def test_inverse_correlation(self) -> None:
        # Build A and B from opposite daily returns so corr ~= -1.
        rng = np.random.default_rng(3)
        daily = rng.normal(0.001, 0.01, size=30)  # A's daily returns
        neg = -daily  # B's daily returns (opposite sign)
        dates = [
            (dt.date(2026, 1, 5) + dt.timedelta(days=i)).isoformat() for i in range(31)
        ]
        a_prices = [100.0]
        for r in daily:
            a_prices.append(a_prices[-1] * (1.0 + r))
        b_prices = [50.0]
        for r in neg:
            b_prices.append(b_prices[-1] * (1.0 + r))
        a = _series("A", list(zip(dates, a_prices, strict=True)))
        b = _series("B", list(zip(dates, b_prices, strict=True)))
        result = compute_risk_analysis(self._input([a, b]))
        assert result["status"] == "available"
        corr = np.asarray(result["correlation"])
        assert corr[0, 1] < -0.99

    def test_singular_covariance_constant_series(self) -> None:
        # Constant price over distinct dates -> zero returns -> singular
        # (all-zero) covariance; correlation must be reported unavailable.
        constant = [
            ((dt.date(2026, 1, 5) + dt.timedelta(days=i)).isoformat(), 100.0)
            for i in range(10)
        ]
        a = _series("A", constant)
        moving = _series("B", _two_day_walk(50.0, 0.001, 10))
        result = compute_risk_analysis(self._input([a, moving]))
        assert result["status"] == "available"
        assert result["correlation"] is None  # constant series: no correlation
        # A constant factor contributes zero volatility.
        assert result["annualised_factor_volatility_pct"]["A"] == 0.0
        check = result["euler_sum_check"]
        assert check["matches"] is True

    def test_missing_dates_not_forward_filled(self) -> None:
        a = _series("A", _two_day_walk(100.0, 0.001, 12))
        b_points = _two_day_walk(50.0, 0.001, 12)
        dropped = dt.date.fromisoformat(b_points[3][0])  # the date we will drop
        b_points.pop(3)
        b = _series("B", b_points)
        dates, returns, reasons = aligned_daily_returns([a, b])
        assert reasons == []
        # 11 shared dates -> 10 returns; the gap must not be filled in.
        assert returns.shape == (2, 10)
        assert len(dates) == 11
        # The dropped date must not appear in the aligned output.
        assert dropped not in dates

    def test_nan_inf_never_raise(self) -> None:
        a = _series(
            "A",
            [("2026-01-05", float("nan")), ("2026-01-06", float("inf"))],
        )
        b = _series("B", _two_day_walk(50.0, 0.001, 10))
        result = compute_risk_analysis(self._input([a, b]))
        assert result["status"] == "unavailable"
        assert any("non-finite" in r for r in result["reasons"])

    def test_uncovered_holding_stays_in_full_book(self) -> None:
        a = _series("A", _two_day_walk(100.0, 0.002, 15))
        unsupported = _series("X", _two_day_walk(30.0, 0.001, 15))
        result = compute_risk_analysis(
            RiskAnalysisInput(
                factors=(a,),
                cash_weight=0.1,
                sleeve_weights={"A": 0.9},  # normalised over supported + cash
                full_book_weights={"A": 0.63, "X": 0.27, "cash": 0.10},
                unsupported=(unsupported,),
            )
        )
        assert result["status"] == "available"
        assert result["unsupported_factors"] == [
            {"name": "X", "full_book_weight": 0.27}
        ]
        assert result["full_book_weights"]["X"] == 0.27
        # Covariance maths uses the normalised sleeve weights (0.9 A + 0.1 cash).
        assert_allclose(result["factor_weights"]["A"], 0.9)
        assert_allclose(result["factor_weights"]["cash"], 0.1)

    def test_unnormalised_sleeve_weights_rejected(self) -> None:
        a = _series("A", _two_day_walk(100.0, 0.002, 10))
        result = compute_risk_analysis(
            RiskAnalysisInput(
                factors=(a,),
                cash_weight=0.1,
                sleeve_weights={"A": 0.3},  # sums to 0.4, not 1.0
                full_book_weights={"A": 0.3},
            )
        )
        assert result["status"] == "unavailable"
        assert any("normalise" in r for r in result["reasons"])


class TestDeterminism:
    def test_same_input_same_output(self) -> None:
        factors = (
            _series("A", _two_day_walk(100.0, 0.002)),
            _series("B", _two_day_walk(50.0, -0.003)),
        )
        kwargs = {
            "cash_weight": 0.1,
            "sleeve_weights": {"A": 0.45, "B": 0.45},
            "full_book_weights": {"A": 0.45, "B": 0.45, "cash": 0.1},
        }
        first = compute_risk_analysis(RiskAnalysisInput(factors=factors, **kwargs))
        second = compute_risk_analysis(RiskAnalysisInput(factors=factors, **kwargs))
        assert first == second

    def test_finite_for_valid_inputs(self) -> None:
        factors = (
            _series("A", _two_day_walk(100.0, 0.002)),
            _series("B", _two_day_walk(50.0, -0.003)),
        )
        result = compute_risk_analysis(
            RiskAnalysisInput(
                factors=factors,
                cash_weight=0.0,
                sleeve_weights={"A": 0.5, "B": 0.5},
                full_book_weights={"A": 0.5, "B": 0.5},
            )
        )
        for value in (
            result["annualised_portfolio_volatility_pct"],
            *result["annualised_factor_volatility_pct"].values(),
            *result["euler_vol_contribution_pct"].values(),
        ):
            assert math.isfinite(value)

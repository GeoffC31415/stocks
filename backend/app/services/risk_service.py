"""Pure current-composition risk maths (Task 3).

Deterministic, dependency-light (numpy only) risk calculations for the
current portfolio composition. No FastAPI, SQLAlchemy, or network access:
the orchestration layer (Task 4) maps instruments to canonical factors,
aggregates duplicate symbols, normalises analysed-sleeve weights, and calls
:func:`compute_risk_analysis` here.

Input contract
--------------
- Ordered, dated GBP price series per canonical factor (duplicate
  instruments are aggregated by :func:`aggregate_canonical_factors`).
- Analysed-sleeve weights normalised across supported factors + cash.
  Unsupported factors stay outside the covariance input but keep their
  separate full-book weights in the result metadata.

Unavailability policy: invalid or insufficient inputs never raise
incidental NumPy warnings or exceptions; they come back as explicit
reasons in the result so callers can render unavailable states.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Sequence

#: Trading days per year for annualisation.
TRADING_DAYS = 252

#: Minimum paired observations for annualised alpha / Information Ratio.
MIN_ALPHA_OBSERVATIONS = 252

#: Tolerance for the Euler sum-of-contributions check.
EULER_TOLERANCE = 1e-9


@dataclass(frozen=True)
class RiskFactorSeries:
    """A canonical factor: one date/price series plus its constituents."""

    name: str
    prices: list[tuple[dt.date, float]]
    constituents: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True)
class RiskAnalysisInput:
    """Everything the pure maths needs (see module docstring)."""

    factors: tuple[RiskFactorSeries, ...]
    #: Analysed-sleeve weight of cash; factor weights + this must total 1.
    cash_weight: float
    #: factor name -> analysed-sleeve weight (supported factors only).
    sleeve_weights: dict[str, float]
    #: name -> full-book weight (factors, cash, and unsupported).
    full_book_weights: dict[str, float]
    unsupported: tuple[RiskFactorSeries, ...] = ()
    benchmark_prices: list[tuple[dt.date, float]] | None = None
    total_value_gbp: float | None = None


# ---------------------------------------------------------------------------
# 1-2. Validation + alignment (no forward-fill)
# ---------------------------------------------------------------------------


def validate_price_series(name: str, prices: Sequence[tuple[dt.date, float]]) -> list[str]:
    """Explicit reasons for unusable series; empty list when clean."""
    reasons: list[str] = []
    if not prices:
        return [f"{name}: empty series"]
    seen: set[dt.date] = set()
    prev_date: dt.date | None = None
    for date, price in prices:
        if not math.isfinite(price):
            reasons.append(f"{name}: non-finite price on {date.isoformat()}")
        elif price <= 0:
            reasons.append(f"{name}: non-positive price on {date.isoformat()}")
        if date in seen:
            reasons.append(f"{name}: duplicate date {date.isoformat()}")
        seen.add(date)
        if prev_date is not None and date < prev_date:
            reasons.append(f"{name}: out-of-order dates at {date.isoformat()}")
        prev_date = date
    return reasons


def aligned_daily_returns(
    factors: Sequence[RiskFactorSeries],
) -> tuple[list[dt.date], np.ndarray, list[str]]:
    """Align factor histories by date and compute simple daily returns.

    A date is kept only when *every* factor has an observation there —
    no forward-fill across missing trading observations. Returns are
    simple (p1/p0 - 1) between successive aligned observations.
    """
    reasons: list[str] = []
    for factor in factors:
        reasons.extend(validate_price_series(factor.name, factor.prices))
    if reasons:
        return [], np.empty((len(factors), 0)), reasons
    if not factors:
        return [], np.empty((0, 0)), ["no supported factors to align"]

    maps = [{date: float(price) for date, price in f.prices} for f in factors]
    common = sorted(set.intersection(*(set(m) for m in maps)))
    if len(common) < 2:
        return (
            [],
            np.empty((len(factors), 0)),
            [f"insufficient overlap: only {len(common)} aligned dates"],
        )
    n = len(common) - 1
    returns = np.empty((len(factors), n))
    for i, series in enumerate(maps):
        for j in range(n):
            p0 = series[common[j]]
            p1 = series[common[j + 1]]
            returns[i, j] = p1 / p0 - 1.0
    return common, returns, []


# ---------------------------------------------------------------------------
# 3-4. Covariance / correlation / volatility / Euler contributions
# ---------------------------------------------------------------------------


def sample_covariance(returns: np.ndarray) -> np.ndarray:
    """Sample (ddof=1) covariance over the observation axis."""
    if returns.shape[1] < 2:
        return np.zeros((returns.shape[0], returns.shape[0]))
    centered = returns - returns.mean(axis=1, keepdims=True)
    return centered @ centered.T / (returns.shape[1] - 1)


def correlation_matrix(cov: np.ndarray) -> np.ndarray | None:
    """Correlation from the covariance; None when any series is constant."""
    stds = np.sqrt(np.diag(cov))
    if np.any(stds <= 0) or not np.all(np.isfinite(stds)):
        return None
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = cov / np.outer(stds, stds)
    corr = np.clip(corr, -1.0, 1.0)
    np.fill_diagonal(corr, 1.0)
    return corr


def annualised_volatility(returns_row: np.ndarray) -> float:
    """Sample daily std x sqrt(252); 0.0 for constant/empty series."""
    if returns_row.size < 2:
        return 0.0
    if np.ptp(returns_row) == 0.0:  # constant series: exactly zero risk
        return 0.0
    std = float(np.std(returns_row, ddof=1))
    if not math.isfinite(std):
        return 0.0
    return std * math.sqrt(TRADING_DAYS)


def euler_vol_contribution(cov: np.ndarray, factor_weights: np.ndarray) -> dict[str, Any]:
    """Euler (marginal) volatility contributions for the factor weights.

    Cash is excluded here (zero variance/covariance); the weights may sum
    to less than 1 because the analysed-sleeve normalisation includes cash.
    Negative contributions are retained, not clamped.
    """
    weights = np.asarray(factor_weights, dtype=float)
    sigma2 = float(weights @ cov @ weights)
    if sigma2 <= 0 or not math.isfinite(sigma2):
        sigma_daily = 0.0
    else:
        sigma_daily = math.sqrt(sigma2)
    if sigma_daily > 0:
        marginal = (cov @ weights) / sigma_daily
        contributions = weights * marginal
    else:
        contributions = np.zeros_like(weights)
    total = float(contributions.sum())
    return {
        "sigma_daily": sigma_daily,
        "sigma_annualised": sigma_daily * math.sqrt(TRADING_DAYS),
        "contributions_annualised": [float(c) * math.sqrt(TRADING_DAYS) for c in contributions],
        "sum_matches_sigma": math.isclose(
            total, sigma_daily, rel_tol=EULER_TOLERANCE, abs_tol=1e-15
        ),
    }


# ---------------------------------------------------------------------------
# 6. Duplicate-symbol aggregation (constituents preserved)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CanonicalFactorEntry:
    """One instrument mapped to a canonical symbol (orchestration output)."""

    symbol: str
    name: str
    prices: list[tuple[dt.date, float]]
    instrument_id: int
    account_name: str


def _as_date(value: dt.date | str) -> dt.date:
    """Normalise an ISO-string or ``datetime.date`` to ``datetime.date``."""
    return value if isinstance(value, dt.date) else dt.date.fromisoformat(value)


def aggregate_canonical_factors(entries: Sequence[CanonicalFactorEntry]) -> list[RiskFactorSeries]:
    """Group repeated canonical symbols into one factor per symbol.

    The same symbol shares one price history; the factor keeps every
    (instrument_id, account) constituent so downstream views can explain
    what is inside the aggregated exposure. Dates are normalised to
    ``datetime.date`` regardless of the input representation.
    """
    groups: dict[str, list[CanonicalFactorEntry]] = {}
    for entry in entries:
        groups.setdefault(entry.symbol, []).append(entry)
    factors: list[RiskFactorSeries] = []
    for _symbol, group in groups.items():
        longest = max((entry.prices for entry in group), key=len)
        prices = sorted(
            (_as_date(date), float(price)) for date, price in longest
        )
        factors.append(
            RiskFactorSeries(
                name=group[0].name,
                prices=prices,
                constituents=tuple((entry.instrument_id, entry.account_name) for entry in group),
            )
        )
    factors.sort(key=lambda factor: factor.name)
    return factors


# ---------------------------------------------------------------------------
# 7-8. Benchmark metrics + alpha / Information Ratio
# ---------------------------------------------------------------------------


def benchmark_metrics(
    portfolio_returns: np.ndarray,
    benchmark_returns: np.ndarray,
    *,
    min_alpha_observations: int = MIN_ALPHA_OBSERVATIONS,
) -> dict[str, Any]:
    """Paired beta / correlation / tracking error, and gated alpha / IR.

    Documented method for alpha / IR (only shown when the gate passes):
    - alpha = mean of the paired daily excess returns (r_p - r_b),
      annualised by x TRADING_DAYS;
    - IR  = mean(excess) / std(excess, ddof=1) x sqrt(TRADING_DAYS).
    """
    n = min(len(portfolio_returns), len(benchmark_returns))
    if n < 2:
        return {"available": False, "reasons": ["insufficient paired benchmark observations"]}
    port = np.asarray(portfolio_returns[:n], dtype=float)
    bench = np.asarray(benchmark_returns[:n], dtype=float)
    if not (np.all(np.isfinite(port)) and np.all(np.isfinite(bench))):
        return {"available": False, "reasons": ["non-finite benchmark returns"]}

    # Manual moments (np.cov collapses to a 0-d array when one side has zero
    # variance, which would break [0, 1] indexing).
    centred_p = port - port.mean()
    centred_b = bench - bench.mean()
    var_b = float(centred_b @ centred_b / (n - 1))
    cov_pb = float(centred_p @ centred_b / (n - 1))
    std_p = float(math.sqrt(float(centred_p @ centred_p / (n - 1))))
    std_b = float(math.sqrt(var_b))
    beta = cov_pb / var_b if var_b > 0 else None
    corr = cov_pb / (std_p * std_b) if (std_p > 0 and std_b > 0) else None
    diff = port - bench
    tracking_error = float(np.std(diff, ddof=1)) * math.sqrt(TRADING_DAYS) if n > 1 else 0.0

    result: dict[str, Any] = {
        "available": True,
        "observations": n,
        "beta": beta,
        "correlation": corr,
        "tracking_error_annualised_pct": tracking_error * 100.0,
        "alpha_annualised_pct": None,
        "information_ratio": None,
        "alpha_reasons": [],
    }
    if n >= min_alpha_observations:
        mean_excess = float(np.mean(diff))
        std_excess = float(np.std(diff, ddof=1))
        result["alpha_annualised_pct"] = mean_excess * TRADING_DAYS * 100.0
        # Guard with ptp (exact constant series) so float noise (~1e-19) on a
        # degenerate constant excess does not produce a bogus IR.
        if std_excess > 0 and float(np.ptp(diff)) > 0:
            result["information_ratio"] = (mean_excess / std_excess) * math.sqrt(TRADING_DAYS)
        else:
            result["alpha_reasons"].append("zero tracking variance: IR undefined")
    else:
        result["alpha_reasons"].append(
            f"alpha/IR require >= {min_alpha_observations} paired observations; have {n}"
        )
    return result


# ---------------------------------------------------------------------------
# Top-level orchestration (pure)
# ---------------------------------------------------------------------------


def _unavailable(reasons: list[str]) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "reasons": reasons,
        "notes": [],
        "aligned": None,
        "covariance_annualised": None,
        "correlation": None,
        "annualised_factor_volatility_pct": {},
        "euler_vol_contribution_pct": {},
        "euler_sum_check": None,
        "annualised_portfolio_volatility_pct": None,
        "factor_weights": {},
        "benchmark": None,
    }


def compute_risk_analysis(inp: RiskAnalysisInput) -> dict[str, Any]:
    """Run the full pure risk analysis for one current composition."""
    base: dict[str, Any] = {
        "status": "available",
        "reasons": [],
        "notes": [],
        "full_book_weights": dict(inp.full_book_weights),
        "unsupported_factors": [
            {
                "name": factor.name,
                "full_book_weight": inp.full_book_weights.get(factor.name),
            }
            for factor in inp.unsupported
        ],
    }

    if inp.total_value_gbp is not None and inp.total_value_gbp <= 0:
        base.update(**_unavailable(["zero total value"]))
        return base

    # Cash-only book: defined, zero risk, no covariance input.
    if not inp.factors:
        if inp.cash_weight > 0:
            base.update(
                **{
                    "status": "available",
                    "reasons": [],
                    "notes": ["cash-only composition: zero volatility"],
                    "aligned": None,
                    "covariance_annualised": None,
                    "correlation": None,
                    "annualised_factor_volatility_pct": {},
                    "annualised_portfolio_volatility_pct": 0.0,
                    "euler_vol_contribution_pct": {"cash": 0.0},
                    "euler_sum_check": {
                        "contribution_sum_pct": 0.0,
                        "sigma_pct": 0.0,
                        "matches": True,
                    },
                    "factor_weights": {"cash": inp.cash_weight},
                }
            )
            return base
        reasons = ["no supported factors and no cash weight"]
        base.update(**_unavailable(reasons))
        return base

    factor_names = [factor.name for factor in inp.factors]
    weight_vector = np.array(
        [inp.sleeve_weights.get(name, 0.0) for name in factor_names] + [inp.cash_weight],
        dtype=float,
    )
    if not np.all(np.isfinite(weight_vector)) or np.any(weight_vector < 0):
        base.update(**_unavailable(["non-finite or negative sleeve weights"]))
        return base
    unknown = set(inp.sleeve_weights) - set(factor_names)
    if unknown:
        base.update(**_unavailable([f"weight for unknown factor: {sorted(unknown)}"]))
        return base
    if abs(float(weight_vector.sum()) - 1.0) > 1e-6:
        base.update(
            **_unavailable(
                [f"sleeve weights do not normalise (sum={float(weight_vector.sum()):.6f})"]
            )
        )
        return base

    common, returns, align_reasons = aligned_daily_returns(inp.factors)
    if align_reasons:
        base.update(**_unavailable(align_reasons))
        return base

    cov = sample_covariance(returns)
    corr = correlation_matrix(cov)
    factor_weights = weight_vector[:-1]  # cash adds zero variance
    euler = euler_vol_contribution(cov, factor_weights)

    factor_vols = {
        name: annualised_volatility(returns[i]) * 100.0 for i, name in enumerate(factor_names)
    }
    euler_pct = {
        name: value * 100.0
        for name, value in zip(factor_names, euler["contributions_annualised"], strict=True)
    }
    euler_pct["cash"] = 0.0
    sigma_pct = euler["sigma_annualised"] * 100.0

    result = {
        "status": "available",
        "reasons": [],
        "notes": base["notes"],
        "aligned": {
            "first": common[0].isoformat(),
            "last": common[-1].isoformat(),
            "observations": int(returns.shape[1]),
        },
        "covariance_annualised": (cov * TRADING_DAYS).tolist(),
        "correlation": None if corr is None else corr.tolist(),
        "annualised_factor_volatility_pct": factor_vols,
        "annualised_portfolio_volatility_pct": sigma_pct,
        "euler_vol_contribution_pct": euler_pct,
        "euler_sum_check": {
            "contribution_sum_pct": float(np.sum(list(euler_pct.values()))),
            "sigma_pct": sigma_pct,
            "matches": euler["sum_matches_sigma"],
        },
        "factor_weights": {
            **dict(zip(factor_names, factor_weights.tolist(), strict=True)),
            "cash": float(inp.cash_weight),
        },
        "full_book_weights": dict(inp.full_book_weights),
        "unsupported_factors": base["unsupported_factors"],
        "benchmark": None,
    }

    if inp.benchmark_prices:
        bench_map = {date: float(price) for date, price in inp.benchmark_prices}
        bench_dates = [date for date in common if date in bench_map]
        if len(bench_dates) < 2:
            result["benchmark"] = {
                "available": False,
                "reasons": ["insufficient benchmark overlap with factor dates"],
            }
        else:
            # Pair by return end-date so a missing benchmark observation
            # drops the pair instead of forward-filling.
            port_by_end = {common[j + 1]: returns[:, j] for j in range(len(common) - 1)}
            paired_end_dates: list[dt.date] = []
            port_pairs: list[np.ndarray] = []
            bench_pairs: list[float] = []
            for j in range(len(bench_dates) - 1):
                end_date = bench_dates[j + 1]
                start_price = bench_map[bench_dates[j]]
                if end_date in port_by_end and start_price > 0:
                    paired_end_dates.append(end_date)
                    port_pairs.append(port_by_end[end_date])
                    bench_pairs.append(bench_map[end_date] / start_price - 1.0)
            if len(paired_end_dates) < 2:
                result["benchmark"] = {
                    "available": False,
                    "reasons": ["insufficient paired benchmark observations"],
                }
            else:
                port_matrix = np.column_stack(port_pairs)
                result["benchmark"] = benchmark_metrics(port_matrix, np.asarray(bench_pairs, dtype=float))
    else:
        result["benchmark"] = {"available": False, "reasons": ["no benchmark series provided"]}

    return result

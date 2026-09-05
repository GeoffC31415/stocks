"""Portfolio growth + risk metrics.

Computes growth and risk statistics (total/annualised return, volatility,
Sharpe/Sortino, max drawdown) from the snapshot-derived portfolio value
series, and returns a normalized growth curve that is directly comparable
to the rebased benchmark series used elsewhere.

The pure ``compute_performance_metrics`` function is deterministic and
DB-free so the statistics can be unit tested against synthetic series.
"""

from __future__ import annotations

import datetime as dt
import math
import statistics
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import HoldingSnapshot, ImportBatch, Instrument, Order
from app.services.market_data_service import fetch_history
from app.services.portfolio_service import (
    MIN_ANNUALISATION_DAYS,
    classify_external_flows,
)

# Period -> trailing day count. ``ALL`` means "from the first snapshot".
# ``YTD`` is resolved relative to the window end (Jan 1 of that year).
PERIOD_OPTIONS: dict[str, int | None] = {
    "1M": 30,
    "3M": 91,
    "6M": 183,
    "1Y": 365,
    "YTD": None,  # handled specially
    "ALL": None,
}

TRADING_DAYS_PER_YEAR = 365.25


def resolve_period_start(period: str, reference: dt.date) -> dt.date | None:
    """Resolve the inclusive window start for a period label.

    Returns ``None`` for ``ALL`` (use the earliest available point).
    """
    if period == "ALL":
        return None
    if period == "YTD":
        return dt.date(reference.year, 1, 1)
    days = PERIOD_OPTIONS.get(period)
    if days is None:
        raise ValueError(f"Unknown period: {period}")
    return reference - dt.timedelta(days=days)


def _annualisation_factor(dates: list[dt.date]) -> float:
    """Average annualization multiplier from the mean period length.

    For N dated points there are N-1 return periods spanning ``total_days``.
    The number of such periods that fit in a year is ``365.25 / avg_period``.
    """
    if len(dates) < 2:
        return 1.0
    total_days = (dates[-1] - dates[0]).days
    if total_days <= 0:
        return 1.0
    avg_period_days = total_days / (len(dates) - 1)
    if avg_period_days <= 0:
        return 1.0
    return TRADING_DAYS_PER_YEAR / avg_period_days


def compute_performance_metrics(
    points: list[tuple[dt.date, float]],
    *,
    risk_free_annual_pct: float = 0.0,
) -> dict:
    """Compute growth + risk statistics from dated portfolio value points.

    ``points`` is a chronologically ordered list of ``(date, value_gbp)``.
    Returns a dict matching ``PerformanceSummary`` (minus growth/benchmarks).
    """
    base: dict = {
        "period_start": None,
        "period_end": None,
        "start_value_gbp": None,
        "end_value_gbp": None,
        "total_return_pct": None,
        "annualised_return_pct": None,
        "annualised_volatility_pct": None,
        "sharpe_ratio": None,
        "sortino_ratio": None,
        "max_drawdown_pct": None,
        "best_period_return_pct": None,
        "worst_period_return_pct": None,
        "num_periods": 0,
        "annualisation_factor": None,
        "risk_free_annual_pct": risk_free_annual_pct,
        "method": "arithmetic period returns on snapshot-derived portfolio value",
        "notes": [],
    }
    if not points:
        base["notes"].append("No dated portfolio values are available.")
        return base
    if len(points) < 2:
        base["period_start"] = points[0][0]
        base["period_end"] = points[0][0]
        base["start_value_gbp"] = points[0][1]
        base["end_value_gbp"] = points[0][1]
        base["notes"].append("At least two dated portfolio values are required for return metrics.")
        return base

    dates = [p[0] for p in points]
    values = [p[1] for p in points]
    start_value = values[0]
    end_value = values[-1]

    base.update(
        period_start=dates[0],
        period_end=dates[-1],
        start_value_gbp=round(start_value, 2),
        end_value_gbp=round(end_value, 2),
    )

    # Simple total return on the value series.
    if start_value > 0:
        base["total_return_pct"] = round((end_value / start_value - 1.0) * 100.0, 4)
    else:
        base["notes"].append("Starting value is not positive, so total return is unavailable.")

    # Geometric annualised return.
    total_days = (dates[-1] - dates[0]).days
    years = total_days / TRADING_DAYS_PER_YEAR
    if start_value > 0 and end_value > 0 and years > 0:
        base["annualised_return_pct"] = round(
            ((end_value / start_value) ** (1.0 / years) - 1.0) * 100.0, 4
        )
    elif years <= 0:
        base["notes"].append("Annualised return is unavailable for a zero-length window.")

    # Period returns.
    period_returns: list[float] = []
    for i in range(1, len(values)):
        prev = values[i - 1]
        if prev <= 0:
            continue
        period_returns.append(values[i] / prev - 1.0)
    n = len(period_returns)
    base["num_periods"] = n

    if n == 0:
        base["notes"].append("No positive prior value available to form period returns.")
        return base

    ann_factor = _annualisation_factor(dates)
    base["annualisation_factor"] = round(ann_factor, 4)
    mean_r = statistics.fmean(period_returns)
    base["best_period_return_pct"] = round(max(period_returns) * 100.0, 4)
    base["worst_period_return_pct"] = round(min(period_returns) * 100.0, 4)

    # Max drawdown on the *raw* value series (peak-to-trough, in percent).
    # The payload overlays the flow-adjusted drawdown as the primary value and
    # keeps this as ``max_drawdown_raw_pct``; a raw drawdown is distorted by
    # cash being added or taken out of the account.
    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (v - peak) / peak
            if dd < max_dd:
                max_dd = dd
    base["max_drawdown_pct"] = round(max_dd * 100.0, 4)

    # Risk metrics require a variance estimate (>= 2 periods).
    rf_per_period = (risk_free_annual_pct / 100.0) / ann_factor if ann_factor > 0 else 0.0
    if n < 2:
        base["notes"].append(
            "At least two period returns are required for volatility and risk ratios."
        )
        return base

    std_r = statistics.stdev(period_returns)
    sqrt_ann = math.sqrt(ann_factor)
    if std_r == 0.0:
        base["annualised_volatility_pct"] = 0.0
        base["notes"].append("Period returns have zero variance, so Sharpe is undefined.")
        return base

    base["annualised_volatility_pct"] = round(std_r * sqrt_ann * 100.0, 4)
    sharpe = ((mean_r - rf_per_period) / std_r) * sqrt_ann
    base["sharpe_ratio"] = round(sharpe, 4)

    # Sortino: downside deviation relative to the per-period risk-free hurdle.
    downside = [min(r - rf_per_period, 0.0) for r in period_returns]
    downside_dev = math.sqrt(statistics.fmean([d * d for d in downside]))
    if downside_dev > 0:
        sortino = ((mean_r - rf_per_period) / downside_dev) * sqrt_ann
        base["sortino_ratio"] = round(sortino, 4)
    else:
        base["notes"].append("No downside periods in the window, so Sortino is undefined.")
    return base


def _dietz_interval_return(
    value_prev: float,
    value_next: float,
    raw_flow: float,
    weighted_flow: float,
) -> float | None:
    """Modified Dietz return for one interval.

    Uses the standard Modified Dietz form shared with the returns card: the
    **raw** signed net flow in the numerator (money added is not gain, money
    removed is not a loss) and the **weighted** flow in the denominator (a
    flow earns credit for the time it actually sat in the account).

    ``raw_flow`` is the signed net flow in the interval (contributions +,
    withdrawals −); ``weighted_flow`` is that flow weighted by hold duration.
    Returns ``None`` when the interval is unusable (non-positive prior value
    or a non-positive denominator).
    """
    if not all(math.isfinite(v) for v in (value_prev, value_next, raw_flow, weighted_flow)):
        return None
    if value_prev <= 0 or value_next < 0:
        return None
    denominator = value_prev + weighted_flow
    if denominator <= 0:
        return None
    result = (value_next - (value_prev + raw_flow)) / denominator
    return result if math.isfinite(result) and result >= -1 else None


def _interval_dietz_returns(
    points: list[tuple[dt.date, float]],
    signed_flows: list[tuple[dt.date, float]],
) -> list[tuple[dt.date, float | None]]:
    """Per-interval Modified Dietz returns, one entry per usable snapshot interval.

    Returns ``[(date_of_interval_end, dietz_return | None), ...]`` where the
    return is ``None`` for an interval whose prior value or denominator is
    non-positive (unusable). A flow on the interval start date is already part
    of the start value, so it is excluded from that interval's numerator.
    """
    dates = [p[0] for p in points]
    values = [p[1] for p in points]
    out: list[tuple[dt.date, float | None]] = []
    for i in range(1, len(values)):
        span_start = dates[i - 1]
        span_end = dates[i]
        interval_days = (span_end - span_start).days
        if interval_days <= 0:
            continue
        raw_flow = 0.0
        weighted_flow = 0.0
        for flow_date, amount in signed_flows:
            if span_start < flow_date <= span_end:
                raw_flow += amount
                weighted_flow += amount * ((span_end - flow_date).days / interval_days)
        out.append(
            (
                span_end,
                _dietz_interval_return(values[i - 1], values[i], raw_flow, weighted_flow),
            )
        )
    return out


def build_flow_adjusted_curve(
    points: list[tuple[dt.date, float]],
    signed_flows: list[tuple[dt.date, float]],
) -> list[dict]:
    """Chain-link valid interval Modified Dietz returns into a wealth index.

    The index starts at 100 on the first snapshot date. Each usable interval
    multiplies the running index by ``(1 + dietz_return)``. An unusable
    interval makes the curve unavailable rather than inventing a flat return.
    A valid pure contribution with no market gain keeps the index flat.
    Deterministic and DB-free.
    """
    if len(points) < 2:
        return []
    curve: list[dict] = [{"date": points[0][0], "index": 100.0}]
    index = 100.0
    for date, interval_return in _interval_dietz_returns(points, signed_flows):
        if interval_return is None:
            return []
        index = index * (1.0 + interval_return)
        curve.append({"date": date, "index": round(index, 4)})
    return curve


def build_drawdown_curve(curve: list[dict]) -> list[dict]:
    """Drawdown (in percent, <= 0) of a flow-adjusted wealth index.

    Each point carries ``date``, ``index``, ``drawdown_pct`` and ``at_peak``.
    ``drawdown_pct`` is ``(index - running_peak) / running_peak * 100`` and is
    0.0 whenever the index is at or above its running peak. A drawdown
    "recovers" (returns to 0.0) once the index reaches a new peak.
    """
    out: list[dict] = []
    peak = 0.0
    for point in curve:
        index = point["index"]
        if index > peak:
            peak = index
        at_peak = peak > 0 and index >= peak
        drawdown_pct = (index - peak) / peak * 100.0 if peak > 0 else 0.0
        out.append(
            {
                "date": point["date"],
                "index": index,
                "drawdown_pct": round(drawdown_pct, 4),
                "at_peak": at_peak,
            }
        )
    return out


def max_flow_adjusted_drawdown(curve: list[dict]) -> float | None:
    """Deepest flow-adjusted drawdown (most negative percent) across the index.

    Returns ``None`` when the curve is empty. A monotonic or flat index yields 0.0.
    """
    if not curve:
        return None
    values = [p["drawdown_pct"] for p in build_drawdown_curve(curve)]
    if not values:
        return None
    return round(min(values), 4)


def compute_flow_adjusted_metrics(
    points: list[tuple[dt.date, float]],
    signed_flows: list[tuple[dt.date, float]],
    *,
    contributions: float,
    withdrawals: float,
    risk_free_annual_pct: float = 0.0,
) -> dict:
    """Growth + risk with external cashflows netted out (Modified Dietz).

    ``signed_flows`` are ``(date, signed_amount)`` external cashflows
    (contributions positive, withdrawals negative) for the window, already
    classified via ``classify_external_flows``. This is the flow-aware
    counterpart to :func:`compute_performance_metrics`; it exists because a
    raw value series conflates market movement with cash being added or
    removed, so volatility/Sharpe/Sortino would be distorted by those flows.

    A contribution (e.g. a manual HL cash injection + new orders) is *not*
    portfolio gain; a withdrawal is *not* a loss. Modified Dietz removes the
    flow effect from the return, and the per-interval Dietz returns are used
    for the risk statistics so the risk metrics are also flow-adjusted.
    """
    base: dict = {
        "contributions_gbp": round(contributions, 2),
        "withdrawals_gbp": round(withdrawals, 2),
        "net_external_flow_gbp": round(contributions - withdrawals, 2),
        "total_return_pct": None,
        "annualised_return_pct": None,
        "annualised_volatility_pct": None,
        "sharpe_ratio": None,
        "sortino_ratio": None,
        "num_periods": 0,
        "annualisation_factor": None,
        "method": "Chain-linked interval Modified Dietz on snapshot-derived portfolio value",
        "notes": [
            "Returns are flow-adjusted: external contributions (manual cash + new "
            "orders) and withdrawals are netted out via Modified Dietz, so growth "
            "reflects market movement rather than money added to or taken from "
            "the account. DRIP buys are internal and excluded."
        ],
    }
    if len(points) < 2:
        base["notes"].append(
            "At least two dated portfolio values are required for flow-adjusted metrics."
        )
        return base

    dates = [p[0] for p in points]
    # KPI, wealth curve and risk statistics share the same interval returns.
    total_days = (dates[-1] - dates[0]).days
    intervals = _interval_dietz_returns(points, signed_flows)
    if len(intervals) != len(points) - 1 or any(value is None for _, value in intervals):
        base["notes"].append("An unusable snapshot interval prevents a complete flow-adjusted return.")
        return base
    interval_returns = [value for _, value in intervals if value is not None]
    if interval_returns:
        period_return = math.prod(1.0 + value for value in interval_returns) - 1.0
        base["total_return_pct"] = round(period_return * 100.0, 4)
        if total_days >= MIN_ANNUALISATION_DAYS and period_return > -1:
            years = total_days / TRADING_DAYS_PER_YEAR
            base["annualised_return_pct"] = round(
                ((1.0 + period_return) ** (1.0 / years) - 1.0) * 100.0, 4
            )
        elif total_days < MIN_ANNUALISATION_DAYS:
            base["notes"].append(
                "Annualised flow-adjusted return is unavailable for periods under 365 days."
            )

    n = len(interval_returns)
    base["num_periods"] = n
    if n == 0:
        base["notes"].append(
            "No usable interval returns for flow-adjusted volatility or risk ratios."
        )
        return base

    ann_factor = _annualisation_factor(dates)
    base["annualisation_factor"] = round(ann_factor, 4)
    mean_r = statistics.fmean(interval_returns)
    std_r = statistics.stdev(interval_returns) if n >= 2 else 0.0
    sqrt_ann = math.sqrt(ann_factor)
    rf_per_period = (risk_free_annual_pct / 100.0) / ann_factor if ann_factor > 0 else 0.0

    base["annualised_volatility_pct"] = round(std_r * sqrt_ann * 100.0, 4)
    if std_r > 0:
        base["sharpe_ratio"] = round(((mean_r - rf_per_period) / std_r) * sqrt_ann, 4)
    else:
        base["notes"].append("Zero interval-return variance, so flow-adjusted Sharpe is undefined.")

    downside = [min(r - rf_per_period, 0.0) for r in interval_returns]
    downside_dev = math.sqrt(statistics.fmean([d * d for d in downside]))
    if downside_dev > 0:
        base["sortino_ratio"] = round(((mean_r - rf_per_period) / downside_dev) * sqrt_ann, 4)
    else:
        base["notes"].append("No downside intervals in the window, so flow-adjusted Sortino is undefined.")
    return base


async def build_value_series(
    session: AsyncSession,
    *,
    account_name: str | None = None,
) -> tuple[list[dict], dt.date | None]:
    """Reconstruct the portfolio value after each snapshot batch.

    Returns ``(points, coverage_start)`` where each point is
    ``{"as_of_date": dt.date, "value_gbp": float}`` in date order, and
    ``coverage_start`` is the first snapshot date on which *every* account in
    the selection had already been observed (``None`` when a single account is
    selected or no accounts were found).

    Carrying each account's last snapshot forward is how the app defines
    portfolio value (see ``portfolio_value_timeseries``). For the all-account
    view a value is only "complete" once all accounts have coverage, which is
    what ``coverage_start`` encodes.
    """
    batches_result = await session.execute(
        select(ImportBatch).order_by(ImportBatch.as_of_date, ImportBatch.id)
    )
    batches = list(batches_result.scalars().all())
    if not batches:
        return [], None

    snapshot_query = (
        select(HoldingSnapshot)
        .join(Instrument, Instrument.id == HoldingSnapshot.instrument_id)
        .options(selectinload(HoldingSnapshot.instrument))
        .order_by(HoldingSnapshot.import_batch_id)
    )
    if account_name is not None:
        snapshot_query = snapshot_query.where(Instrument.account_name == account_name)
    snapshots_result = await session.execute(snapshot_query)

    by_batch: dict[int, list[HoldingSnapshot]] = defaultdict(list)
    all_account_names: set[str] = set()
    for snapshot in snapshots_result.scalars().all():
        by_batch[snapshot.import_batch_id].append(snapshot)
        all_account_names.add(snapshot.instrument.account_name)

    # ``all_account_names`` is the full set of accounts in the selection, so
    # the coverage anchor is judged against every account (not those seen so far).
    current_by_instrument: dict[int, HoldingSnapshot] = {}
    points: list[dict] = []
    covered_accounts: set[str] = set()
    coverage_start: dt.date | None = None

    for batch in batches:
        for snapshot in by_batch.get(batch.id, []):
            current_by_instrument[snapshot.instrument_id] = snapshot
        for closed in (batch.diff_summary or {}).get("closed", []):
            instrument_id = closed.get("instrument_id")
            if instrument_id is not None:
                current_by_instrument.pop(int(instrument_id), None)

        if not current_by_instrument:
            continue
        covered_accounts |= {s.instrument.account_name for s in current_by_instrument.values()}
        if (
            coverage_start is None
            and len(all_account_names) > 1
            and covered_accounts == all_account_names
        ):
            coverage_start = batch.as_of_date

        total_value = sum(s.value_gbp or 0.0 for s in current_by_instrument.values())
        points.append({"as_of_date": batch.as_of_date, "value_gbp": float(total_value)})
    return points, coverage_start


async def _flow_adjusted_block(
    session: AsyncSession,
    *,
    account_name: str | None,
    points: list[tuple[dt.date, float]],
    window_start: dt.date,
    window_end: dt.date,
    risk_free_annual_pct: float,
) -> dict:
    """Flow-adjusted (Modified Dietz) growth + risk for a window.

    Queries the window's orders, classifies external cashflows with the shared
    ``classify_external_flows`` (so the returns card and this agree), and
    feeds them to the pure :func:`compute_flow_adjusted_metrics`. Never raises;
    on any DB error it returns a ``flow_adjusted`` block flagged as unavailable
    so the rest of the payload still renders.
    """
    unavailable: dict = {
        "contributions_gbp": 0.0,
        "withdrawals_gbp": 0.0,
        "net_external_flow_gbp": 0.0,
        "total_return_pct": None,
        "annualised_return_pct": None,
        "annualised_volatility_pct": None,
        "sharpe_ratio": None,
        "sortino_ratio": None,
        "num_periods": 0,
        "annualisation_factor": None,
        "method": "Chain-linked interval Modified Dietz on snapshot-derived portfolio value",
        "notes": ["Flow-adjusted metrics are unavailable for this window."],
        "flow_adjusted_curve": [],
        "drawdown_curve": [],
        "max_drawdown_pct": None,
    }
    try:
        orders_query = select(Order).where(
            Order.order_date >= dt.datetime.combine(window_start, dt.time.min),
            Order.order_date <= dt.datetime.combine(window_end, dt.time.max),
        )
        if account_name is not None:
            orders_query = orders_query.where(Order.account_name == account_name)
        orders_result = await session.execute(orders_query.order_by(Order.order_date))
        contributions, withdrawals, signed_flows = classify_external_flows(
            orders_result.scalars().all()
        )
    except Exception:  # noqa: BLE001 - a flow query failure should not kill the panel
        return unavailable

    block = compute_flow_adjusted_metrics(
        points,
        signed_flows,
        contributions=contributions,
        withdrawals=withdrawals,
        risk_free_annual_pct=risk_free_annual_pct,
    )

    # Chain-linked flow-adjusted wealth index + its drawdown, so the KPI max
    # drawdown and the main curve agree on the same interval series.
    flow_curve = build_flow_adjusted_curve(points, signed_flows)
    block["flow_adjusted_curve"] = flow_curve
    block["drawdown_curve"] = build_drawdown_curve(flow_curve)
    block["max_drawdown_pct"] = max_flow_adjusted_drawdown(flow_curve)
    return block


async def get_portfolio_performance(
    session: AsyncSession,
    *,
    account_name: str | None = None,
    period: str = "ALL",
    risk_free_annual_pct: float = 0.0,
    benchmark_symbols: list[str] | None = None,
) -> dict:
    """Assemble the performance payload for a period window.

    Reuses the snapshot-derived value series (the authoritative account
    value) and, when network access is available, rebased benchmark
    series for visual comparison. Benchmark failures never fail the call.
    """
    if period not in PERIOD_OPTIONS:
        raise ValueError(f"Unknown period: {period}")

    series, coverage_start = await build_value_series(session, account_name=account_name)
    if not series:
        return {
            "period": period,
            "period_start": None,
            "period_end": None,
            "start_value_gbp": None,
            "end_value_gbp": None,
            "total_return_pct": None,
            "annualised_return_pct": None,
            "annualised_volatility_pct": None,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "max_drawdown_pct": None,
            "best_period_return_pct": None,
            "worst_period_return_pct": None,
            "num_periods": 0,
            "annualisation_factor": None,
            "risk_free_annual_pct": risk_free_annual_pct,
            "method": "arithmetic period returns on snapshot-derived portfolio value",
            "notes": ["No portfolio snapshots are available for this selection."],
            "coverage_start": None,
            "growth_curve": [],
            "benchmarks": [],
            "max_drawdown_raw_pct": None,
            "flow_adjusted_curve": [],
            "drawdown_curve": [],
            "flow_adjusted": None,
        }

    all_points: list[tuple[dt.date, float]] = [(p["as_of_date"], p["value_gbp"]) for p in series]
    all_points.sort(key=lambda p: p[0])

    # All-account growth is only meaningful once every account has been
    # observed; anchor the window to that coverage date when it is available.
    reference = all_points[-1][0]
    window_start = resolve_period_start(period, reference)
    if coverage_start is not None:
        window_start = (
            max(window_start, coverage_start) if window_start is not None else coverage_start
        )

    window = all_points if window_start is None else [p for p in all_points if p[0] >= window_start]
    if not window:
        window = [all_points[-1]]

    metrics = compute_performance_metrics(
        window,
        risk_free_annual_pct=risk_free_annual_pct,
    )
    if (
        coverage_start is not None
        and window
        and window[0][0] == coverage_start
        and period in ("1M", "3M", "6M", "1Y", "YTD")
    ):
        metrics["notes"].insert(
            0,
            "The window starts at the first date every selected account had snapshot coverage, "
            "so growth reflects complete-portfolio returns.",
        )

    # Normalized growth curve: 100 at the window start.
    base_value = window[0][1] or 0.0
    growth_curve: list[dict] = []
    for d, v in window:
        normalized = (v / base_value * 100.0) if base_value > 0 else None
        growth_curve.append(
            {
                "as_of_date": d,
                "value_gbp": round(v, 2),
                "normalized_value": round(normalized, 4) if normalized is not None else None,
            }
        )

    benchmarks: list[dict] = []
    if benchmark_symbols:
        for symbol in benchmark_symbols:
            try:
                rows = await fetch_history(session, symbol, start=window_start, base_value=100.0)
            except Exception:  # noqa: BLE001 - network/parse failures are non-fatal
                continue
            for row in rows:
                benchmarks.append(
                    {
                        "date": row["date"],
                        "symbol": row["symbol"],
                        "value": round(float(row["rebased_value"]), 4),
                    }
                )
    benchmarks.sort(key=lambda r: (r["date"], r["symbol"]))

    # --- Flow-adjusted (Modified Dietz) metrics. ---
    # External cashflows in the window are netted out so the HL cash
    # injection + new orders don't masquerade as market gain. The flow
    # classification is shared with the returns card so the two agree.
    window_start_date = window[0][0]
    window_end_date = window[-1][0]
    flow_adjusted = await _flow_adjusted_block(
        session,
        account_name=account_name,
        points=window,
        window_start=window_start_date,
        window_end=window_end_date,
        risk_free_annual_pct=risk_free_annual_pct,
    )

    payload = {
        "period": period,
        "coverage_start": coverage_start,
        **metrics,
        # The raw-value drawdown is kept under a distinct name so the primary
        # max_drawdown_pct can be the flow-adjusted one (cash flows no longer
        # distort the displayed drawdown).
        "max_drawdown_raw_pct": metrics.get("max_drawdown_pct"),
        "growth_curve": growth_curve,
        "benchmarks": benchmarks,
        "flow_adjusted": flow_adjusted,
        # Chain-linked flow-adjusted index + drawdown, mirrored at top level so
        # the UI's primary line and headline KPI share one interval series.
        "flow_adjusted_curve": flow_adjusted.get("flow_adjusted_curve", []),
        "drawdown_curve": flow_adjusted.get("drawdown_curve", []),
        "max_drawdown_pct": (
            flow_adjusted.get("max_drawdown_pct")
            if flow_adjusted.get("max_drawdown_pct") is not None
            else metrics.get("max_drawdown_pct")
        ),
    }
    return payload

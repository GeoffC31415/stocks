"""Orchestrates the current-portfolio risk analysis (Task 4).

Reads the latest holdings for the selected account scope, splits them into
cash / supported factors / unsupported holdings, loads ONLY cached market
history (plus cached FX for non-GBP series) and feeds the pure maths in
:mod:`app.services.risk_service`.

No network access: an empty market cache simply produces a report with
``available=false`` and explicit reasons — it never triggers a live fetch
and never converts missing data into zeros.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models import HoldingSnapshot, ImportBatch, Instrument, MarketFxPoint
from app.services.market_data_coverage import COVERAGE_GATE_PCT, STALE_AFTER_DAYS
from app.services.market_data_service import (
    SOURCE,
    fx_pair_for_currency,
    load_points,
)
from app.services.risk_service import (
    RiskAnalysisInput,
    RiskFactorSeries,
    compute_risk_analysis,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

#: Fewer aligned daily observations than this: the report carries
#: ``available=false`` with an explicit reason.
MIN_OBSERVATIONS = 126


async def _latest_batch_for_scope(
    session: AsyncSession, account_name: str | None
) -> ImportBatch | None:
    query = select(ImportBatch)
    if account_name is not None:
        query = (
            query.join(HoldingSnapshot, HoldingSnapshot.import_batch_id == ImportBatch.id)
            .join(Instrument, Instrument.id == HoldingSnapshot.instrument_id)
            .where(Instrument.account_name == account_name)
        )
    query = query.order_by(ImportBatch.as_of_date.desc(), ImportBatch.id.desc()).limit(1)
    return (await session.execute(query)).scalar_one_or_none()


def _scope_instrument_filter(account_name: str | None) -> Any:
    """Instrument filter for the scope; None means all open instruments."""
    if account_name is None:
        return None
    return Instrument.account_name == account_name


async def _latest_snapshots_for_scope(
    session: AsyncSession, account_name: str | None, batch_id: int
) -> list[HoldingSnapshot]:
    """All current open exposures, ranked by valuation date then import ID."""
    instrument_filter = _scope_instrument_filter(account_name)
    if instrument_filter is not None:
        open_ids = list(
            (
                await session.execute(
                    select(Instrument.id).where(
                        Instrument.account_name == account_name,
                        Instrument.closed_at.is_(None),
                    )
                )
            ).scalars().all()
        )
        if not open_ids:
            return []

    latest_by_instrument = (
        select(
            HoldingSnapshot.id.label("snapshot_id"),
            func.row_number().over(
                partition_by=HoldingSnapshot.instrument_id,
                order_by=(ImportBatch.as_of_date.desc(), ImportBatch.id.desc()),
            ).label("rank"),
        )
        .join(ImportBatch, ImportBatch.id == HoldingSnapshot.import_batch_id)
        .subquery()
    )
    query = (
        select(HoldingSnapshot)
        .options(selectinload(HoldingSnapshot.instrument), selectinload(HoldingSnapshot.batch))
        .join(
            latest_by_instrument,
            (HoldingSnapshot.id == latest_by_instrument.c.snapshot_id)
            & (latest_by_instrument.c.rank == 1),
        )
        .join(Instrument, Instrument.id == HoldingSnapshot.instrument_id)
        .join(ImportBatch, ImportBatch.id == HoldingSnapshot.import_batch_id)
        .where(
            Instrument.closed_at.is_(None),
        )
    )
    if instrument_filter is not None:
        query = query.where(Instrument.account_name == account_name)
    return list((await session.execute(query)).scalars().all())


async def _load_gbp_series(
    session: AsyncSession, ticker: str, currency: str | None,
    *, issues: list[str] | None = None,
    as_of: dt.date | None = None,
) -> list[tuple[dt.date, float]] | None:
    """Cached, GBP-converted price series for a ticker; None when unusable."""
    points = await load_points(session, ticker, source=SOURCE)
    if as_of is not None:
        if issues is not None and any(point.date > as_of for point in points):
            issues.append(f"{ticker}: excluded cached prices after valuation date {as_of.isoformat()}")
        points = [point for point in points if point.date <= as_of]
    if len(points) < 2:
        return None
    if currency not in {"GBP", "GBp", "GBX", "USD", "EUR"}:
        return None
    issue = None
    if any(point.currency != currency for point in points):
        issue = "inconsistent currency"
    adjusted = [point.adjusted_close is not None for point in points]
    if any(adjusted) and not all(adjusted):
        issue = "mixed price basis: incomplete adjusted history"
    if issue:
        if issues is not None:
            issues.append(issue)
        return None
    pair = fx_pair_for_currency(currency)
    rates: dict[dt.date, float] = {}
    if pair is not None:
        rows = (await session.execute(
            select(MarketFxPoint).where(
                MarketFxPoint.source == SOURCE, MarketFxPoint.pair == pair
            )
        )).scalars().all()
        rates = {row.date: row.rate for row in rows}
    series: list[tuple[dt.date, float]] = []
    for point in points:
        close = point.adjusted_close if point.adjusted_close is not None else point.close
        if close is None or close <= 0:
            continue
        if pair is not None:
            rate = rates.get(point.date)
            if rate is None or rate <= 0:
                continue
            value = float(close) / rate
        else:
            value = float(close) / (100.0 if currency in {"GBp", "GBX"} else 1.0)
        series.append((point.date, value))
    series.sort(key=lambda item: item[0])
    return series if len(series) >= 2 else None


def _factor_names(analysis: dict[str, Any] | None) -> list[str]:
    if not analysis:
        return []
    weights = analysis.get("factor_weights") or {}
    return [name for name in weights if name != "cash"]


async def portfolio_risk_analysis(
    session: AsyncSession,
    *,
    account_name: str | None = None,
    benchmark_symbols: list[str] | None = None,
) -> dict[str, Any]:
    """Build the full risk-analysis payload (see module docstring)."""
    batch = await _latest_batch_for_scope(session, account_name)
    if batch is None:
        return _unavailable_report(
            reasons=["no import batches found"],
            account_name=account_name,
        )
    valuation_date = batch.as_of_date
    snapshots = await _latest_snapshots_for_scope(session, account_name, batch.id)
    if not snapshots:
        return _unavailable_report(
            reasons=["no open holdings in scope"],
            account_name=account_name,
            valuation_date=valuation_date,
        )

    values = [float(s.value_gbp or 0.0) for s in snapshots]
    if any(not math.isfinite(v) for v in values) or not math.isfinite(sum(abs(v) for v in values)):
        return _unavailable_report(
            reasons=["non-finite holding value or aggregate overflow; coverage unavailable"],
            account_name=account_name,
            valuation_date=valuation_date,
        )
    cash_value = 0.0
    holdings: list[HoldingSnapshot] = []
    for snapshot in snapshots:
        value = float(snapshot.value_gbp or 0.0)
        if snapshot.instrument.is_cash:
            cash_value += value
        else:
            holdings.append(snapshot)
    total_value = cash_value + sum(float(s.value_gbp or 0.0) for s in holdings)
    valuation_mismatches = [
        f"{s.instrument.account_name}/{s.instrument.id}: {s.batch.as_of_date.isoformat()}"
        for s in snapshots if s.batch.as_of_date != valuation_date
    ]

    # Group holdings by canonical ticker; duplicate symbols aggregate and
    # keep their instrument/account constituents.
    by_ticker: dict[str, list[HoldingSnapshot]] = {}
    unticked: list[HoldingSnapshot] = []
    for snapshot in holdings:
        ticker = (snapshot.instrument.ticker or "").strip()
        if ticker:
            by_ticker.setdefault(ticker, []).append(snapshot)
        else:
            unticked.append(snapshot)

    supported: list[RiskFactorSeries] = []
    supported_values: list[float] = []
    unsupported: list[RiskFactorSeries] = []
    unsupported_values: list[float] = []
    stale_tickers: list[str] = []
    factor_details: dict[str, dict[str, Any]] = {}
    cache_warnings: list[str] = []

    for ticker in sorted(by_ticker):
        group = by_ticker[ticker]
        group_value = sum(float(s.value_gbp or 0.0) for s in group)
        names = {s.instrument.security_name for s in group if s.instrument.security_name}
        name = f"ticker:{ticker}"
        constituents = tuple(
            (s.instrument.id, s.instrument.account_name) for s in group
        )
        factor_details[name] = {"labels": sorted(names), "constituents": constituents}
        currency = None
        currency_rows = (
            await load_points(session, ticker, source=SOURCE, start=None)
        )
        if currency_rows:
            currency = currency_rows[0].currency
        series_issues: list[str] = []
        series = await _load_gbp_series(
            session, ticker, currency, issues=series_issues, as_of=valuation_date
        )
        cache_warnings.extend(series_issues)
        if series is None:
            pair = fx_pair_for_currency(currency or "GBP")
            reason = (
                f"missing fx ({pair})" if pair is not None else "no cached series"
            )
            if series_issues:
                reason = "; ".join(series_issues)
            unsupported.append(
                RiskFactorSeries(
                    name=name, prices=[], constituents=constituents, reason=reason
                )
            )
            unsupported_values.append(group_value)
            continue
        if valuation_date - series[-1][0] > dt.timedelta(days=STALE_AFTER_DAYS):
            stale_tickers.append(ticker)
        supported.append(
            RiskFactorSeries(
                name=name, prices=series, constituents=constituents
            )
        )
        supported_values.append(group_value)

    for snapshot in unticked:
        name = f"instrument:{snapshot.instrument.id}"
        factor_details[name] = {
            "labels": [snapshot.instrument.security_name],
            "constituents": ((snapshot.instrument.id, snapshot.instrument.account_name),),
        }
        unsupported.append(
            RiskFactorSeries(
                name=name,
                prices=[],
                constituents=((snapshot.instrument.id, snapshot.instrument.account_name),),
                reason="no ticker",
            )
        )
        unsupported_values.append(float(snapshot.value_gbp or 0.0))

    supported_value = sum(supported_values)
    unsupported_value = sum(unsupported_values)
    denominator = supported_value + cash_value
    sleeve_weights = {
        factor.name: (value / denominator) if denominator > 0 else 0.0
        for factor, value in zip(supported, supported_values, strict=True)
    }
    full_book_weights: dict[str, float] = {
        **{
            factor.name: (value / total_value) if total_value else 0.0
            for factor, value in zip(supported, supported_values, strict=True)
        },
        **{
            factor.name: (value / total_value) if total_value else 0.0
            for factor, value in zip(unsupported, unsupported_values, strict=True)
        },
        "cash": (cash_value / total_value) if total_value else 0.0,
    }

    benchmark_prices: list[tuple[dt.date, float]] | None = None
    benchmark_used: str | None = None
    if benchmark_symbols:
        for symbol in benchmark_symbols:
            rows = await load_points(session, symbol, source=SOURCE, start=None)
            if len(rows) >= 2:
                benchmark_prices = await _load_gbp_series(
                    session, symbol, rows[0].currency,
                    issues=cache_warnings, as_of=valuation_date,
                )
                if benchmark_prices is not None:
                    benchmark_used = symbol
                    break

    analysis_input = RiskAnalysisInput(
        factors=tuple(supported),
        cash_weight=(cash_value / denominator) if denominator else 0.0,
        sleeve_weights=sleeve_weights,
        full_book_weights=full_book_weights,
        unsupported=tuple(unsupported),
        benchmark_prices=benchmark_prices,
        total_value_gbp=total_value if total_value > 0 else None,
    )
    analysis = compute_risk_analysis(analysis_input)
    analysis["factor_details"] = factor_details

    observations = int((analysis.get("aligned") or {}).get("observations", 0))
    noncash_value = supported_value + unsupported_value
    covered_pct = (supported_value / noncash_value * 100.0) if noncash_value > 0 else None
    gate_met = covered_pct is not None and covered_pct >= COVERAGE_GATE_PCT
    available = (
        analysis["status"] == "available"
        and gate_met
        and observations >= MIN_OBSERVATIONS
        and not valuation_mismatches
    )
    reasons: list[str] = list(analysis.get("reasons") or [])
    if valuation_mismatches:
        reasons.append("inconsistent valuation dates across current holdings")
    if not available:
        if covered_pct is None:
            reasons.append("cash-only or zero-value book: no non-cash history to analyse")
        elif analysis["status"] == "available" and not gate_met:
            reasons.append(
                f"coverage gate not met: {covered_pct:.1f}% of non-cash value covered "
                f"(threshold {COVERAGE_GATE_PCT:.0f}%)"
            )
        if analysis["status"] == "available" and observations < MIN_OBSERVATIONS:
            reasons.append(
                f"insufficient aligned observations: {observations} "
                f"(minimum {MIN_OBSERVATIONS})"
            )

    warnings: list[str] = list(cache_warnings)
    aligned = analysis.get("aligned") or {}
    if aligned.get("last"):
        aligned_last = dt.date.fromisoformat(aligned["last"])
        if valuation_date - aligned_last > dt.timedelta(days=STALE_AFTER_DAYS):
            warnings.append(
                f"stale aligned analysis window: {aligned['first']} to {aligned['last']}; "
                f"staleness measured against valuation date {valuation_date.isoformat()}"
            )
    if valuation_mismatches:
        warnings.append("inconsistent valuation dates (values retained): " + "; ".join(valuation_mismatches))
    if stale_tickers:
        warnings.append(
            f"stale market data (last close older than {STALE_AFTER_DAYS} days): "
            f"{', '.join(stale_tickers)}"
        )
    for factor in unsupported:
        warnings.append(
            f"excluded from risk analysis ({factor.reason}): {factor.name}"
        )

    return {
        "account_name": account_name,
        "valuation_date": valuation_date.isoformat(),
        "available": available,
        "reasons": reasons,
        "analysis": analysis if available else None,
        "factor_names": _factor_names(analysis),
        "benchmark_symbol": benchmark_used,
        "coverage": {
            "total_value_gbp": total_value,
            "cash_value_gbp": cash_value,
            "supported_value_gbp": supported_value,
            "unsupported_value_gbp": unsupported_value,
            "covered_pct": covered_pct,
            "gate_threshold_pct": COVERAGE_GATE_PCT,
            "gate_met": gate_met,
            "observations": observations,
            "min_observations": MIN_OBSERVATIONS,
        },
        "stale_factors": stale_tickers,
        "stale_after_days": STALE_AFTER_DAYS,
        "warnings": warnings,
    }


def _unavailable_report(
    reasons: list[str],
    *,
    account_name: str | None,
    valuation_date: dt.date | None = None,
) -> dict[str, Any]:
    return {
        "account_name": account_name,
        "valuation_date": valuation_date.isoformat() if valuation_date else None,
        "available": False,
        "reasons": reasons,
        "analysis": None,
        "factor_names": [],
        "benchmark_symbol": None,
        "coverage": {
            "total_value_gbp": 0.0,
            "cash_value_gbp": 0.0,
            "supported_value_gbp": 0.0,
            "unsupported_value_gbp": 0.0,
            "covered_pct": None,
            "gate_threshold_pct": COVERAGE_GATE_PCT,
            "gate_met": False,
            "observations": 0,
            "min_observations": MIN_OBSERVATIONS,
        },
        "stale_factors": [],
        "stale_after_days": STALE_AFTER_DAYS,
        "warnings": [],
    }

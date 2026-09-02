"""Read-only market-data coverage report (Task 2, step 7).

Reports, for the open non-cash instruments:
- current GBP value covered vs uncovered, with a per-instrument reason;
- duplicate tickers (the same series backing several accounts);
- commonly aligned dates shared by all cached series;
- stale series (last cached date older than the threshold);
- currency-conversion availability (cached FX rates per needed pair);
- whether the 80% coverage gate is met.

Nothing here touches the network; it only reads instruments, snapshots and
the market cache. Missing data is reported, never converted to zeros.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from app.models import HoldingSnapshot, ImportBatch, Instrument, MarketFxPoint, MarketPricePoint

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

#: A series whose last cached date is older than this is flagged stale.
STALE_AFTER_DAYS = 14

#: The plan's coverage gate: at least this share of current GBP value must be
#: backed by usable market series (after FX conversion).
COVERAGE_GATE_PCT = 80.0

#: Pairs needed to convert non-GBP series into GBP (foreign currency per GBP).
_CURRENCY_TO_PAIR: dict[str, str] = {"USD": "GBPUSD", "EUR": "GBPEUR"}


def to_gbp(value: float, currency: str, pair_rate: float | None) -> float | None:
    """Convert ``value`` in ``currency`` to GBP using a GBP-quoted rate.

    GBP needs no rate. Other currencies need a cached rate for their pair
    (e.g. ``GBPUSD`` = USD per GBP, so GBP = USD / rate). Returns ``None``
    when conversion is not possible — callers must report the gap, not
    assume zeros.
    """
    ccy = (currency or "").upper()
    if ccy == "GBP":
        return float(value)
    if ccy not in _CURRENCY_TO_PAIR or pair_rate is None or pair_rate <= 0:
        return None
    return float(value) / pair_rate


def _fx_pair_needed(currency: str | None) -> str | None:
    ccy = (currency or "").upper()
    if ccy in ("", "GBP"):
        return None
    return _CURRENCY_TO_PAIR.get(ccy)


async def _latest_batch_as_of(session: AsyncSession) -> dt.date | None:
    return (await session.execute(select(func.max(ImportBatch.as_of_date)))).scalar_one_or_none()


async def _series_last_dates(session: AsyncSession) -> dict[str, dt.date]:
    rows = (
        await session.execute(
            select(MarketPricePoint.symbol, func.max(MarketPricePoint.date)).group_by(
                MarketPricePoint.symbol
            )
        )
    ).all()
    return {symbol: last for symbol, last in rows if last is not None}


async def _aligned_dates(session: AsyncSession, tickers: list[str]) -> dict[str, Any]:
    """Dates present in every cached series (the common analysis window)."""
    date_sets: list[set[dt.date]] = []
    for ticker in tickers:
        rows = (
            await session.execute(
                select(MarketPricePoint.date).where(MarketPricePoint.symbol == ticker)
            )
        ).scalars().all()
        if len(rows) >= 2:
            date_sets.append(set(rows))
    if len(date_sets) < 2:
        return {"count": 0, "first": None, "last": None}
    common = set.intersection(*date_sets)
    if not common:
        return {"count": 0, "first": None, "last": None}
    ordered = sorted(common)
    return {"count": len(ordered), "first": ordered[0], "last": ordered[-1]}


async def coverage_report(
    session: AsyncSession,
    *,
    stale_after_days: int = STALE_AFTER_DAYS,
) -> dict[str, Any]:
    """Build the read-only coverage report (see module docstring)."""
    as_of = await _latest_batch_as_of(session)
    last_dates = await _series_last_dates(session)

    instruments = (
        (await session.execute(select(Instrument).order_by(Instrument.id))).scalars().all()
    )
    open_instruments = [inst for inst in instruments if not inst.is_cash and not inst.closed_at]

    # Latest snapshot value per instrument (from the most recent batch).
    latest_snapshot_value: dict[int, float | None] = {}
    if as_of is not None:
        batch_ids = (
            await session.execute(
                select(ImportBatch.id).where(ImportBatch.as_of_date == as_of)
            )
        ).scalars().all()
        if batch_ids:
            rows = (
                await session.execute(
                    select(HoldingSnapshot.instrument_id, HoldingSnapshot.value_gbp)
                    .where(HoldingSnapshot.import_batch_id.in_(batch_ids))
                )
            ).all()
            for instrument_id, value_gbp in rows:
                latest_snapshot_value.setdefault(instrument_id, value_gbp)

    duplicates: dict[str, list[int]] = {}
    for inst in open_instruments:
        if inst.ticker:
            duplicates.setdefault(inst.ticker.strip(), []).append(inst.id)
    duplicates = {ticker: ids for ticker, ids in duplicates.items() if len(ids) > 1}

    # FX availability for every currency we would need to convert.
    symbol_currencies: dict[str, str] = {}
    for ticker in {inst.ticker.strip() for inst in open_instruments if inst.ticker}:
        currency = await _series_currency(session, ticker)
        if currency is not None:
            symbol_currencies[ticker] = currency
    needed_pairs = sorted(
        {
            pair
            for ticker, currency in symbol_currencies.items()
            if (pair := _fx_pair_needed(currency))
        }
    )
    fx: dict[str, Any] = {}
    for pair in needed_pairs:
        row = (
            await session.execute(
                select(MarketFxPoint)
                .where(MarketFxPoint.pair == pair)
                .order_by(MarketFxPoint.date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        fx[pair] = (
            None
            if row is None
            else {"latest_date": row.date, "rate": row.rate, "fetched_at": row.fetched_at}
        )

    entries: list[dict[str, Any]] = []
    total_value = 0.0
    covered_value = 0.0
    for inst in open_instruments:
        value_gbp = latest_snapshot_value.get(inst.id)
        if value_gbp is None:
            value_gbp = 0.0
        total_value += value_gbp

        ticker = (inst.ticker or "").strip()
        currency = symbol_currencies.get(ticker) if ticker else None
        reason: str | None = None
        if not ticker:
            reason = "no ticker"
        elif ticker not in last_dates:
            reason = "no cached series"
        else:
            pair = _fx_pair_needed(currency)
            if pair is not None and fx.get(pair) is None:
                reason = f"missing fx ({pair})"

        status = "covered" if reason is None else "uncovered"
        if status == "covered":
            covered_value += value_gbp
        stale = False
        if ticker in last_dates and as_of is not None:
            stale = last_dates[ticker] < as_of - dt.timedelta(days=stale_after_days)
        entries.append(
            {
                "instrument_id": inst.id,
                "identifier": inst.identifier,
                "ticker": ticker or None,
                "value_gbp": value_gbp,
                "currency": currency,
                "last_date": last_dates.get(ticker) if ticker else None,
                "stale": stale,
                "status": status,
                "reason": reason,
            }
        )

    covered_pct = (covered_value / total_value * 100.0) if total_value > 0 else None
    tickers_with_series = sorted(ticker for ticker in last_dates if ticker)
    aligned = await _aligned_dates(session, tickers_with_series)

    return {
        "as_of": as_of,
        "total_value_gbp": total_value,
        "covered_value_gbp": covered_value,
        "uncovered_value_gbp": total_value - covered_value,
        "coverage_pct": covered_pct,
        "gate": {"threshold_pct": COVERAGE_GATE_PCT, "met": bool(covered_pct is not None and covered_pct >= COVERAGE_GATE_PCT)},
        "duplicates": duplicates,
        "aligned_dates": aligned,
        "fx": fx,
        "stale_series": [
            entry for entry in entries if entry["stale"]
        ],
        "instruments": entries,
    }


async def _series_currency(session: AsyncSession, ticker: str | None) -> str | None:
    """Source currency of the cached series for a ticker, if any."""
    if not ticker:
        return None
    row = (
        await session.execute(
            select(MarketPricePoint.currency)
            .where(MarketPricePoint.symbol == ticker.strip())
            .order_by(MarketPricePoint.date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return row

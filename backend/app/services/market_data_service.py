from __future__ import annotations

import asyncio
import csv
import datetime as dt
import io
import urllib.parse
import urllib.request
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Instrument, InstrumentQuote


def _stooq_symbol(symbol: str) -> str:
    return symbol.strip().lower()


def _fetch_stooq_csv(symbol: str, *, interval: str = "d") -> list[dict[str, str]]:
    params = urllib.parse.urlencode({"s": _stooq_symbol(symbol), "i": interval})
    url = f"https://stooq.com/q/d/l/?{params}"
    with urllib.request.urlopen(url, timeout=12) as response:
        text = response.read().decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(text)))
    return [row for row in rows if row.get("Date") and row.get("Close")]


async def fetch_history(
    symbol: str,
    *,
    start: dt.date | None = None,
    base_value: float = 100.0,
) -> list[dict[str, Any]]:
    rows = await asyncio.to_thread(_fetch_stooq_csv, symbol)
    points: list[dict[str, Any]] = []
    first_close: float | None = None
    for row in rows:
        try:
            date = dt.date.fromisoformat(row["Date"])
            close = float(row["Close"])
        except (KeyError, ValueError):
            continue
        if start is not None and date < start:
            continue
        if first_close is None:
            first_close = close
        if first_close <= 0:
            continue
        points.append(
            {
                "date": date,
                "symbol": symbol,
                "close": close,
                "rebased_value": (close / first_close) * base_value,
            }
        )
    return points


async def fetch_latest_quote(symbol: str) -> dict[str, Any] | None:
    rows = await asyncio.to_thread(_fetch_stooq_csv, symbol)
    if not rows:
        return None
    row = rows[-1]
    try:
        return {
            "ticker": symbol.strip(),
            "price_gbp": float(row["Close"]),
            "price_ccy": "GBP",
            "as_of_date": dt.date.fromisoformat(row["Date"]),
            "fetched_at": dt.datetime.now(dt.UTC),
        }
    except (KeyError, ValueError):
        return None


async def refresh_instrument_quote(
    session: AsyncSession,
    instrument: Instrument,
) -> InstrumentQuote | None:
    if not instrument.ticker:
        return None
    payload = await fetch_latest_quote(instrument.ticker)
    if payload is None:
        return None

    existing = (
        await session.execute(
            select(InstrumentQuote).where(InstrumentQuote.instrument_id == instrument.id)
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = InstrumentQuote(instrument_id=instrument.id, ticker=instrument.ticker)
        session.add(existing)

    existing.ticker = payload["ticker"]
    existing.price_gbp = payload["price_gbp"]
    existing.price_ccy = payload["price_ccy"]
    existing.as_of_date = payload["as_of_date"]
    existing.fetched_at = payload["fetched_at"]
    await session.commit()
    await session.refresh(existing)
    return existing


def infer_asset_class(instrument: Instrument) -> str | None:
    text = f"{instrument.security_name} {instrument.identifier}".lower()
    if instrument.is_cash:
        return "Cash"
    if "etf" in text or "ucits" in text or "index" in text:
        return "ETF"
    if "bond" in text or "gilt" in text:
        return "Bond"
    return "Equity"

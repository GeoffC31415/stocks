"""Explicit market-data refresh and read-only coverage endpoints.

Refresh is an operator-triggered, bounded operation (bounded concurrency,
per-symbol timeout, retry/backoff, partial-failure reporting) that never
deletes usable cached rows. Coverage is strictly read-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.database import get_session
from app.models import Instrument
from app.schemas import (
    MarketCoverageInstrument,
    MarketCoverageResponse,
    MarketDataRefreshRequest,
    MarketDataRefreshResponse,
)
from app.services.market_data_coverage import coverage_report
from app.services.market_data_service import (
    DEFAULT_FX_PAIRS,
    fetch_latest_quote,
    refresh_market_data,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/market-data", tags=["market-data"])


async def _open_tickers(session: AsyncSession) -> list[str]:
    rows = (
        (await session.execute(select(Instrument))).scalars().all()
    )
    tickers: list[str] = []
    for inst in rows:
        if inst.is_cash or inst.closed_at or not inst.ticker:
            continue
        ticker = inst.ticker.strip()
        if ticker and ticker not in tickers:
            tickers.append(ticker)
    return tickers


@router.post("/refresh", response_model=MarketDataRefreshResponse)
async def refresh(req: MarketDataRefreshRequest, session: AsyncSession = Depends(get_session)):
    symbols = [s.strip() for s in req.symbols if s.strip()]
    if not symbols:
        symbols = await _open_tickers(session)
    if not symbols:
        raise HTTPException(status_code=400, detail="No symbols to refresh.")

    fx_pairs = [p.strip().upper() for p in req.fx_pairs if p.strip()] or list(DEFAULT_FX_PAIRS)
    start = req.start

    result = await refresh_market_data(
        session,
        symbols,
        fx_pairs=fx_pairs,
        start=start,
        concurrency=req.concurrency,
        timeout=req.timeout_s,
    )
    return MarketDataRefreshResponse(
        ok=result.ok,
        failed=result.failed,
        points_stored=result.points_stored,
        partial=result.partial,
    )


@router.get("/coverage", response_model=MarketCoverageResponse)
async def coverage(session: AsyncSession = Depends(get_session)):
    report = await coverage_report(session)
    gate = report["gate"]
    return MarketCoverageResponse(
        as_of=report["as_of"],
        total_value_gbp=report["total_value_gbp"],
        covered_value_gbp=report["covered_value_gbp"],
        uncovered_value_gbp=report["uncovered_value_gbp"],
        coverage_pct=report["coverage_pct"],
        gate_met=gate["met"],
        gate_threshold_pct=gate["threshold_pct"],
        duplicates=report["duplicates"],
        aligned_dates=report["aligned_dates"],
        fx=report["fx"],
        stale_series=[MarketCoverageInstrument(**entry) for entry in report["stale_series"]],
        instruments=[MarketCoverageInstrument(**entry) for entry in report["instruments"]],
    )


@router.get("/quote/{symbol}")
async def quote(symbol: str) -> dict:
    """Latest provider close in its source currency (not assumed to be GBP)."""
    payload = await fetch_latest_quote(symbol)
    if payload is None:
        raise HTTPException(status_code=404, detail="No quote available for that symbol.")
    payload["fetched_at"] = payload["fetched_at"].isoformat()
    return payload

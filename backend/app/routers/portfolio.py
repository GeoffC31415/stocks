from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas import BenchmarkPoint, InstrumentOut, PortfolioSummary
from app.services.market_data_service import fetch_history
from app.services.portfolio_service import (
    build_instrument_out,
    build_portfolio_summary,
    portfolio_value_timeseries,
)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _to_instrument_out(row: dict) -> InstrumentOut:
    return build_instrument_out(row["instrument"], row["snapshot"])


@router.get("/summary", response_model=PortfolioSummary)
async def summary(session: AsyncSession = Depends(get_session)) -> PortfolioSummary:
    data = await build_portfolio_summary(session)
    return PortfolioSummary(
        as_of_date=data["as_of_date"],
        import_batch_id=data["import_batch_id"],
        total_value_gbp=data["total_value_gbp"],
        total_book_cost_gbp=data["total_book_cost_gbp"],
        total_pnl_gbp=data["total_pnl_gbp"],
        by_account=data["by_account"],
        by_group=data["by_group"],
        allocation=data["allocation"],
        group_allocation=data["group_allocation"],
        worst_pct=[_to_instrument_out(row) for row in data["worst_pct"]],
        best_pct=[_to_instrument_out(row) for row in data["best_pct"]],
    )


@router.get("/timeseries")
async def timeseries(session: AsyncSession = Depends(get_session)) -> list[dict]:
    return await portfolio_value_timeseries(session)


@router.get("/benchmarks", response_model=list[BenchmarkPoint])
async def benchmarks(
    symbols: list[str] = Query(default=["spx.us", "vwrl.uk"]),
    start: dt.date | None = None,
    base_value: float = 100.0,
) -> list[BenchmarkPoint]:
    rows: list[dict] = []
    for symbol in symbols:
        rows.extend(await fetch_history(symbol, start=start, base_value=base_value))
    rows.sort(key=lambda row: (row["date"], row["symbol"]))
    return [BenchmarkPoint(**row) for row in rows]

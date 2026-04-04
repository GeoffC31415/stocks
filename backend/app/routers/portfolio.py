from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas import InstrumentOut, PortfolioSummary
from app.services.portfolio_service import build_portfolio_summary, portfolio_value_timeseries

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _to_instrument_out(row: dict) -> InstrumentOut:
    inst = row["instrument"]
    snap = row["snapshot"]
    return InstrumentOut(
        id=inst.id,
        account_name=inst.account_name,
        identifier=inst.identifier,
        security_name=inst.security_name,
        is_cash=inst.is_cash,
        closed_at=inst.closed_at,
        latest_value_gbp=snap.value_gbp,
        latest_book_cost_gbp=snap.book_cost_gbp,
        latest_pct_change=snap.pct_change,
        pnl_gbp=row["pnl_gbp"],
        group_ids=[],
    )


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
        worst_pct=[_to_instrument_out(row) for row in data["worst_pct"]],
        best_pct=[_to_instrument_out(row) for row in data["best_pct"]],
    )


@router.get("/timeseries")
async def timeseries(session: AsyncSession = Depends(get_session)) -> list[dict]:
    return await portfolio_value_timeseries(session)

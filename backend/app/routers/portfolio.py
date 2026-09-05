from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.routers.analysis_scope import validate_analysis_scope
from app.schemas import (
    AllocationDimension,
    AllocationResponse,
    BenchmarkPoint,
    InstrumentOut,
    PerformanceSummary,
    PortfolioReturnSummary,
    PortfolioSummary,
    RiskAnalysisResponse,
    SnapshotAttributionResponse,
)
from app.services.allocation_service import get_allocation
from app.services.attribution_service import get_snapshot_attribution
from app.services.market_data_service import fetch_history
from app.services.performance_service import (
    build_value_series,
    get_portfolio_performance,
    resolve_period_start,
)
from app.services.portfolio_risk_service import portfolio_risk_analysis
from app.services.portfolio_service import (
    build_instrument_out,
    build_portfolio_summary,
    get_portfolio_return_summary,
    portfolio_value_timeseries,
)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _to_instrument_out(row: dict) -> InstrumentOut:
    return build_instrument_out(
        row["instrument"],
        row["snapshot"],
        snapshot_as_of_date=row.get("snapshot_as_of_date"),
    )


@router.get("/allocation", response_model=AllocationResponse)
async def allocation(
    dimension: AllocationDimension = "asset_class",
    account_name: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> AllocationResponse:
    try:
        data = await get_allocation(session, dimension=dimension, account_name=account_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AllocationResponse(**data)


@router.get("/summary", response_model=PortfolioSummary)
async def summary(account_name: str | None = None, session: AsyncSession = Depends(get_session)) -> PortfolioSummary:
    data = await build_portfolio_summary(session, account_name=account_name)
    return PortfolioSummary(
        scope=data["scope"],
        position_count=data["position_count"],
        invested_value_gbp=data["invested_value_gbp"],
        cash_value_gbp=data["cash_value_gbp"],
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
async def timeseries(
    account_name: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    return await portfolio_value_timeseries(session, account_name=account_name)


@router.get("/returns", response_model=PortfolioReturnSummary, dependencies=[Depends(validate_analysis_scope)])
async def returns(
    account_name: str | None = None,
    from_date: dt.date | None = None,
    to_date: dt.date | None = None,
    period: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> PortfolioReturnSummary:
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(422, "Return start date must not follow end date.")
    if period is not None:
        series, coverage_start = await build_value_series(session, account_name=account_name)
        if series:
            to_date = series[-1]["as_of_date"]
            from_date = resolve_period_start(period, to_date)
            if coverage_start is not None:
                from_date = max(from_date, coverage_start) if from_date else coverage_start
    data = await get_portfolio_return_summary(
        session,
        account_name=account_name,
        from_date=from_date,
        to_date=to_date,
    )
    return PortfolioReturnSummary(**data)


@router.get("/performance", response_model=PerformanceSummary, dependencies=[Depends(validate_analysis_scope)])
async def performance(
    account_name: str | None = None,
    period: str = "ALL",
    risk_free_annual_pct: float = 0.0,
    benchmark: list[str] = Query(default=["spx.us", "vwrl.uk"]),
    include_benchmarks: bool = True,
    session: AsyncSession = Depends(get_session),
) -> PerformanceSummary:
    """Period-scoped growth + risk metrics and a normalized growth curve.

    ``period`` is one of ``1M/3M/6M/1Y/YTD/ALL``. Benchmarks are rebased to
    100 at the window start using cached history only. Unsupported scope
    parameters are rejected rather than silently widening the analysis.
    """
    data = await get_portfolio_performance(
        session,
        account_name=account_name,
        period=period,
        risk_free_annual_pct=risk_free_annual_pct,
        benchmark_symbols=benchmark if include_benchmarks else None,
    )
    return PerformanceSummary(**data)


@router.get("/attribution", response_model=SnapshotAttributionResponse)
async def attribution(
    account_name: str | None = None,
    from_batch_id: int | None = None,
    to_batch_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> SnapshotAttributionResponse:
    data = await get_snapshot_attribution(
        session,
        account_name=account_name,
        from_batch_id=from_batch_id,
        to_batch_id=to_batch_id,
    )
    return SnapshotAttributionResponse(**data)


@router.get("/benchmarks", response_model=list[BenchmarkPoint])
async def benchmarks(
    symbols: list[str] = Query(default=["spx.us", "vwrl.uk"]),
    start: dt.date | None = None,
    base_value: float = 100.0,
    session: AsyncSession = Depends(get_session),
) -> list[BenchmarkPoint]:
    rows: list[dict] = []
    for symbol in symbols:
        rows.extend(await fetch_history(session, symbol, start=start, base_value=base_value))
    rows.sort(key=lambda row: (row["date"], row["symbol"]))
    return [BenchmarkPoint(**row) for row in rows]


@router.get("/risk", response_model=RiskAnalysisResponse)
async def risk(
    account_name: str | None = None,
    benchmark: list[str] = Query(default=["spx.us"]),
    session: AsyncSession = Depends(get_session),
) -> RiskAnalysisResponse:
    """Current-composition risk analysis (volatility, beta, contributions).

    Uses ONLY cached market history and cached FX. Excluded holdings,
    missing FX, stale series and unmet coverage gates are surfaced, never
    hidden. The valuation is anchored to the latest snapshot date in scope.
    """
    return RiskAnalysisResponse(
        **await portfolio_risk_analysis(
            session,
            account_name=account_name,
            benchmark_symbols=benchmark,
        )
    )

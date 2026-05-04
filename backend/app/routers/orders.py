from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Order
from app.schemas import (
    CashflowPoint,
    EstimatedTimeseriesPoint,
    OrderAnalytics,
    OrderImportBatchOut,
    OrderOut,
    PositionSummary,
    UnlinkedOrdersResponse,
)
from app.services.instrument_matcher import link_orders_to_instruments
from app.services.order_service import (
    DuplicateOrderImportError,
    get_cashflow_timeseries,
    get_estimated_portfolio_timeseries,
    get_order_analytics,
    get_order_positions,
    import_hl_orders_csv,
    import_order_history,
)

router = APIRouter(prefix="/api/orders", tags=["orders"])

_DRIP_DEFAULT = 1000.0


@router.post("/import", response_model=OrderImportBatchOut, status_code=status.HTTP_201_CREATED)
async def import_orders(
    file: UploadFile = File(...),
    drip_threshold: float = Form(default=_DRIP_DEFAULT),
    force: bool = Form(default=False),
    session: AsyncSession = Depends(get_session),
) -> OrderImportBatchOut:
    if not file.filename or not file.filename.lower().endswith(".xls"):
        raise HTTPException(status_code=400, detail="Please upload a .xls file.")
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        batch, _ = await import_order_history(
            session,
            file_bytes=payload,
            filename=file.filename,
            drip_threshold_gbp=drip_threshold,
            force=force,
        )
    except DuplicateOrderImportError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"This order history file was already imported (batch {exc.batch_id}).",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Import failed: {exc}") from exc

    return OrderImportBatchOut(
        id=batch.id,
        created_at=batch.created_at,
        filename=batch.filename,
        row_count=batch.row_count,
    )


@router.post("/import/hl", response_model=OrderImportBatchOut, status_code=status.HTTP_201_CREATED)
async def import_hl_orders(
    file: UploadFile = File(...),
    drip_threshold: float = Form(default=_DRIP_DEFAULT),
    force: bool = Form(default=False),
    session: AsyncSession = Depends(get_session),
) -> OrderImportBatchOut:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file.")
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        batch, _ = await import_hl_orders_csv(
            session,
            file_bytes=payload,
            filename=file.filename,
            drip_threshold_gbp=drip_threshold,
            force=force,
        )
    except DuplicateOrderImportError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"This order history file was already imported (batch {exc.batch_id}).",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Import failed: {exc}") from exc

    return OrderImportBatchOut(
        id=batch.id,
        created_at=batch.created_at,
        filename=batch.filename,
        row_count=batch.row_count,
    )


@router.get("/analytics", response_model=OrderAnalytics)
async def order_analytics(
    drip_threshold: float = _DRIP_DEFAULT,
    session: AsyncSession = Depends(get_session),
) -> OrderAnalytics:
    data = await get_order_analytics(session, drip_threshold_gbp=drip_threshold)
    return OrderAnalytics(**data)


@router.get("/cashflow-timeseries", response_model=list[CashflowPoint])
async def cashflow_timeseries(
    drip_threshold: float = _DRIP_DEFAULT,
    session: AsyncSession = Depends(get_session),
) -> list[CashflowPoint]:
    data = await get_cashflow_timeseries(session, drip_threshold_gbp=drip_threshold)
    return [CashflowPoint(**row) for row in data]


@router.get("/positions", response_model=list[PositionSummary])
async def order_positions(
    drip_threshold: float = _DRIP_DEFAULT,
    session: AsyncSession = Depends(get_session),
) -> list[PositionSummary]:
    data = await get_order_positions(session, drip_threshold_gbp=drip_threshold)
    return [PositionSummary(**row) for row in data]


@router.get("/estimated-timeseries", response_model=list[EstimatedTimeseriesPoint])
async def estimated_timeseries(
    session: AsyncSession = Depends(get_session),
) -> list[EstimatedTimeseriesPoint]:
    data = await get_estimated_portfolio_timeseries(session)
    return [EstimatedTimeseriesPoint(**row) for row in data]


@router.post("/backfill-instruments")
async def backfill_instruments(
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    """Re-run instrument matching on all unlinked orders."""
    linked = await link_orders_to_instruments(session)
    await session.commit()
    return {"orders_linked": linked}


@router.get("/unlinked", response_model=UnlinkedOrdersResponse)
async def list_unlinked_orders(
    drip_threshold: float = _DRIP_DEFAULT,
    limit: int = 200,
    session: AsyncSession = Depends(get_session),
) -> UnlinkedOrdersResponse:
    """Orders that the matcher could not associate with an instrument.

    These would otherwise be silently absent from per-position analytics.
    """
    count_result = await session.execute(
        select(func.count()).select_from(Order).where(Order.instrument_id.is_(None))
    )
    count = int(count_result.scalar_one() or 0)

    rows_result = await session.execute(
        select(Order)
        .where(Order.instrument_id.is_(None))
        .order_by(Order.order_date.desc())
        .limit(limit)
    )
    orders = [
        OrderOut(
            id=o.id,
            security_name=o.security_name,
            instrument_id=o.instrument_id,
            order_date=o.order_date,
            order_status=o.order_status,
            account_name=o.account_name,
            side=o.side,
            quantity=o.quantity,
            cost_proceeds_gbp=o.cost_proceeds_gbp,
            country=o.country,
            is_drip=(
                o.side.lower() == "buy"
                and o.cost_proceeds_gbp is not None
                and o.cost_proceeds_gbp < drip_threshold
            ),
        )
        for o in rows_result.scalars().all()
    ]
    return UnlinkedOrdersResponse(count=count, orders=orders)


@router.get("", response_model=list[OrderOut])
async def list_orders(
    side: str | None = None,
    is_drip: bool | None = None,
    drip_threshold: float = _DRIP_DEFAULT,
    limit: int = 200,
    session: AsyncSession = Depends(get_session),
) -> list[OrderOut]:
    q = select(Order).order_by(Order.order_date.desc()).limit(limit)
    result = await session.execute(q)
    orders = list(result.scalars().all())

    out: list[OrderOut] = []
    for o in orders:
        computed_drip = (
            o.side.lower() == "buy"
            and o.cost_proceeds_gbp is not None
            and o.cost_proceeds_gbp < drip_threshold
        )
        if side is not None and o.side.lower() != side.lower():
            continue
        if is_drip is not None and computed_drip != is_drip:
            continue
        out.append(
            OrderOut(
                id=o.id,
                security_name=o.security_name,
                instrument_id=o.instrument_id,
                order_date=o.order_date,
                order_status=o.order_status,
                account_name=o.account_name,
                side=o.side,
                quantity=o.quantity,
                cost_proceeds_gbp=o.cost_proceeds_gbp,
                country=o.country,
                is_drip=computed_drip,
            )
        )

    return out

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.models import HoldingSnapshot, ImportBatch, Instrument, InstrumentGroupMember, InstrumentQuote
from app.schemas import InstrumentHistoryPoint, InstrumentMarketPatch, InstrumentOut, InstrumentQuoteOut, OrderOut
from app.services.market_data_service import infer_asset_class, refresh_instrument_quote
from app.services.order_service import get_orders_for_instrument
from app.services.portfolio_service import (
    build_instrument_out,
    get_latest_batch,
    get_previous_batch,
    instrument_history,
    snapshot_metrics,
)

router = APIRouter(prefix="/api/instruments", tags=["instruments"])


@router.get("", response_model=list[InstrumentOut])
async def list_instruments(session: AsyncSession = Depends(get_session)) -> list[InstrumentOut]:
    batch = await get_latest_batch(session)
    if batch is None:
        return []

    snap_result = await session.execute(
        select(HoldingSnapshot)
        .where(HoldingSnapshot.import_batch_id == batch.id)
        .options(selectinload(HoldingSnapshot.instrument))
        .order_by(HoldingSnapshot.value_gbp.desc().nullslast())
    )
    snapshots = snap_result.scalars().all()

    membership_result = await session.execute(select(InstrumentGroupMember))
    memberships = membership_result.scalars().all()
    by_instrument: dict[int, list[int]] = {}
    for member in memberships:
        by_instrument.setdefault(member.instrument_id, []).append(member.group_id)

    quote_result = await session.execute(select(InstrumentQuote))
    quotes = {quote.instrument_id: quote for quote in quote_result.scalars().all()}

    prev_batch = await get_previous_batch(session, before_batch_id=batch.id)
    prev_snapshots: dict[int, HoldingSnapshot] = {}
    if prev_batch is not None:
        prev_result = await session.execute(
            select(HoldingSnapshot).where(HoldingSnapshot.import_batch_id == prev_batch.id)
        )
        prev_snapshots = {s.instrument_id: s for s in prev_result.scalars().all()}

    instrument_ids = [snap.instrument_id for snap in snapshots]
    metrics_by_instrument: dict[int, dict[str, float | int | None]] = {}
    if instrument_ids:
        history_result = await session.execute(
            select(HoldingSnapshot)
            .join(ImportBatch, HoldingSnapshot.import_batch_id == ImportBatch.id)
            .where(HoldingSnapshot.instrument_id.in_(instrument_ids))
            .order_by(HoldingSnapshot.instrument_id, ImportBatch.as_of_date, ImportBatch.id)
        )
        history_by_instrument: dict[int, list[HoldingSnapshot]] = {}
        for history_snapshot in history_result.scalars().all():
            history_by_instrument.setdefault(history_snapshot.instrument_id, []).append(
                history_snapshot
            )
        metrics_by_instrument = snapshot_metrics(history_by_instrument)

    return [
        build_instrument_out(
            snap.instrument,
            snap,
            quote=quotes.get(snap.instrument_id),
            group_ids=by_instrument.get(snap.instrument_id, []),
            previous_snapshot=prev_snapshots.get(snap.instrument_id),
            metrics=metrics_by_instrument.get(snap.instrument_id),
        )
        for snap in snapshots
    ]


@router.get("/{instrument_id}/history", response_model=list[InstrumentHistoryPoint])
async def get_instrument_history(
    instrument_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[InstrumentHistoryPoint]:
    existing = await session.get(Instrument, instrument_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Instrument not found.")
    rows = await instrument_history(session, instrument_id)
    return [InstrumentHistoryPoint.model_validate(row) for row in rows]


@router.get("/{instrument_id}/orders", response_model=list[OrderOut])
async def get_instrument_orders(
    instrument_id: int,
    drip_threshold: float = 1000.0,
    session: AsyncSession = Depends(get_session),
) -> list[OrderOut]:
    existing = await session.get(Instrument, instrument_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Instrument not found.")
    orders = await get_orders_for_instrument(session, instrument_id)
    return [
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
        for o in orders
    ]


@router.patch("/{instrument_id}/market", response_model=InstrumentOut)
async def update_instrument_market(
    instrument_id: int,
    body: InstrumentMarketPatch,
    session: AsyncSession = Depends(get_session),
) -> InstrumentOut:
    inst = await session.get(Instrument, instrument_id)
    if inst is None:
        raise HTTPException(status_code=404, detail="Instrument not found.")

    if "ticker" in body.model_fields_set:
        inst.ticker = body.ticker.strip() if body.ticker else None
    if "sector" in body.model_fields_set:
        inst.sector = body.sector.strip() if body.sector else None
    if "region" in body.model_fields_set:
        inst.region = body.region.strip() if body.region else None
    if "asset_class" in body.model_fields_set:
        inst.asset_class = body.asset_class.strip() if body.asset_class else None
    if inst.asset_class is None:
        inst.asset_class = infer_asset_class(inst)

    await session.commit()
    await session.refresh(inst)
    return build_instrument_out(inst, snapshot=None)


@router.post("/{instrument_id}/quote", response_model=InstrumentQuoteOut)
async def refresh_quote(
    instrument_id: int,
    session: AsyncSession = Depends(get_session),
) -> InstrumentQuoteOut:
    inst = await session.get(Instrument, instrument_id)
    if inst is None:
        raise HTTPException(status_code=404, detail="Instrument not found.")
    quote = await refresh_instrument_quote(session, inst)
    if quote is None:
        raise HTTPException(status_code=400, detail="Set a Stooq-compatible ticker first.")
    return InstrumentQuoteOut(
        instrument_id=quote.instrument_id,
        ticker=quote.ticker,
        price_gbp=quote.price_gbp,
        price_ccy=quote.price_ccy,
        as_of_date=quote.as_of_date,
        fetched_at=quote.fetched_at,
    )

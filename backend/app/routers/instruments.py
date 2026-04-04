from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.models import HoldingSnapshot, Instrument, InstrumentGroupMember
from app.schemas import InstrumentHistoryPoint, InstrumentOut
from app.services.portfolio_service import get_latest_batch, instrument_history

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

    out: list[InstrumentOut] = []
    for snap in snapshots:
        inst = snap.instrument
        pnl = None
        if snap.value_gbp is not None and snap.book_cost_gbp is not None:
            pnl = snap.value_gbp - snap.book_cost_gbp
        out.append(
            InstrumentOut(
                id=inst.id,
                account_name=inst.account_name,
                identifier=inst.identifier,
                security_name=inst.security_name,
                is_cash=inst.is_cash,
                closed_at=inst.closed_at,
                latest_value_gbp=snap.value_gbp,
                latest_book_cost_gbp=snap.book_cost_gbp,
                latest_pct_change=snap.pct_change,
                pnl_gbp=pnl,
                group_ids=sorted(by_instrument.get(inst.id, [])),
            )
        )
    return out


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

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.models import HoldingSnapshot, Instrument, InstrumentGroup, InstrumentGroupMember
from app.schemas import GroupMembersBody, InstrumentGroupCreate, InstrumentGroupOut, InstrumentGroupPatch
from app.services.portfolio_service import get_latest_batch

router = APIRouter(prefix="/api/groups", tags=["groups"])


async def _group_totals(session: AsyncSession) -> dict[int, float]:
    batch = await get_latest_batch(session)
    if batch is None:
        return {}
    snaps_result = await session.execute(
        select(HoldingSnapshot).where(HoldingSnapshot.import_batch_id == batch.id)
    )
    by_instrument = {s.instrument_id: (s.value_gbp or 0.0) for s in snaps_result.scalars().all()}
    members_result = await session.execute(select(InstrumentGroupMember))
    totals: dict[int, float] = {}
    for member in members_result.scalars().all():
        totals[member.group_id] = totals.get(member.group_id, 0.0) + by_instrument.get(
            member.instrument_id,
            0.0,
        )
    return totals


@router.get("", response_model=list[InstrumentGroupOut])
async def list_groups(session: AsyncSession = Depends(get_session)) -> list[InstrumentGroupOut]:
    result = await session.execute(
        select(InstrumentGroup).options(selectinload(InstrumentGroup.members)).order_by(InstrumentGroup.name)
    )
    groups = result.scalars().unique().all()
    totals = await _group_totals(session)
    return [
        InstrumentGroupOut(
            id=g.id,
            name=g.name,
            color=g.color,
            member_count=len(g.members),
            total_value_gbp=totals.get(g.id, 0.0),
        )
        for g in groups
    ]


@router.post("", response_model=InstrumentGroupOut, status_code=status.HTTP_201_CREATED)
async def create_group(
    body: InstrumentGroupCreate,
    session: AsyncSession = Depends(get_session),
) -> InstrumentGroupOut:
    existing = (
        await session.execute(select(InstrumentGroup).where(InstrumentGroup.name == body.name.strip()))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Group name already exists.")
    group = InstrumentGroup(name=body.name.strip(), color=body.color)
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return InstrumentGroupOut(
        id=group.id,
        name=group.name,
        color=group.color,
        member_count=0,
        total_value_gbp=0.0,
    )


@router.patch("/{group_id}", response_model=InstrumentGroupOut)
async def patch_group(
    group_id: int,
    body: InstrumentGroupPatch,
    session: AsyncSession = Depends(get_session),
) -> InstrumentGroupOut:
    group = await session.get(InstrumentGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found.")
    if body.name is not None:
        new_name = body.name.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="Group name cannot be empty.")
        group.name = new_name
    if body.color is not None:
        group.color = body.color
    await session.commit()
    await session.refresh(group)
    totals = await _group_totals(session)
    member_count = (
        await session.execute(select(InstrumentGroupMember).where(InstrumentGroupMember.group_id == group.id))
    ).scalars().all()
    return InstrumentGroupOut(
        id=group.id,
        name=group.name,
        color=group.color,
        member_count=len(member_count),
        total_value_gbp=totals.get(group.id, 0.0),
    )


@router.put("/{group_id}/members", response_model=InstrumentGroupOut)
async def replace_group_members(
    group_id: int,
    body: GroupMembersBody,
    session: AsyncSession = Depends(get_session),
) -> InstrumentGroupOut:
    group = await session.get(InstrumentGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found.")

    instrument_ids = sorted(set(body.instrument_ids))
    if instrument_ids:
        result = await session.execute(select(Instrument.id).where(Instrument.id.in_(instrument_ids)))
        existing = set(result.scalars().all())
        missing = [instrument_id for instrument_id in instrument_ids if instrument_id not in existing]
        if missing:
            raise HTTPException(status_code=400, detail=f"Unknown instrument ids: {missing}")

    existing_members_result = await session.execute(
        select(InstrumentGroupMember).where(InstrumentGroupMember.group_id == group_id)
    )
    for member in existing_members_result.scalars().all():
        await session.delete(member)
    for instrument_id in instrument_ids:
        session.add(InstrumentGroupMember(group_id=group_id, instrument_id=instrument_id))

    await session.commit()
    totals = await _group_totals(session)
    return InstrumentGroupOut(
        id=group.id,
        name=group.name,
        color=group.color,
        member_count=len(instrument_ids),
        total_value_gbp=totals.get(group.id, 0.0),
    )

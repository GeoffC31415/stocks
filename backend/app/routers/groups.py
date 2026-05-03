from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.models import HoldingSnapshot, Instrument, InstrumentGroup, InstrumentGroupMember
from app.schemas import (
    GroupMembersBody,
    GroupPerformance,
    InstrumentGroupCreate,
    InstrumentGroupOut,
    InstrumentGroupPatch,
)
from app.services.order_service import get_group_performance
from app.services.portfolio_service import get_latest_batch

router = APIRouter(prefix="/api/groups", tags=["groups"])

_DRIP_DEFAULT = 1000.0


async def _all_group_totals(session: AsyncSession) -> dict[int, float]:
    """Sum of latest-snapshot value per group, in a single grouped query."""
    batch = await get_latest_batch(session)
    if batch is None:
        return {}
    r = await session.execute(
        select(
            InstrumentGroupMember.group_id,
            func.coalesce(func.sum(HoldingSnapshot.value_gbp), 0.0),
        )
        .select_from(InstrumentGroupMember)
        .outerjoin(
            HoldingSnapshot,
            (HoldingSnapshot.instrument_id == InstrumentGroupMember.instrument_id)
            & (HoldingSnapshot.import_batch_id == batch.id),
        )
        .group_by(InstrumentGroupMember.group_id)
    )
    return {group_id: float(total or 0.0) for group_id, total in r.all()}


async def _single_group_summary(
    session: AsyncSession, group_id: int
) -> tuple[int, float]:
    """Member count and current total value for a single group."""
    member_count = (
        await session.execute(
            select(func.count())
            .select_from(InstrumentGroupMember)
            .where(InstrumentGroupMember.group_id == group_id)
        )
    ).scalar_one() or 0

    batch = await get_latest_batch(session)
    if batch is None:
        return int(member_count), 0.0

    total = (
        await session.execute(
            select(func.coalesce(func.sum(HoldingSnapshot.value_gbp), 0.0))
            .select_from(InstrumentGroupMember)
            .join(
                HoldingSnapshot,
                (HoldingSnapshot.instrument_id == InstrumentGroupMember.instrument_id)
                & (HoldingSnapshot.import_batch_id == batch.id),
            )
            .where(InstrumentGroupMember.group_id == group_id)
        )
    ).scalar_one()
    return int(member_count), float(total or 0.0)


@router.get("/performance", response_model=list[GroupPerformance])
async def group_performance(
    drip_threshold: float = _DRIP_DEFAULT,
    session: AsyncSession = Depends(get_session),
) -> list[GroupPerformance]:
    data = await get_group_performance(session, drip_threshold_gbp=drip_threshold)
    return [GroupPerformance(**row) for row in data]


@router.get("", response_model=list[InstrumentGroupOut])
async def list_groups(session: AsyncSession = Depends(get_session)) -> list[InstrumentGroupOut]:
    result = await session.execute(
        select(InstrumentGroup).options(selectinload(InstrumentGroup.members)).order_by(InstrumentGroup.name)
    )
    groups = result.scalars().unique().all()
    totals = await _all_group_totals(session)
    return [
        InstrumentGroupOut(
            id=g.id,
            name=g.name,
            color=g.color,
            target_allocation_pct=g.target_allocation_pct,
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
    group = InstrumentGroup(
        name=body.name.strip(),
        color=body.color,
        target_allocation_pct=body.target_allocation_pct,
    )
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return InstrumentGroupOut(
        id=group.id,
        name=group.name,
        color=group.color,
        target_allocation_pct=group.target_allocation_pct,
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
    if "target_allocation_pct" in body.model_fields_set:
        group.target_allocation_pct = body.target_allocation_pct
    await session.commit()
    await session.refresh(group)
    member_count, total_value = await _single_group_summary(session, group.id)
    return InstrumentGroupOut(
        id=group.id,
        name=group.name,
        color=group.color,
        target_allocation_pct=group.target_allocation_pct,
        member_count=member_count,
        total_value_gbp=total_value,
    )


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    group = await session.get(InstrumentGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found.")
    await session.delete(group)
    await session.commit()


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
    _, total_value = await _single_group_summary(session, group.id)
    return InstrumentGroupOut(
        id=group.id,
        name=group.name,
        color=group.color,
        target_allocation_pct=group.target_allocation_pct,
        member_count=len(instrument_ids),
        total_value_gbp=total_value,
    )

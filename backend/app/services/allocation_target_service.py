"""Read-only group targets; existing groups remain descriptive tags."""

import math
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.allocation_target_schemas import AllocationTargets, TargetGroup
from app.models import InstrumentGroup
from app.services.portfolio_service import get_current_snapshots


async def get_allocation_targets(
    session: AsyncSession,
    *,
    account_name: str | None = None,
    tolerance_pp: float = 2,
) -> AllocationTargets:
    snapshots = [
        s
        for s in await get_current_snapshots(session)
        if account_name is None or s.instrument.account_name == account_name
    ]
    values = {
        s.instrument_id: s.value_gbp
        for s in snapshots
        if not s.instrument.is_cash
        and s.value_gbp is not None
        and math.isfinite(s.value_gbp)
        and s.value_gbp > 0
    }
    total = sum(values.values())
    cash_values = [s.value_gbp for s in snapshots if s.instrument.is_cash]
    cash = None if any(v is None or not math.isfinite(v) for v in cash_values) else sum(v for v in cash_values if v is not None)
    if cash is not None and not math.isfinite(cash):
        cash = None
    groups = (
        await session.scalars(
            select(InstrumentGroup)
            .options(selectinload(InstrumentGroup.members))
            .order_by(InstrumentGroup.id)
        )
    ).all()
    reasons = []
    if cash is None:
        reasons.append("Cash valuation is missing or non-finite; real cash cannot be stated reliably.")
    if any(
        s.value_gbp is None or not math.isfinite(s.value_gbp) or s.value_gbp < 0
        for s in snapshots
        if not s.instrument.is_cash
    ):
        reasons.append(
            "Missing, negative or non-finite investment values prevent a complete target comparison."
        )
    if not total:
        reasons.append("No positive invested value in this account scope.")
    if not groups or any(g.target_allocation_pct is None for g in groups):
        reasons.append("Set a target for every group; existing groups remain descriptive tags.")
    targets = [g.target_allocation_pct for g in groups if g.target_allocation_pct is not None]
    valid_targets = all(math.isfinite(t) and 0 <= t <= 100 for t in targets)
    if not valid_targets or abs(sum(targets) - 100) > 0.01 + 1e-10:
        reasons.append(
            "Targets must be finite, between 0 and 100, and sum to 100% within 0.01 percentage points."
        )
    membership = Counter(
        m.instrument_id for g in groups for m in g.members if m.instrument_id in values
    )
    if any(membership[i] > 1 for i in values):
        reasons.append(
            "Overlapping groups are descriptive tags, not an exclusive target set. Resolve memberships in Groups."
        )
    if any(membership[i] == 0 for i in values):
        reasons.append(
            "Some invested holdings are unassigned. Assign each to exactly one target group."
        )
    rows = []
    for group in groups:
        members = sorted(m.instrument_id for m in group.members if m.instrument_id in values)
        value = sum(values[i] for i in members)
        weight = value / total * 100 if total else None
        target = group.target_allocation_pct
        if target is not None and not math.isfinite(target):
            target = None
        rows.append(
            TargetGroup(
                group_id=group.id,
                name=group.name,
                instrument_ids=members,
                actual_value_gbp=value,
                actual_weight_pct=weight,
                target_weight_pct=target,
                drift_pp=weight - target if weight is not None and target is not None else None,
                gap_gbp=total * target / 100 - value if target is not None else None,
                within_tolerance=abs(weight - target) <= tolerance_pp
                if weight is not None and target is not None
                else None,
            )
        )
    if reasons:
        for row in rows:
            row.drift_pp = row.gap_gbp = row.within_tolerance = None
    return AllocationTargets(
        status="unavailable" if reasons else "available",
        account_name=account_name,
        invested_value_gbp=total,
        excluded_cash_gbp=cash,
        tolerance_pp=tolerance_pp,
        reasons=reasons,
        groups=rows,
    )

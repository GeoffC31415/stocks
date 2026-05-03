from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    HoldingSnapshot,
    ImportBatch,
    Instrument,
    InstrumentGroup,
    Order,
)


async def get_latest_batch(session: AsyncSession) -> ImportBatch | None:
    r = await session.execute(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(1))
    return r.scalar_one_or_none()


async def snapshots_for_batch_with_instruments(
    session: AsyncSession,
    batch_id: int,
) -> Sequence[HoldingSnapshot]:
    r = await session.execute(
        select(HoldingSnapshot)
        .where(HoldingSnapshot.import_batch_id == batch_id)
        .options(selectinload(HoldingSnapshot.instrument))
    )
    return r.scalars().all()


def _pnl_row(value_gbp: float | None, book_gbp: float | None) -> float | None:
    if value_gbp is None or book_gbp is None:
        return None
    return value_gbp - book_gbp


async def build_portfolio_summary(session: AsyncSession) -> dict:
    batch = await get_latest_batch(session)
    if batch is None:
        return {
            "as_of_date": None,
            "import_batch_id": None,
            "total_value_gbp": 0.0,
            "total_book_cost_gbp": 0.0,
            "total_pnl_gbp": 0.0,
            "by_account": {},
            "by_group": {},
            "allocation": [],
            "group_allocation": [],
            "worst_pct": [],
            "best_pct": [],
            "instruments": [],
        }

    snaps = await snapshots_for_batch_with_instruments(session, batch.id)
    total_value = 0.0
    total_book = 0.0
    by_account: dict[str, float] = defaultdict(float)

    instrument_rows: list[dict] = []
    for s in snaps:
        inst = s.instrument
        v = s.value_gbp or 0.0
        total_value += v
        by_account[inst.account_name] += v
        bc = s.book_cost_gbp
        if bc is not None and not inst.is_cash:
            total_book += bc
        pnl = _pnl_row(s.value_gbp, s.book_cost_gbp)
        instrument_rows.append(
            {
                "instrument": inst,
                "snapshot": s,
                "pnl_gbp": pnl,
            }
        )

    # total_pnl: for display use sum of per-line pnl where book exists + cash has no book
    line_pnl = 0.0
    for row in instrument_rows:
        if row["pnl_gbp"] is not None:
            line_pnl += row["pnl_gbp"]
        elif row["instrument"].is_cash:
            pass
    total_pnl_gbp = line_pnl

    r_groups = await session.execute(
        select(InstrumentGroup).options(selectinload(InstrumentGroup.members))
    )
    groups = r_groups.scalars().unique().all()
    by_group: dict[str, float] = {}
    inst_to_value = {row["instrument"].id: row["snapshot"].value_gbp or 0.0 for row in instrument_rows}
    group_allocation: list[dict] = []
    for g in groups:
        total_g = 0.0
        for m in g.members:
            total_g += inst_to_value.get(m.instrument_id, 0.0)
        by_group[g.name] = total_g
        weight_pct = (total_g / total_value * 100.0) if total_value > 0 else 0.0
        group_allocation.append(
            {
                "label": g.name,
                "kind": "group",
                "value_gbp": round(total_g, 2),
                "weight_pct": round(weight_pct, 2),
                "target_pct": g.target_allocation_pct,
                "drift_pct": (
                    round(weight_pct - g.target_allocation_pct, 2)
                    if g.target_allocation_pct is not None
                    else None
                ),
                "is_concentration_risk": False,
            }
        )

    non_cash = [r for r in instrument_rows if not r["instrument"].is_cash]
    non_cash_total = sum(row["snapshot"].value_gbp or 0.0 for row in non_cash)
    allocation = [
        {
            "label": row["instrument"].security_name,
            "kind": "holding",
            "value_gbp": round(row["snapshot"].value_gbp or 0.0, 2),
            "weight_pct": round(
                ((row["snapshot"].value_gbp or 0.0) / non_cash_total) * 100.0,
                2,
            )
            if non_cash_total > 0
            else 0.0,
            "target_pct": None,
            "drift_pct": None,
            "is_concentration_risk": (
                non_cash_total > 0
                and ((row["snapshot"].value_gbp or 0.0) / non_cash_total) * 100.0 > 20.0
            ),
        }
        for row in sorted(
            non_cash,
            key=lambda item: item["snapshot"].value_gbp or 0.0,
            reverse=True,
        )
    ]
    with_pct = [r for r in non_cash if r["snapshot"].pct_change is not None]
    worst = sorted(with_pct, key=lambda x: x["snapshot"].pct_change or 0.0)[:8]
    best = sorted(with_pct, key=lambda x: x["snapshot"].pct_change or 0.0, reverse=True)[:8]

    return {
        "as_of_date": batch.as_of_date,
        "import_batch_id": batch.id,
        "total_value_gbp": total_value,
        "total_book_cost_gbp": total_book,
        "total_pnl_gbp": total_pnl_gbp,
        "by_account": dict(by_account),
        "by_group": by_group,
        "allocation": allocation,
        "group_allocation": group_allocation,
        "worst_pct": worst,
        "best_pct": best,
        "instruments": instrument_rows,
    }


async def instrument_history(
    session: AsyncSession,
    instrument_id: int,
) -> list[dict]:
    orders_result = await session.execute(
        select(Order)
        .where(Order.instrument_id == instrument_id)
        .order_by(Order.order_date)
    )
    orders = list(orders_result.scalars().all())
    discretionary_basis_by_date: dict[object, float] = {}
    running_basis = 0.0
    order_index = 0

    r = await session.execute(
        select(HoldingSnapshot, ImportBatch)
        .join(ImportBatch, HoldingSnapshot.import_batch_id == ImportBatch.id)
        .where(HoldingSnapshot.instrument_id == instrument_id)
        .order_by(ImportBatch.as_of_date, ImportBatch.id)
    )
    out: list[dict] = []
    for snap, batch in r.all():
        while order_index < len(orders) and orders[order_index].order_date.date() <= batch.as_of_date:
            order = orders[order_index]
            cost = order.cost_proceeds_gbp or 0.0
            if order.side.lower() == "buy" and not order.is_drip:
                running_basis += cost
            elif order.side.lower() == "sell":
                running_basis -= cost
            order_index += 1
        discretionary_basis_by_date[batch.as_of_date] = running_basis
        out.append(
            {
                "as_of_date": batch.as_of_date,
                "value_gbp": snap.value_gbp,
                "book_cost_gbp": snap.book_cost_gbp,
                "discretionary_cost_basis_gbp": discretionary_basis_by_date[batch.as_of_date],
                "quantity": snap.quantity,
                "pct_change": snap.pct_change,
            }
        )
    return out


async def portfolio_value_timeseries(session: AsyncSession) -> list[dict]:
    r = await session.execute(
        select(ImportBatch.id, ImportBatch.as_of_date).order_by(ImportBatch.as_of_date, ImportBatch.id)
    )
    batches = r.all()
    series: list[dict] = []
    for bid, as_of in batches:
        snaps = await snapshots_for_batch_with_instruments(session, bid)
        total_v = sum(s.value_gbp or 0.0 for s in snaps)
        total_b = sum(
            s.book_cost_gbp or 0.0 for s in snaps if not s.instrument.is_cash and s.book_cost_gbp
        )
        series.append(
            {
                "as_of_date": as_of.isoformat(),
                "total_value_gbp": total_v,
                "total_book_cost_gbp": total_b,
            }
        )
    return series

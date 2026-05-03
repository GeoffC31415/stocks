from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    HoldingSnapshot,
    ImportBatch,
    Instrument,
    InstrumentGroup,
    InstrumentQuote,
    Order,
)
from app.schemas import InstrumentOut


async def get_latest_batch(session: AsyncSession) -> ImportBatch | None:
    r = await session.execute(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(1))
    return r.scalar_one_or_none()


async def get_previous_batch(
    session: AsyncSession, *, before_batch_id: int
) -> ImportBatch | None:
    r = await session.execute(
        select(ImportBatch)
        .where(ImportBatch.id < before_batch_id)
        .order_by(ImportBatch.id.desc())
        .limit(1)
    )
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


def compute_pnl_gbp(value_gbp: float | None, book_cost_gbp: float | None) -> float | None:
    """Single source of truth for unrealised P&L per holding."""
    if value_gbp is None or book_cost_gbp is None:
        return None
    return value_gbp - book_cost_gbp


def _delta(after: float | None, before: float | None) -> float | None:
    if after is None or before is None:
        return None
    return after - before


def build_instrument_out(
    instrument: Instrument,
    snapshot: HoldingSnapshot | None,
    *,
    quote: InstrumentQuote | None = None,
    group_ids: Sequence[int] | None = None,
    trailing_drip_yield_pct: float | None = None,
    previous_snapshot: HoldingSnapshot | None = None,
) -> InstrumentOut:
    """Build a single InstrumentOut from its model parts.

    Centralises field mapping so financial fields like ``pnl_gbp`` and
    snapshot-vs-previous-snapshot deltas have one definition.
    """
    value_gbp = snapshot.value_gbp if snapshot is not None else None
    book_cost_gbp = snapshot.book_cost_gbp if snapshot is not None else None
    pct_change = snapshot.pct_change if snapshot is not None else None
    quantity = snapshot.quantity if snapshot is not None else None
    prev_value = previous_snapshot.value_gbp if previous_snapshot is not None else None
    prev_quantity = previous_snapshot.quantity if previous_snapshot is not None else None

    return InstrumentOut(
        id=instrument.id,
        account_name=instrument.account_name,
        identifier=instrument.identifier,
        security_name=instrument.security_name,
        is_cash=instrument.is_cash,
        ticker=instrument.ticker,
        sector=instrument.sector,
        region=instrument.region,
        asset_class=instrument.asset_class,
        closed_at=instrument.closed_at,
        latest_value_gbp=value_gbp,
        latest_book_cost_gbp=book_cost_gbp,
        latest_pct_change=pct_change,
        pnl_gbp=compute_pnl_gbp(value_gbp, book_cost_gbp),
        latest_quote_price_gbp=quote.price_gbp if quote is not None else None,
        latest_quote_as_of_date=quote.as_of_date if quote is not None else None,
        latest_quote_fetched_at=quote.fetched_at if quote is not None else None,
        trailing_drip_yield_pct=trailing_drip_yield_pct,
        delta_value_gbp_since_prev_snapshot=_delta(value_gbp, prev_value),
        delta_quantity_since_prev_snapshot=_delta(quantity, prev_quantity),
        group_ids=sorted(group_ids) if group_ids else [],
    )


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
        pnl = compute_pnl_gbp(s.value_gbp, s.book_cost_gbp)
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
    """Aggregate value and (non-cash) book cost per import batch in a single query."""
    book_cost_expr = case(
        (Instrument.is_cash.is_(False), HoldingSnapshot.book_cost_gbp),
        else_=0.0,
    )
    r = await session.execute(
        select(
            ImportBatch.as_of_date,
            func.coalesce(func.sum(HoldingSnapshot.value_gbp), 0.0).label("total_value"),
            func.coalesce(func.sum(book_cost_expr), 0.0).label("total_book"),
        )
        .select_from(ImportBatch)
        .outerjoin(HoldingSnapshot, HoldingSnapshot.import_batch_id == ImportBatch.id)
        .outerjoin(Instrument, Instrument.id == HoldingSnapshot.instrument_id)
        .group_by(ImportBatch.id, ImportBatch.as_of_date)
        .order_by(ImportBatch.as_of_date, ImportBatch.id)
    )
    return [
        {
            "as_of_date": as_of.isoformat(),
            "total_value_gbp": float(total_value or 0.0),
            "total_book_cost_gbp": float(total_book or 0.0),
        }
        for as_of, total_value, total_book in r.all()
    ]

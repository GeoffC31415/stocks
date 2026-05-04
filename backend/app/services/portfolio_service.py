from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import func, select
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


async def get_latest_batch_for_account(
    session: AsyncSession,
    account_name: str,
) -> ImportBatch | None:
    r = await session.execute(
        select(ImportBatch)
        .join(HoldingSnapshot, HoldingSnapshot.import_batch_id == ImportBatch.id)
        .join(Instrument, Instrument.id == HoldingSnapshot.instrument_id)
        .where(Instrument.account_name == account_name)
        .order_by(ImportBatch.id.desc())
        .limit(1)
    )
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


async def get_current_snapshots(session: AsyncSession) -> Sequence[HoldingSnapshot]:
    """Latest non-closed snapshot per instrument, across all account-specific batches."""
    latest_by_instrument = (
        select(
            HoldingSnapshot.instrument_id,
            func.max(HoldingSnapshot.import_batch_id).label("latest_batch_id"),
        )
        .group_by(HoldingSnapshot.instrument_id)
        .subquery()
    )
    r = await session.execute(
        select(HoldingSnapshot)
        .join(
            latest_by_instrument,
            (HoldingSnapshot.instrument_id == latest_by_instrument.c.instrument_id)
            & (HoldingSnapshot.import_batch_id == latest_by_instrument.c.latest_batch_id),
        )
        .join(Instrument, Instrument.id == HoldingSnapshot.instrument_id)
        .where(Instrument.closed_at.is_(None))
        .options(selectinload(HoldingSnapshot.instrument))
        .order_by(HoldingSnapshot.value_gbp.desc().nullslast())
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


def _drawdown_from_peak(current: float | None, peak: float | None) -> float | None:
    if current is None or peak is None or peak <= 0:
        return None
    return ((current - peak) / peak) * 100.0


def _quantity_unchanged_snapshot_count(snapshots: Sequence[HoldingSnapshot]) -> int | None:
    latest = snapshots[-1] if snapshots else None
    if latest is None or latest.quantity is None:
        return None

    count = 0
    for snapshot in reversed(snapshots):
        if snapshot.quantity != latest.quantity:
            break
        count += 1
    return count


def snapshot_metrics(
    snapshots_by_instrument: dict[int, Sequence[HoldingSnapshot]],
) -> dict[int, dict[str, float | int | None]]:
    """Peak and quantity-stability metrics derived from an instrument's snapshot history."""
    metrics: dict[int, dict[str, float | int | None]] = {}
    for instrument_id, snapshots in snapshots_by_instrument.items():
        peak_value = max(
            (snapshot.value_gbp for snapshot in snapshots if snapshot.value_gbp is not None),
            default=None,
        )
        peak_price = max(
            (snapshot.last_price for snapshot in snapshots if snapshot.last_price is not None),
            default=None,
        )
        latest = snapshots[-1] if snapshots else None
        current_price = latest.last_price if latest is not None else None
        current_value = latest.value_gbp if latest is not None else None
        drawdown = _drawdown_from_peak(current_price, peak_price)
        if drawdown is None:
            drawdown = _drawdown_from_peak(current_value, peak_value)

        metrics[instrument_id] = {
            "peak_value_gbp": peak_value,
            "peak_last_price": peak_price,
            "drawdown_from_peak_pct": drawdown,
            "quantity_unchanged_snapshot_count": _quantity_unchanged_snapshot_count(snapshots),
        }
    return metrics


def build_instrument_out(
    instrument: Instrument,
    snapshot: HoldingSnapshot | None,
    *,
    quote: InstrumentQuote | None = None,
    group_ids: Sequence[int] | None = None,
    trailing_drip_yield_pct: float | None = None,
    previous_snapshot: HoldingSnapshot | None = None,
    metrics: dict[str, float | int | None] | None = None,
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
        peak_value_gbp=metrics.get("peak_value_gbp") if metrics else None,
        peak_last_price=metrics.get("peak_last_price") if metrics else None,
        drawdown_from_peak_pct=metrics.get("drawdown_from_peak_pct") if metrics else None,
        quantity_unchanged_snapshot_count=(
            int(metrics["quantity_unchanged_snapshot_count"])
            if metrics and metrics.get("quantity_unchanged_snapshot_count") is not None
            else None
        ),
        group_ids=sorted(group_ids) if group_ids else [],
    )


async def build_portfolio_summary(session: AsyncSession) -> dict:
    snaps = await get_current_snapshots(session)
    if not snaps:
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

    batch_ids = {snapshot.import_batch_id for snapshot in snaps}
    batch_result = await session.execute(select(ImportBatch).where(ImportBatch.id.in_(batch_ids)))
    batches = list(batch_result.scalars().all())
    latest_batch = max(batches, key=lambda batch: batch.id) if batches else None
    latest_as_of = max((batch.as_of_date for batch in batches), default=None)

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
        "as_of_date": latest_as_of,
        "import_batch_id": latest_batch.id if latest_batch is not None else None,
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
    """Portfolio value after each import, carrying forward untouched account snapshots."""
    batches_result = await session.execute(
        select(ImportBatch).order_by(ImportBatch.as_of_date, ImportBatch.id)
    )
    batches = list(batches_result.scalars().all())
    if not batches:
        return []

    snapshots_result = await session.execute(
        select(HoldingSnapshot)
        .join(Instrument)
        .options(selectinload(HoldingSnapshot.instrument))
        .order_by(HoldingSnapshot.import_batch_id)
    )
    snapshots_by_batch: dict[int, list[HoldingSnapshot]] = defaultdict(list)
    for snapshot in snapshots_result.scalars().all():
        snapshots_by_batch[snapshot.import_batch_id].append(snapshot)

    current_by_instrument: dict[int, HoldingSnapshot] = {}
    rows: list[dict] = []
    for batch in batches:
        for snapshot in snapshots_by_batch.get(batch.id, []):
            current_by_instrument[snapshot.instrument_id] = snapshot

        for closed in (batch.diff_summary or {}).get("closed", []):
            instrument_id = closed.get("instrument_id")
            if instrument_id is not None:
                current_by_instrument.pop(int(instrument_id), None)

        total_value = sum(snapshot.value_gbp or 0.0 for snapshot in current_by_instrument.values())
        total_book = sum(
            snapshot.book_cost_gbp or 0.0
            for snapshot in current_by_instrument.values()
            if not snapshot.instrument.is_cash
        )
        rows.append(
            {
                "as_of_date": batch.as_of_date.isoformat(),
                "total_value_gbp": float(total_value or 0.0),
                "total_book_cost_gbp": float(total_book or 0.0),
            }
        )

    return rows

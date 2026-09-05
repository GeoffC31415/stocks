from __future__ import annotations

import datetime as dt
import math
from collections import defaultdict
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models import HoldingSnapshot, ImportBatch, Instrument, Order
from app.services.order_scope_service import order_account_scope
from app.services.valuation_service import valuation_state_at_batch

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


BASE_NOTES = [
    "DRIP purchases are treated as an internal/reinvested income proxy, not as external contributions.",
    "Sales are treated as withdrawals because the source data cannot show whether proceeds remained in the account.",
    "Residual market movement is an attribution estimate after observed external flows and the DRIP proxy.",
]


def _batch_metadata(batch: ImportBatch | None) -> dict | None:
    if batch is None:
        return None
    return {
        "id": batch.id,
        "created_at": batch.created_at,
        "as_of_date": batch.as_of_date,
        "file_sha256": batch.file_sha256,
        "filename": batch.filename,
        "diff_summary": batch.diff_summary,
    }


def _unavailable(
    *, from_batch: ImportBatch | None, to_batch: ImportBatch | None, note: str
) -> dict:
    return {
        "from_batch": _batch_metadata(from_batch),
        "to_batch": _batch_metadata(to_batch),
        "opening_value_gbp": None,
        "closing_value_gbp": None,
        "raw_value_change_gbp": None,
        "contributions_gbp": None,
        "withdrawals_gbp": None,
        "drip_proxy_gbp": None,
        "net_external_flow_gbp": None,
        "residual_market_movement_gbp": None,
        "reconciliation_difference_gbp": None,
        "top_contributors": [],
        "top_detractors": [],
        "movements": [],
        "unallocated_residual_gbp": None,
        "percentage_point_reason": "Percentage-point attribution is unavailable: no validated additive return denominator is defined.",
        "notes": BASE_NOTES + [note],
    }


def _select_default_from_batch(
    relevant: list[ImportBatch], to_batch: ImportBatch
) -> ImportBatch | None:
    """Select the latest earlier batch from a distinct snapshot date."""
    prior = [
        batch
        for batch in relevant
        if batch.as_of_date < to_batch.as_of_date
    ]
    return max(prior, key=lambda batch: (batch.as_of_date, batch.id)) if prior else None


async def get_snapshot_attribution(
    session: AsyncSession,
    *,
    account_name: str | None = None,
    from_batch_id: int | None = None,
    to_batch_id: int | None = None,
) -> dict:
    """Attribute a snapshot value change to observed flows, DRIP, and a residual estimate."""
    relevant_query = (
        select(ImportBatch)
        .join(HoldingSnapshot, HoldingSnapshot.import_batch_id == ImportBatch.id)
        .join(Instrument, Instrument.id == HoldingSnapshot.instrument_id)
        .distinct()
        .order_by(ImportBatch.as_of_date, ImportBatch.id)
    )
    if account_name is not None:
        relevant_query = relevant_query.where(Instrument.account_name == account_name)
    relevant = list((await session.execute(relevant_query)).scalars().all())

    to_batch = await session.get(ImportBatch, to_batch_id) if to_batch_id is not None else None
    if to_batch_id is None and relevant:
        to_batch = relevant[-1]
    if to_batch_id is not None and to_batch is None:
        return _unavailable(
            from_batch=None,
            to_batch=None,
            note="The requested closing snapshot batch does not exist.",
        )
    if to_batch is None:
        return _unavailable(
            from_batch=None,
            to_batch=None,
            note="No portfolio snapshots are available for this selection.",
        )

    from_batch = (
        await session.get(ImportBatch, from_batch_id) if from_batch_id is not None else None
    )
    if from_batch_id is None:
        from_batch = _select_default_from_batch(relevant, to_batch)
    if from_batch_id is not None and from_batch is None:
        return _unavailable(
            from_batch=None,
            to_batch=to_batch,
            note="The requested opening snapshot batch does not exist.",
        )
    if from_batch is None:
        return _unavailable(
            from_batch=None,
            to_batch=to_batch,
            note="No previous snapshot is available for this selection, so change attribution is unavailable.",
        )
    if from_batch.as_of_date >= to_batch.as_of_date:
        return _unavailable(
            from_batch=from_batch,
            to_batch=to_batch,
            note="The opening valuation date must precede the closing valuation date; same-date comparisons are unavailable.",
        )

    opening_state = await valuation_state_at_batch(session, from_batch, account_name)
    closing_state = await valuation_state_at_batch(session, to_batch, account_name)
    if opening_state is None or closing_state is None:
        return _unavailable(
            from_batch=from_batch,
            to_batch=to_batch,
            note="Both snapshot boundaries must contain holdings for this selection.",
        )
    if opening_state.account_dates.keys() != closing_state.account_dates.keys():
        return _unavailable(from_batch=from_batch, to_batch=to_batch,
                            note="Selected account coverage changed between boundaries; it cannot be attributed as market movement.")
    opening = {s.instrument_id: s for s in opening_state.snapshots}
    closing = {s.instrument_id: s for s in closing_state.snapshots}
    boundary_snapshots = list(opening.values()) + list(closing.values())
    if (any(snapshot.value_gbp is None or not math.isfinite(snapshot.value_gbp) for snapshot in boundary_snapshots)
            or not all(math.isfinite(sum(s.value_gbp or 0 for s in boundary))
                       for boundary in (opening.values(), closing.values()))):
        return _unavailable(
            from_batch=from_batch,
            to_batch=to_batch,
            note="A boundary snapshot has a missing or non-finite GBP value, so attribution is unavailable.",
        )

    history_query = select(Order)
    if account_name is not None:
        history_query = history_query.where(order_account_scope(account_name))
    has_order_history = (
        await session.execute(history_query.limit(1))
    ).scalar_one_or_none() is not None
    if not has_order_history:
        result = _unavailable(
            from_batch=from_batch,
            to_batch=to_batch,
            note="No imported order history is available for this selection; flows and residual attribution are unknown.",
        )
        result.update(
            opening_value_gbp=sum(float(snapshot.value_gbp) for snapshot in opening.values()),
            closing_value_gbp=sum(float(snapshot.value_gbp) for snapshot in closing.values()),
        )
        result["raw_value_change_gbp"] = result["closing_value_gbp"] - result["opening_value_gbp"]
        return result

    orders_query = select(Order).where(
        Order.order_date > dt.datetime.combine(from_batch.as_of_date, dt.time.max),
        Order.order_date <= dt.datetime.combine(to_batch.as_of_date, dt.time.max),
    )
    if account_name is not None:
        orders_query = orders_query.where(order_account_scope(account_name))
    orders = list((await session.execute(orders_query.order_by(Order.order_date))).scalars().all())

    contributions = withdrawals = drip_proxy = 0.0
    external_by_instrument: dict[int, float] = defaultdict(float)
    drip_by_instrument: dict[int, float] = defaultdict(float)
    unlinked_count = 0
    missing_amount_count = 0
    source_orders: dict[int, list[int]] = defaultdict(list)
    for order in orders:
        if order.cost_proceeds_gbp is None or not math.isfinite(order.cost_proceeds_gbp) or order.side.lower() not in {"buy", "sell"}:
            missing_amount_count += 1
            continue
        amount = abs(float(order.cost_proceeds_gbp))
        side = order.side.lower()
        if side == "buy" and order.is_drip:
            drip_proxy += amount
            if order.instrument_id is not None:
                drip_by_instrument[order.instrument_id] += amount
        elif side == "buy":
            contributions += amount
            if order.instrument_id is not None:
                external_by_instrument[order.instrument_id] += amount
        elif side == "sell":
            withdrawals += amount
            if order.instrument_id is not None:
                external_by_instrument[order.instrument_id] -= amount
        else:
            continue
        if order.instrument_id is None:
            unlinked_count += 1
        else:
            source_orders[order.instrument_id].append(order.id)

    opening_value = sum(float(snapshot.value_gbp) for snapshot in opening.values())
    closing_value = sum(float(snapshot.value_gbp) for snapshot in closing.values())
    raw_change = closing_value - opening_value
    if missing_amount_count or not all(math.isfinite(value) for value in (contributions, withdrawals, drip_proxy, raw_change)):
        result = _unavailable(from_batch=from_batch, to_batch=to_batch,
                              note="Complete flows are unknown: missing/unsupported order amounts or a non-finite aggregate prevent residual attribution.")
        result.update(opening_value_gbp=opening_value, closing_value_gbp=closing_value,
                      raw_value_change_gbp=raw_change if math.isfinite(raw_change) else None)
        return result
    net_external = contributions - withdrawals
    residual = raw_change - net_external - drip_proxy
    reconciliation = raw_change - (net_external + drip_proxy + residual)

    movements: list[dict] = []
    for instrument_id in set(opening) | set(closing):
        before = opening.get(instrument_id)
        after = closing.get(instrument_id)
        snapshot = after or before
        if snapshot is None:
            continue
        opening_amount = float(before.value_gbp) if before is not None else 0.0
        closing_amount = float(after.value_gbp) if after is not None else 0.0
        raw = closing_amount - opening_amount
        external = external_by_instrument[instrument_id]
        drip = drip_by_instrument[instrument_id]
        movements.append(
            {
                "instrument_id": instrument_id,
                "source_order_ids": source_orders[instrument_id],
                "contribution_pct_points": None,
                "identifier": snapshot.instrument.identifier,
                "security_name": snapshot.instrument.security_name,
                "account_name": snapshot.instrument.account_name,
                "opening_value_gbp": opening_amount,
                "closing_value_gbp": closing_amount,
                "raw_value_change_gbp": raw,
                "net_external_flow_gbp": external,
                "drip_proxy_gbp": drip,
                "estimated_market_movement_gbp": raw - external - drip,
            }
        )
    contributors = sorted(
        (row for row in movements if row["estimated_market_movement_gbp"] > 0),
        key=lambda row: row["estimated_market_movement_gbp"],
        reverse=True,
    )[:5]
    detractors = sorted(
        (row for row in movements if row["estimated_market_movement_gbp"] < 0),
        key=lambda row: row["estimated_market_movement_gbp"],
    )[:5]
    notes = list(BASE_NOTES)
    if unlinked_count:
        notes.append(
            f"{unlinked_count} flow order(s) were not linked to an instrument; per-instrument estimates do not allocate those flows."
        )
    if any(date != from_batch.as_of_date for date in opening_state.account_dates.values()) or any(date != to_batch.as_of_date for date in closing_state.account_dates.values()):
        notes.append("Some account valuations are carried forward at these boundaries; market movement is not synchronously observed.")
    return {
        "from_batch": _batch_metadata(from_batch),
        "to_batch": _batch_metadata(to_batch),
        "opening_value_gbp": opening_value,
        "closing_value_gbp": closing_value,
        "raw_value_change_gbp": raw_change,
        "contributions_gbp": contributions,
        "withdrawals_gbp": withdrawals,
        "drip_proxy_gbp": drip_proxy,
        "net_external_flow_gbp": net_external,
        "residual_market_movement_gbp": residual,
        "reconciliation_difference_gbp": reconciliation,
        "movements": movements,
        "unallocated_residual_gbp": residual - sum(row["estimated_market_movement_gbp"] for row in movements),
        "percentage_point_reason": "Percentage-point attribution is unavailable: no validated additive return denominator is defined.",
        "top_contributors": contributors,
        "top_detractors": detractors,
        "notes": notes,
    }

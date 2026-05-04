from __future__ import annotations

import datetime
import hashlib
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    HoldingSnapshot,
    ImportBatch,
    Instrument,
    InstrumentGroup,
    InstrumentGroupMember,
    Order,
    OrderImportBatch,
)
from app.services.barclays_order_parser import ParsedOrderRow, parse_barclays_order_xls_bytes
from app.services.hl_parser import parse_hl_activity_csv_bytes
from app.services.instrument_matcher import link_orders_to_instruments
from app.services.order_fingerprint import order_fingerprint


class DuplicateOrderImportError(Exception):
    def __init__(self, batch_id: int) -> None:
        self.batch_id = batch_id
        super().__init__(f"Identical order history file already imported as batch {batch_id}")


def _cagr(start_value: float, end_value: float, start: datetime.date, end: datetime.date) -> float | None:
    """Compound Annual Growth Rate as a percentage. Returns None when not meaningful."""
    years = (end - start).days / 365.25
    if years < 0.25 or start_value <= 0 or end_value <= 0:
        return None
    try:
        return ((end_value / start_value) ** (1.0 / years) - 1.0) * 100.0
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def _cashflow_amount(order: Order, *, drip_threshold_gbp: float) -> float:
    cost = order.cost_proceeds_gbp or 0.0
    side = order.side.lower()
    is_drip = side == "buy" and cost < drip_threshold_gbp
    if side == "buy" and not is_drip:
        return cost
    if side == "sell":
        return -cost
    return 0.0


def _modified_dietz_annualised(
    orders: list[Order],
    *,
    end_value: float,
    end_date: datetime.date,
    drip_threshold_gbp: float,
) -> float | None:
    cashflows = [
        (order.order_date.date(), _cashflow_amount(order, drip_threshold_gbp=drip_threshold_gbp))
        for order in orders
        if order.cost_proceeds_gbp is not None
    ]
    cashflows = [(flow_date, amount) for flow_date, amount in cashflows if amount != 0.0]
    if not cashflows:
        return None

    start_date = min(flow_date for flow_date, _ in cashflows)
    total_days = (end_date - start_date).days
    if total_days < 91:
        return None

    net_flows = sum(amount for _, amount in cashflows)
    weighted_flows = 0.0
    for flow_date, amount in cashflows:
        days_after_flow = max((end_date - flow_date).days, 0)
        weighted_flows += amount * (days_after_flow / total_days)

    if weighted_flows <= 0:
        return None

    period_return = (end_value - net_flows) / weighted_flows
    if period_return <= -1:
        return -100.0

    years = total_days / 365.25
    try:
        return ((1.0 + period_return) ** (1.0 / years) - 1.0) * 100.0
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def _trailing_drip_yield_pct(
    orders: list[Order],
    *,
    average_value_gbp: float | None,
    end_date: datetime.date,
    drip_threshold_gbp: float,
) -> float | None:
    if average_value_gbp is None or average_value_gbp <= 0:
        return None
    start_date = end_date - datetime.timedelta(days=365)
    drip_total = 0.0
    for order in orders:
        cost = order.cost_proceeds_gbp or 0.0
        if (
            start_date <= order.order_date.date() <= end_date
            and order.side.lower() == "buy"
            and cost < drip_threshold_gbp
        ):
            drip_total += cost
    if drip_total <= 0:
        return None
    return (drip_total / average_value_gbp) * 100.0


async def import_order_history(
    session: AsyncSession,
    *,
    file_bytes: bytes,
    filename: str | None,
    drip_threshold_gbp: float,
    force: bool = False,
) -> tuple[OrderImportBatch, int]:
    parsed: list[ParsedOrderRow] = parse_barclays_order_xls_bytes(
        file_bytes, drip_threshold_gbp=drip_threshold_gbp
    )
    return await ingest_parsed_orders(
        session,
        parsed=parsed,
        file_bytes=file_bytes,
        filename=filename,
        force=force,
    )


async def import_hl_orders_csv(
    session: AsyncSession,
    *,
    file_bytes: bytes,
    filename: str | None,
    drip_threshold_gbp: float,
    force: bool = False,
) -> tuple[OrderImportBatch, int]:
    parsed = parse_hl_activity_csv_bytes(
        file_bytes,
        drip_threshold_gbp=drip_threshold_gbp,
    )
    return await ingest_parsed_orders(
        session,
        parsed=parsed,
        file_bytes=file_bytes,
        filename=filename,
        force=force,
    )


async def ingest_parsed_orders(
    session: AsyncSession,
    *,
    parsed: list[ParsedOrderRow],
    file_bytes: bytes,
    filename: str | None,
    force: bool = False,
) -> tuple[OrderImportBatch, int]:
    sha = hashlib.sha256(file_bytes).hexdigest()
    if not force:
        dup = (
            await session.execute(
                select(OrderImportBatch).where(OrderImportBatch.file_sha256 == sha)
            )
        ).scalar_one_or_none()
        if dup is not None:
            raise DuplicateOrderImportError(dup.id)

    existing = await session.execute(select(Order.order_fingerprint))
    seen_fingerprints = {fingerprint for fingerprint in existing.scalars().all() if fingerprint}

    batch = OrderImportBatch(
        file_sha256=sha,
        filename=filename,
        row_count=0,
    )
    session.add(batch)
    await session.flush()

    new_orders: list[Order] = []
    for row in parsed:
        fingerprint = order_fingerprint(
            security_name=row.security_name,
            order_date=row.order_date,
            order_status=row.order_status,
            account_name=row.account_name,
            side=row.side,
            quantity=row.quantity,
            cost_proceeds_gbp=row.cost_proceeds_gbp,
            country=row.country,
        )
        if fingerprint in seen_fingerprints:
            continue

        seen_fingerprints.add(fingerprint)
        order = Order(
            order_import_batch_id=batch.id,
            security_name=row.security_name,
            order_date=row.order_date,
            order_status=row.order_status,
            account_name=row.account_name,
            side=row.side,
            quantity=row.quantity,
            cost_proceeds_gbp=row.cost_proceeds_gbp,
            country=row.country,
            is_drip=row.is_drip,
            order_fingerprint=fingerprint,
        )
        session.add(order)
        new_orders.append(order)

    batch.row_count = len(new_orders)
    await session.flush()
    await link_orders_to_instruments(session, new_orders)

    await session.commit()
    await session.refresh(batch)
    return batch, len(new_orders)


async def get_order_analytics(
    session: AsyncSession,
    *,
    drip_threshold_gbp: float = 1000.0,
) -> dict:
    r = await session.execute(select(Order).order_by(Order.order_date))
    orders = list(r.scalars().all())

    if not orders:
        return {
            "total_orders": 0,
            "total_buy_gbp": 0.0,
            "total_drip_gbp": 0.0,
            "total_sell_gbp": 0.0,
            "cash_deployed_gbp": 0.0,
            "net_cash_invested_gbp": 0.0,
            "drip_count": 0,
            "buy_count": 0,
            "sell_count": 0,
            "drip_threshold_gbp": drip_threshold_gbp,
            "annual_drip": [],
            "first_order_date": None,
        }

    total_buy = 0.0
    total_drip = 0.0
    total_sell = 0.0
    buy_count = 0
    sell_count = 0
    drip_count = 0
    annual_drip: dict[int, float] = defaultdict(float)

    for o in orders:
        cost = o.cost_proceeds_gbp or 0.0
        is_drip = o.side.lower() == "buy" and o.cost_proceeds_gbp is not None and o.cost_proceeds_gbp < drip_threshold_gbp

        if o.side.lower() == "buy":
            total_buy += cost
            buy_count += 1
            if is_drip:
                total_drip += cost
                drip_count += 1
                annual_drip[o.order_date.year] += cost
        elif o.side.lower() == "sell":
            total_sell += cost
            sell_count += 1

    cash_deployed = total_buy - total_drip
    net_cash_invested = cash_deployed - total_sell

    first_order_date = min(o.order_date for o in orders).isoformat()

    return {
        "total_orders": len(orders),
        "total_buy_gbp": round(total_buy, 2),
        "total_drip_gbp": round(total_drip, 2),
        "total_sell_gbp": round(total_sell, 2),
        "cash_deployed_gbp": round(cash_deployed, 2),
        "net_cash_invested_gbp": round(net_cash_invested, 2),
        "drip_count": drip_count,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "drip_threshold_gbp": drip_threshold_gbp,
        "annual_drip": [
            {"year": year, "total_gbp": round(v, 2)}
            for year, v in sorted(annual_drip.items())
        ],
        "first_order_date": first_order_date,
    }


async def get_cashflow_timeseries(
    session: AsyncSession,
    *,
    drip_threshold_gbp: float = 1000.0,
) -> list[dict]:
    """Monthly cumulative cash-flow breakdown from order history."""
    r = await session.execute(select(Order).order_by(Order.order_date))
    orders = list(r.scalars().all())
    if not orders:
        return []

    monthly: dict[str, dict] = {}
    for o in orders:
        key = o.order_date.strftime("%Y-%m")
        if key not in monthly:
            monthly[key] = {"discretionary": 0.0, "drip": 0.0, "sells": 0.0}
        cost = o.cost_proceeds_gbp or 0.0
        is_drip = o.side.lower() == "buy" and cost < drip_threshold_gbp
        if o.side.lower() == "buy":
            if is_drip:
                monthly[key]["drip"] += cost
            else:
                monthly[key]["discretionary"] += cost
        elif o.side.lower() == "sell":
            monthly[key]["sells"] += cost

    cum_deployed = 0.0
    cum_drip = 0.0
    cum_sells = 0.0
    result: list[dict] = []
    for key in sorted(monthly):
        m = monthly[key]
        cum_deployed += m["discretionary"] - m["sells"]
        cum_drip += m["drip"]
        cum_sells += m["sells"]
        result.append(
            {
                "month": key,
                "monthly_discretionary": round(m["discretionary"], 2),
                "monthly_drip": round(m["drip"], 2),
                "monthly_sells": round(m["sells"], 2),
                "cumulative_net_deployed": round(cum_deployed, 2),
                "cumulative_drip": round(cum_drip, 2),
                "cumulative_sells": round(cum_sells, 2),
            }
        )
    return result


async def get_estimated_portfolio_timeseries(
    session: AsyncSession,
) -> list[dict]:
    """
    For each month in the order history, estimate portfolio value by applying
    current snapshot prices to the running share quantities from orders.

    Uses the instrument_id FK on orders for reliable price lookup.
    """
    from app.services.portfolio_service import get_current_snapshots

    snapshots = await get_current_snapshots(session)
    price_per_instrument: dict[int, float] = {}
    for snapshot in snapshots:
        if (
            not snapshot.instrument.is_cash
            and snapshot.quantity
            and snapshot.quantity > 0
            and snapshot.value_gbp
        ):
            price_per_instrument[snapshot.instrument_id] = snapshot.value_gbp / snapshot.quantity

    if not price_per_instrument:
        return []

    r = await session.execute(select(Order).order_by(Order.order_date))
    orders = list(r.scalars().all())
    if not orders:
        return []

    all_months = sorted({o.order_date.strftime("%Y-%m") for o in orders})
    orders_by_month: dict[str, list[Order]] = defaultdict(list)
    for o in orders:
        orders_by_month[o.order_date.strftime("%Y-%m")].append(o)

    running_qty: dict[int, float] = defaultdict(float)
    result: list[dict] = []

    for month in all_months:
        for o in orders_by_month[month]:
            if o.instrument_id is None:
                continue
            qty = o.quantity or 0.0
            if o.side.lower() == "buy":
                running_qty[o.instrument_id] += qty
            elif o.side.lower() == "sell":
                running_qty[o.instrument_id] = max(0.0, running_qty[o.instrument_id] - qty)

        total = sum(
            qty * price_per_instrument[iid]
            for iid, qty in running_qty.items()
            if qty > 0 and iid in price_per_instrument
        )
        result.append({"month": month, "estimated_value_gbp": round(total, 2)})

    return result


async def get_order_positions(
    session: AsyncSession,
    *,
    drip_threshold_gbp: float = 1000.0,
) -> list[dict]:
    """
    Per-security position analysis derived from order history,
    enriched with current portfolio values via instrument_id FK.
    """
    r = await session.execute(select(Order).order_by(Order.order_date))
    orders = list(r.scalars().all())
    if not orders:
        return []

    # Aggregate by instrument_id where available, fall back to security_name
    agg: dict[str | int, dict] = {}
    for o in orders:
        key: str | int = o.instrument_id if o.instrument_id is not None else o.security_name.lower().strip()
        if key not in agg:
            agg[key] = {
                "security_name": o.security_name,
                "instrument_id": o.instrument_id,
                "total_buy_gbp": 0.0,
                "discretionary_buy_gbp": 0.0,
                "total_drip_gbp": 0.0,
                "total_sell_gbp": 0.0,
                "order_count": 0,
                "drip_count": 0,
                "first_order": o.order_date,
                "last_order": o.order_date,
                "orders": [],
            }
        p = agg[key]
        cost = o.cost_proceeds_gbp or 0.0
        is_drip = o.side.lower() == "buy" and cost < drip_threshold_gbp
        p["order_count"] += 1
        p["orders"].append(o)
        p["last_order"] = max(p["last_order"], o.order_date)
        p["first_order"] = min(p["first_order"], o.order_date)
        if o.side.lower() == "buy":
            p["total_buy_gbp"] += cost
            if is_drip:
                p["total_drip_gbp"] += cost
                p["drip_count"] += 1
            else:
                p["discretionary_buy_gbp"] += cost
        elif o.side.lower() == "sell":
            p["total_sell_gbp"] += cost

    from app.services.portfolio_service import get_current_snapshots

    instrument_values: dict[int, float] = {}
    average_values: dict[int, float] = {}
    current_snapshots = await get_current_snapshots(session)
    if current_snapshots:
        for s in current_snapshots:
            if not s.instrument.is_cash and s.value_gbp is not None:
                instrument_values[s.instrument_id] = s.value_gbp
        history_result = await session.execute(
            select(HoldingSnapshot).join(Instrument).where(Instrument.is_cash.is_(False))
        )
        value_samples: dict[int, list[float]] = defaultdict(list)
        for s in history_result.scalars().all():
            if s.value_gbp is not None:
                value_samples[s.instrument_id].append(s.value_gbp)
        average_values = {
            instrument_id: sum(values) / len(values)
            for instrument_id, values in value_samples.items()
            if values
        }

    today = datetime.date.today()
    result: list[dict] = []

    for p in agg.values():
        iid = p["instrument_id"]
        current_value = instrument_values.get(iid) if iid is not None else None
        net_cost = p["discretionary_buy_gbp"] - p["total_sell_gbp"]
        is_closed = current_value is None
        first_date = p["first_order"].date()
        last_date = p["last_order"].date()

        estimated_pnl = None
        annualised_return_pct = None
        realized_pnl = None

        if current_value is not None:
            estimated_pnl = current_value - net_cost
            annualised_return_pct = _modified_dietz_annualised(
                p["orders"],
                end_value=current_value,
                end_date=today,
                drip_threshold_gbp=drip_threshold_gbp,
            )
        elif is_closed:
            realized_pnl = p["total_sell_gbp"] - p["total_buy_gbp"]
            if p["total_buy_gbp"] > 0 and p["total_sell_gbp"] > 0:
                annualised_return_pct = _cagr(p["total_buy_gbp"], p["total_sell_gbp"], first_date, last_date)
            elif p["total_buy_gbp"] > 0 and p["total_sell_gbp"] == 0:
                annualised_return_pct = -100.0

        result.append(
            {
                "security_name": p["security_name"],
                "instrument_id": iid,
                "total_buy_gbp": round(p["total_buy_gbp"], 2),
                "discretionary_buy_gbp": round(p["discretionary_buy_gbp"], 2),
                "total_drip_gbp": round(p["total_drip_gbp"], 2),
                "total_sell_gbp": round(p["total_sell_gbp"], 2),
                "net_cost_gbp": round(net_cost, 2),
                "order_count": p["order_count"],
                "drip_count": p["drip_count"],
                "first_order_date": first_date.isoformat(),
                "last_order_date": last_date.isoformat(),
                "current_value_gbp": round(current_value, 2) if current_value is not None else None,
                "estimated_pnl_gbp": round(estimated_pnl, 2) if estimated_pnl is not None else None,
                "annualised_return_pct": round(annualised_return_pct, 1) if annualised_return_pct is not None else None,
                "trailing_drip_yield_pct": (
                    round(
                        _trailing_drip_yield_pct(
                            p["orders"],
                            average_value_gbp=average_values.get(iid) if iid is not None else None,
                            end_date=today,
                            drip_threshold_gbp=drip_threshold_gbp,
                        ),
                        2,
                    )
                    if iid is not None
                    and _trailing_drip_yield_pct(
                        p["orders"],
                        average_value_gbp=average_values.get(iid),
                        end_date=today,
                        drip_threshold_gbp=drip_threshold_gbp,
                    )
                    is not None
                    else None
                ),
                "realized_pnl_gbp": round(realized_pnl, 2) if realized_pnl is not None else None,
                "is_closed": is_closed,
            }
        )

    result.sort(
        key=lambda x: (
            x["is_closed"],
            -(x["net_cost_gbp"] if not x["is_closed"] else abs(x["realized_pnl_gbp"] or 0)),
        )
    )
    return result


async def get_group_performance(
    session: AsyncSession,
    *,
    drip_threshold_gbp: float = 1000.0,
) -> list[dict]:
    """Per-group performance: combined value, P&L, CAGR, snapshot history and member breakdown.

    A group's combined CAGR uses the earliest order_date among members, the sum of
    discretionary cost flows minus sells (i.e. external capital invested) and the
    current snapshot value. A weighted-CAGR is also returned (average of member
    CAGRs weighted by absolute net cost) which is more robust when members
    started at very different times.
    """
    groups_result = await session.execute(
        select(InstrumentGroup).order_by(InstrumentGroup.name)
    )
    groups = list(groups_result.scalars().all())
    if not groups:
        return []

    members_result = await session.execute(select(InstrumentGroupMember))
    members_by_group: dict[int, list[int]] = defaultdict(list)
    for m in members_result.scalars().all():
        members_by_group[m.group_id].append(m.instrument_id)

    all_member_ids = {iid for ids in members_by_group.values() for iid in ids}
    if not all_member_ids:
        return [
            {
                "group_id": g.id,
                "name": g.name,
                "color": g.color,
                "member_count": 0,
                "members_with_value": 0,
                "total_current_value_gbp": 0.0,
                "total_net_cost_gbp": 0.0,
                "total_pnl_gbp": 0.0,
                "pnl_pct": None,
                "combined_cagr_pct": None,
                "weighted_cagr_pct": None,
                "earliest_order_date": None,
                "timeseries": [],
                "members": [],
            }
            for g in groups
        ]

    instruments_result = await session.execute(
        select(Instrument).where(Instrument.id.in_(all_member_ids))
    )
    instrument_by_id: dict[int, Instrument] = {
        i.id: i for i in instruments_result.scalars().all()
    }

    orders_result = await session.execute(
        select(Order)
        .where(Order.instrument_id.in_(all_member_ids))
        .order_by(Order.order_date)
    )
    orders = list(orders_result.scalars().all())

    per_instrument: dict[int, dict] = {}
    for o in orders:
        iid = o.instrument_id
        if iid is None:
            continue
        slot = per_instrument.setdefault(
            iid,
            {
                "total_buy_gbp": 0.0,
                "discretionary_buy_gbp": 0.0,
                "total_drip_gbp": 0.0,
                "total_sell_gbp": 0.0,
                "first_order": o.order_date,
                "last_order": o.order_date,
                "orders": [],
            },
        )
        cost = o.cost_proceeds_gbp or 0.0
        is_drip = o.side.lower() == "buy" and cost < drip_threshold_gbp
        slot["first_order"] = min(slot["first_order"], o.order_date)
        slot["last_order"] = max(slot["last_order"], o.order_date)
        slot["orders"].append(o)
        if o.side.lower() == "buy":
            slot["total_buy_gbp"] += cost
            if is_drip:
                slot["total_drip_gbp"] += cost
            else:
                slot["discretionary_buy_gbp"] += cost
        elif o.side.lower() == "sell":
            slot["total_sell_gbp"] += cost

    from app.services.portfolio_service import get_current_snapshots

    current_values: dict[int, float] = {}
    for s in await get_current_snapshots(session):
        if s.instrument_id in all_member_ids and s.value_gbp is not None:
            current_values[s.instrument_id] = s.value_gbp

    batches_result = await session.execute(
        select(ImportBatch).order_by(ImportBatch.as_of_date, ImportBatch.id)
    )
    batches = list(batches_result.scalars().all())

    snapshots_by_batch: dict[int, dict[int, HoldingSnapshot]] = {}
    if batches:
        history_result = await session.execute(
            select(HoldingSnapshot).where(
                HoldingSnapshot.instrument_id.in_(all_member_ids)
            )
        )
        for s in history_result.scalars().all():
            snapshots_by_batch.setdefault(s.import_batch_id, {})[s.instrument_id] = s

    group_timeseries: dict[int, list[dict]] = {group.id: [] for group in groups}
    current_snapshots: dict[int, HoldingSnapshot] = {}
    for batch in batches:
        current_snapshots.update(snapshots_by_batch.get(batch.id, {}))
        for closed in (batch.diff_summary or {}).get("closed", []):
            instrument_id = closed.get("instrument_id")
            if instrument_id is not None:
                current_snapshots.pop(int(instrument_id), None)

        for group in groups:
            v = 0.0
            bc = 0.0
            for iid in members_by_group.get(group.id, []):
                snap = current_snapshots.get(iid)
                if snap is None:
                    continue
                if snap.value_gbp is not None:
                    v += snap.value_gbp
                if snap.book_cost_gbp is not None:
                    bc += snap.book_cost_gbp
            group_timeseries[group.id].append(
                {
                    "as_of_date": batch.as_of_date,
                    "value_gbp": round(v, 2),
                    "book_cost_gbp": round(bc, 2),
                }
            )

    today = datetime.date.today()
    out: list[dict] = []

    for g in groups:
        member_ids = members_by_group.get(g.id, [])
        members_view: list[dict] = []
        total_value = 0.0
        total_net_cost = 0.0
        weighted_cagr_num = 0.0
        weighted_cagr_den = 0.0
        earliest: datetime.datetime | None = None
        members_with_value = 0

        for iid in member_ids:
            inst = instrument_by_id.get(iid)
            if inst is None:
                continue
            pos = per_instrument.get(iid)
            current_value = current_values.get(iid)
            net_cost = (
                (pos["discretionary_buy_gbp"] - pos["total_sell_gbp"]) if pos else 0.0
            )
            pnl = (
                (current_value - net_cost) if current_value is not None else None
            )
            cagr: float | None = None
            first_dt = pos["first_order"] if pos else None
            if (
                pos is not None
                and current_value is not None
                and net_cost > 0
                and first_dt is not None
            ):
                cagr = _modified_dietz_annualised(
                    pos["orders"],
                    end_value=current_value,
                    end_date=today,
                    drip_threshold_gbp=drip_threshold_gbp,
                )

            members_view.append(
                {
                    "instrument_id": iid,
                    "security_name": inst.security_name,
                    "identifier": inst.identifier,
                    "current_value_gbp": (
                        round(current_value, 2) if current_value is not None else None
                    ),
                    "net_cost_gbp": round(net_cost, 2),
                    "pnl_gbp": round(pnl, 2) if pnl is not None else None,
                    "annualised_return_pct": (
                        round(cagr, 1) if cagr is not None else None
                    ),
                    "weight_pct": None,
                    "first_order_date": (
                        first_dt.date().isoformat() if first_dt is not None else None
                    ),
                }
            )

            if current_value is not None:
                total_value += current_value
                members_with_value += 1
            total_net_cost += net_cost
            if first_dt is not None and (earliest is None or first_dt < earliest):
                earliest = first_dt
            if cagr is not None and net_cost > 0:
                weighted_cagr_num += cagr * net_cost
                weighted_cagr_den += net_cost

        if total_value > 0:
            for m in members_view:
                if m["current_value_gbp"] is not None:
                    m["weight_pct"] = round(
                        (m["current_value_gbp"] / total_value) * 100.0, 1
                    )

        members_view.sort(
            key=lambda m: (m["current_value_gbp"] or 0.0),
            reverse=True,
        )

        total_pnl = total_value - total_net_cost
        pnl_pct = (
            round((total_pnl / total_net_cost) * 100.0, 1)
            if total_net_cost > 0
            else None
        )
        group_orders = [
            order
            for iid in member_ids
            for order in per_instrument.get(iid, {}).get("orders", [])
        ]
        combined_cagr = (
            _modified_dietz_annualised(
                group_orders,
                end_value=total_value,
                end_date=today,
                drip_threshold_gbp=drip_threshold_gbp,
            )
            if total_value > 0
            else None
        )
        weighted_cagr = (
            (weighted_cagr_num / weighted_cagr_den) if weighted_cagr_den > 0 else None
        )

        out.append(
            {
                "group_id": g.id,
                "name": g.name,
                "color": g.color,
                "member_count": len(member_ids),
                "members_with_value": members_with_value,
                "total_current_value_gbp": round(total_value, 2),
                "total_net_cost_gbp": round(total_net_cost, 2),
                "total_pnl_gbp": round(total_pnl, 2),
                "pnl_pct": pnl_pct,
                "combined_cagr_pct": (
                    round(combined_cagr, 1) if combined_cagr is not None else None
                ),
                "weighted_cagr_pct": (
                    round(weighted_cagr, 1) if weighted_cagr is not None else None
                ),
                "earliest_order_date": (
                    earliest.date().isoformat() if earliest is not None else None
                ),
                "timeseries": group_timeseries.get(g.id, []),
                "members": members_view,
            }
        )

    out.sort(key=lambda x: x["total_current_value_gbp"], reverse=True)
    return out


async def get_orders_for_instrument(
    session: AsyncSession,
    instrument_id: int,
) -> list[Order]:
    r = await session.execute(
        select(Order)
        .where(Order.instrument_id == instrument_id)
        .order_by(Order.order_date.desc())
    )
    return list(r.scalars().all())

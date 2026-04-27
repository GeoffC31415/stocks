from __future__ import annotations

import datetime
import hashlib
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import HoldingSnapshot, Instrument, Order, OrderImportBatch
from app.services.barclays_order_parser import ParsedOrderRow, parse_barclays_order_xls_bytes
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


async def import_order_history(
    session: AsyncSession,
    *,
    file_bytes: bytes,
    filename: str | None,
    drip_threshold_gbp: float,
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

    parsed: list[ParsedOrderRow] = parse_barclays_order_xls_bytes(
        file_bytes, drip_threshold_gbp=drip_threshold_gbp
    )

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
    from app.services.portfolio_service import get_latest_batch

    batch = await get_latest_batch(session)
    if not batch:
        return []

    snap_result = await session.execute(
        select(HoldingSnapshot)
        .where(HoldingSnapshot.import_batch_id == batch.id)
        .join(Instrument)
        .where(Instrument.is_cash.is_(False))
    )
    price_per_instrument: dict[int, float] = {}
    for s in snap_result.scalars().all():
        if s.quantity and s.quantity > 0 and s.value_gbp:
            price_per_instrument[s.instrument_id] = s.value_gbp / s.quantity

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
            }
        p = agg[key]
        cost = o.cost_proceeds_gbp or 0.0
        is_drip = o.side.lower() == "buy" and cost < drip_threshold_gbp
        p["order_count"] += 1
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

    from app.services.portfolio_service import get_latest_batch

    batch = await get_latest_batch(session)
    instrument_values: dict[int, float] = {}
    if batch:
        snap_result = await session.execute(
            select(HoldingSnapshot)
            .where(HoldingSnapshot.import_batch_id == batch.id)
            .join(Instrument)
            .where(Instrument.is_cash.is_(False))
        )
        for s in snap_result.scalars().all():
            if s.value_gbp is not None:
                instrument_values[s.instrument_id] = s.value_gbp

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
            if net_cost > 0:
                annualised_return_pct = _cagr(net_cost, current_value, first_date, today)
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

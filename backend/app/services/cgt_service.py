"""UK Capital Gains Tax calculation for share portfolios.

Implements the three UK CGT matching rules for shares:
1. Same-day rule — buys & sells on the same day match first
2. Bed & breakfasting (30-day rule) — buys within 30 days after a sale
3. Section 104 pool — remaining shares form a pooled holding; sales use avg cost
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Instrument, Order


# ---------------------------------------------------------------------------
# Internal data classes
# ---------------------------------------------------------------------------


@dataclass
class Pool:
    """Section 104 holding — tracks quantity, cost and allowance."""

    quantity: float = 0.0
    cost: float = 0.0
    allowance: float = 0.0  # indexation allowance (not applicable pre-2008)


@dataclass
class SaleMatch:
    """A single matched pair (or group) contributing to a realised gain/loss."""

    source: str  # "same_day", "b&f", "pool"
    order_id: int | None = None
    order_date: str | None = None
    security_name: str | None = None
    quantity: float = 0.0
    cost: float = 0.0
    proceeds: float = 0.0


@dataclass
class SaleDetail:
    """Complete breakdown of one sell order."""

    order_id: int
    order_date: str
    security_name: str
    instrument_id: int | None
    quantity: float
    proceeds_gbp: float  # cost_proceeds_gbp from the sell order

    matches: list[SaleMatch] = field(default_factory=list)
    pool_quantity_before: float = 0.0
    pool_cost_before: float = 0.0
    pool_cost_per_share: float = 0.0

    # Aggregate results
    total_cost: float = 0.0
    total_proceeds: float = 0.0
    realised_gain: float = 0.0


# ---------------------------------------------------------------------------
# Core matching engine
# ---------------------------------------------------------------------------


def _tax_year_end(order_date: dt.datetime) -> int:
    """Return the tax year (6 Apr - 5 Apr) end year for an order date.

    Tax year 2023-24 runs 6 Apr 2023 - 5 Apr 2024, so the "end year" is 2024.
    """
    d = order_date.date()
    end_year = d.year if (d.month < 4 or (d.month == 4 and d.day <= 5)) else d.year + 1
    return end_year


def calculate_cgt_for_instrument(
    orders: list[Order],
) -> list[SaleDetail]:
    """Calculate CGT for a single instrument's order history.

    UK CGT matching rules for shares (in priority order):
    1. Same-day rule -- buys & sells on the same day
    2. Bed & breakfasting (30-day rule) -- buys within 30 days after a sell
    3. Section 104 pool -- remaining shares form a pooled holding with avg cost
    """
    buys = sorted(
        [o for o in orders if o.side.lower() == "buy"],
        key=lambda o: o.order_date,
    )
    sells = sorted(
        [o for o in orders if o.side.lower() == "sell"],
        key=lambda o: o.order_date,
    )

    if not sells:
        return []

    pool = Pool()
    sale_details: list[SaleDetail] = []

    # Track which buys have been consumed by same-day or b&f rules,
    # so they don't go into the pool.
    consumed_buys: set[int] = set()

    for sell in sells:
        sale = SaleDetail(
            order_id=sell.id,
            order_date=sell.order_date.isoformat(),
            security_name=sell.security_name,
            instrument_id=sell.instrument_id,
            quantity=sell.quantity or 0.0,
            proceeds_gbp=sell.cost_proceeds_gbp or 0.0,
        )
        sale.pool_quantity_before = pool.quantity
        sale.pool_cost_before = pool.cost
        sale.pool_cost_per_share = (
            pool.cost / pool.quantity if pool.quantity > 0 else 0.0
        )

        remaining_qty = sale.quantity

        # --- 0. Pre-populate pool with unconsumed buys before this sell ---
        for b in buys:
            if b.id in consumed_buys:
                continue
            if b.order_date.date() >= sell.order_date.date():
                continue
            qty = b.quantity or 0.0
            cost = b.cost_proceeds_gbp or 0.0
            pool.quantity += qty
            pool.cost += cost

        # --- 1. Same-day rule ---
        same_day_buys = [
            b for b in buys
            if b.order_date.date() == sell.order_date.date() and b.id not in consumed_buys
        ]
        for b in same_day_buys:
            if remaining_qty <= 0:
                break
            qty = b.quantity or 0.0
            cost = b.cost_proceeds_gbp or 0.0
            match_qty = min(qty, remaining_qty)
            match_cost = (cost / qty) * match_qty if qty > 0 else 0.0
            remaining_qty -= match_qty
            consumed_buys.add(b.id)
            sale.matches.append(
                SaleMatch(
                    source="same_day",
                    order_id=b.id,
                    order_date=b.order_date.isoformat(),
                    security_name=b.security_name,
                    quantity=match_qty,
                    cost=round(match_cost, 2),
                    proceeds=round((sell.cost_proceeds_gbp / sell.quantity) * match_qty, 2) if sell.quantity > 0 else 0.0,
                )
            )

        # --- 2. Bed & breakfasting (30-day rule) ---
        bf_limit = sell.order_date + dt.timedelta(days=30)
        bf_buys = [
            b for b in buys
            if sell.order_date < b.order_date <= bf_limit and b.id not in consumed_buys
        ]
        for b in bf_buys:
            if remaining_qty <= 0:
                break
            qty = b.quantity or 0.0
            cost = b.cost_proceeds_gbp or 0.0
            match_qty = min(qty, remaining_qty)
            match_cost = (cost / qty) * match_qty if qty > 0 else 0.0
            remaining_qty -= match_qty
            consumed_buys.add(b.id)
            sale.matches.append(
                SaleMatch(
                    source="b&f",
                    order_id=b.id,
                    order_date=b.order_date.isoformat(),
                    security_name=b.security_name,
                    quantity=match_qty,
                    cost=round(match_cost, 2),
                    proceeds=round((sell.cost_proceeds_gbp / sell.quantity) * match_qty, 2) if sell.quantity > 0 else 0.0,
                )
            )

        # --- 3. Section 104 pool ---
        if remaining_qty > 0 and pool.quantity > 0:
            pool_qty = min(remaining_qty, pool.quantity)
            pool_cost = (pool.cost / pool.quantity) * pool_qty if pool.quantity > 0 else 0.0
            remaining_qty -= pool_qty

            sale.matches.append(
                SaleMatch(
                    source="pool",
                    quantity=pool_qty,
                    cost=round(pool_cost, 2),
                    proceeds=round((sell.cost_proceeds_gbp / sell.quantity) * pool_qty, 2) if sell.quantity > 0 else 0.0,
                )
            )
            # Remove from pool
            pool.quantity -= pool_qty
            pool.cost -= pool_cost

        # Aggregate
        sale.total_cost = sum(m.cost for m in sale.matches)
        sale.total_proceeds = sell.cost_proceeds_gbp or 0.0
        sale.realised_gain = sale.total_proceeds - sale.total_cost

        sale_details.append(sale)

    # --- Add remaining unconsumed buys (after all sells) to the pool ---
    for b in buys:
        if b.id in consumed_buys:
            continue
        qty = b.quantity or 0.0
        cost = b.cost_proceeds_gbp or 0.0
        pool.quantity += qty
        pool.cost += cost

    return sale_details


@dataclass
class TaxYearSummary:
    """Summary for one UK tax year."""

    tax_year: str  # e.g. "2023-24"
    year_end: int
    total_proceeds: float = 0.0
    total_cost: float = 0.0
    total_gain: float = 0.0
    total_loss: float = 0.0
    gain_count: int = 0
    loss_count: int = 0
    sales: list[SaleDetail] = field(default_factory=list)


def _group_by_tax_year(sale_details: list[SaleDetail]) -> list[TaxYearSummary]:
    """Group sale details into UK tax years."""
    by_year: dict[int, TaxYearSummary] = {}
    for sale in sale_details:
        year_end = _tax_year_end(dt.datetime.fromisoformat(sale.order_date))
        if year_end in by_year:
            existing = by_year[year_end]
            existing.total_proceeds += sale.total_proceeds
            existing.total_cost += sale.total_cost
            gain = sale.total_proceeds - sale.total_cost
            if gain > 0:
                existing.total_gain += gain
                existing.gain_count += 1
            else:
                existing.total_loss += abs(gain)
                existing.loss_count += 1
            existing.sales.append(sale)
        else:
            gain = sale.total_proceeds - sale.total_cost
            by_year[year_end] = TaxYearSummary(
                tax_year=f"{year_end-1}-{str(year_end)[2:]}",
                year_end=year_end,
                total_proceeds=sale.total_proceeds,
                total_cost=sale.total_cost,
                total_gain=max(gain, 0),
                total_loss=max(-gain, 0),
                gain_count=1 if gain > 0 else 0,
                loss_count=1 if gain <= 0 else 0,
                sales=[sale],
            )

    return sorted(by_year.values(), key=lambda x: x.year_end)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def get_instrument_cgt(
    session: AsyncSession,
    *,
    account_name: str | None = None,
    instrument_id: int | None = None,
) -> list[dict]:
    """Per-instrument CGT summary: total gains/losses, by tax year.

    When *instrument_id* is given, returns details for just that instrument.
    When *account_name* is given, filters to instruments in that account.
    """
    q = select(Instrument).where(Instrument.is_cash.is_(False))
    if account_name:
        q = q.where(Instrument.account_name == account_name)
    if instrument_id:
        q = q.where(Instrument.id == instrument_id)
    instruments_result = await session.execute(q)
    instruments = list(instruments_result.scalars().all())

    if not instruments:
        return []

    out: list[dict] = []
    for inst in instruments:
        oq = select(Order).where(
            Order.instrument_id == inst.id,
            func.lower(Order.side).in_(["buy", "sell"]),
        ).order_by(Order.order_date)
        orders_result = await session.execute(oq)
        orders = list(orders_result.scalars().all())

        if not orders:
            continue

        sale_details = calculate_cgt_for_instrument(orders)
        tax_years = _group_by_tax_year(sale_details)

        # Aggregate totals
        total_gain = sum(ty.total_gain for ty in tax_years)
        total_loss = sum(ty.total_loss for ty in tax_years)
        total_proceeds = sum(ty.total_proceeds for ty in tax_years)
        total_cost = sum(ty.total_cost for ty in tax_years)

        out.append(
            {
                "instrument_id": inst.id,
                "security_name": inst.security_name,
                "identifier": inst.identifier,
                "account_name": inst.account_name,
                "total_proceeds_gbp": round(total_proceeds, 2),
                "total_cost_gbp": round(total_cost, 2),
                "total_gain_gbp": round(total_gain, 2),
                "total_loss_gbp": round(total_loss, 2),
                "net_gain_gbp": round(total_gain - total_loss, 2),
                "tax_year_summaries": [
                    {
                        "tax_year": ty.tax_year,
                        "year_end": ty.year_end,
                        "total_proceeds": round(ty.total_proceeds, 2),
                        "total_cost": round(ty.total_cost, 2),
                        "total_gain": round(ty.total_gain, 2),
                        "total_loss": round(ty.total_loss, 2),
                        "gain_count": ty.gain_count,
                        "loss_count": ty.loss_count,
                    }
                    for ty in tax_years
                ],
                "sales": [
                    {
                        "order_id": s.order_id,
                        "order_date": s.order_date,
                        "quantity": s.quantity,
                        "proceeds_gbp": round(s.proceeds_gbp, 2),
                        "total_cost": round(s.total_cost, 2),
                        "realised_gain": round(s.realised_gain, 2),
                        "matches": [
                            {
                                "source": m.source,
                                "order_id": m.order_id,
                                "order_date": m.order_date,
                                "security_name": m.security_name,
                                "quantity": m.quantity,
                                "cost": m.cost,
                                "proceeds": m.proceeds,
                            }
                            for m in s.matches
                        ],
                        "pool_quantity_before": s.pool_quantity_before,
                        "pool_cost_before": s.pool_cost_before,
                    }
                    for s in sale_details
                ],
            }
        )

    out.sort(key=lambda x: x["security_name"])
    return out


async def get_cgt_summary(
    session: AsyncSession,
    *,
    account_name: str | None = None,
) -> dict:
    """Aggregated CGT summary across all instruments, grouped by tax year.

    Returns the same structure as get_instrument_cgt but flattened across
    instruments with a tax_year_totals section.
    """
    instruments_data = await get_instrument_cgt(session, account_name=account_name)
    if not instruments_data:
        return {"instruments": [], "tax_year_totals": []}

    # Aggregate by tax year across instruments
    ty_totals: dict[str, dict] = {}
    for inst in instruments_data:
        for ty in inst["tax_year_summaries"]:
            key = ty["tax_year"]
            if key not in ty_totals:
                ty_totals[key] = {
                    "tax_year": key,
                    "total_proceeds": 0.0,
                    "total_cost": 0.0,
                    "total_gain": 0.0,
                    "total_loss": 0.0,
                    "gain_count": 0,
                    "loss_count": 0,
                    "instrument_count": 0,
                }
            ty_totals[key]["total_proceeds"] += ty["total_proceeds"]
            ty_totals[key]["total_cost"] += ty["total_cost"]
            ty_totals[key]["total_gain"] += ty["total_gain"]
            ty_totals[key]["total_loss"] += ty["total_loss"]
            ty_totals[key]["gain_count"] += ty["gain_count"]
            ty_totals[key]["loss_count"] += ty["loss_count"]
            ty_totals[key]["instrument_count"] += 1

    return {
        "instruments": instruments_data,
        "tax_year_totals": sorted(ty_totals.values(), key=lambda x: x["tax_year"]),
    }

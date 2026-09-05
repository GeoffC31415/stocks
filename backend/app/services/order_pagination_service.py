"""One SQL statement gives count, totals and rows a common read snapshot.

Offset pagination is stable for unchanged data (date DESC, ID DESC); concurrent
imports between page requests can shift offsets. No cross-request snapshot token.
Stored import-time reinvestment classification is authoritative; the threshold
parameter is retained for compatibility and does not reclassify old orders.
"""

import datetime as dt
import math
import sys
from typing import Literal

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.elements import ColumnElement

from app.models import Instrument, InstrumentGroupMember, Order
from app.order_page_schemas import (
    AmountReason,
    OrderPage,
    OrderPageItem,
    OrderPageTotalReasons,
    OrderPageTotals,
)
from app.services.order_scope_service import order_account_scope


def drip_predicate(threshold: float) -> ColumnElement[bool]:
    return and_(
        func.lower(Order.side) == "buy",
        Order.is_drip.is_(True),
    )


async def get_order_page(
    session: AsyncSession,
    *,
    search: str = "",
    kind: Literal["all", "buy", "sell", "drip"] = "all",
    account_name: str | None = None,
    from_date: dt.date | None = None,
    to_date: dt.date | None = None,
    instrument_ids: list[int] | None = None,
    group_ids: list[int] | None = None,
    offset: int = 0,
    limit: int = 100,
    drip_threshold: float = 1000,
) -> OrderPage:
    drip = and_(func.lower(Order.side) == "buy", Order.is_drip.is_(True))
    buy = and_(func.lower(Order.side) == "buy", ~drip)
    sell = func.lower(Order.side) == "sell"
    predicates = []
    if kind != "all":
        predicates.append({"buy": buy, "sell": sell, "drip": drip}[kind])
    if account_name is not None:
        predicates.append(order_account_scope(account_name))
    if from_date:
        predicates.append(Order.order_date >= dt.datetime.combine(from_date, dt.time.min))
    if to_date:
        predicates.append(Order.order_date <= dt.datetime.combine(to_date, dt.time.max))
    if instrument_ids:
        predicates.append(Order.instrument_id.in_(instrument_ids))
    if group_ids:
        predicates.append(
            Order.instrument_id.in_(
                select(InstrumentGroupMember.instrument_id).where(
                    InstrumentGroupMember.group_id.in_(group_ids)
                )
            )
        )
    if search.strip():
        value = search.strip()
        predicates.append(
            or_(
                Order.security_name.icontains(value, autoescape=True),
                Order.instrument.has(
                    or_(
                        Instrument.security_name.icontains(value, autoescape=True),
                        Instrument.ticker.icontains(value, autoescape=True),
                        Instrument.identifier.icontains(value, autoescape=True),
                    )
                ),
            )
        )

    finite = and_(
        Order.cost_proceeds_gbp >= -sys.float_info.max,
        Order.cost_proceeds_gbp <= sys.float_info.max,
    )

    def total_columns(predicate: ColumnElement[bool], key: str):
        missing = func.sum(case((and_(predicate, Order.cost_proceeds_gbp.is_(None)), 1), else_=0))
        invalid = func.sum(
            case((and_(predicate, Order.cost_proceeds_gbp.is_not(None), ~finite), 1), else_=0)
        )
        # Never feed infinities to SUM: opposite infinities can otherwise become
        # SQL NULL and COALESCE would misleadingly turn that into zero.
        amount = func.coalesce(
            func.sum(case((and_(predicate, finite), Order.cost_proceeds_gbp), else_=0)), 0
        )
        return [amount.label(key), missing.label(key + "_missing"), invalid.label(key + "_invalid")]

    summary = (
        select(
            func.count(Order.id).label("total_count"),
            *total_columns(buy, "buy_gbp"),
            *total_columns(sell, "sell_gbp"),
            *total_columns(drip, "drip_gbp"),
        )
        .where(*predicates)
        .subquery()
    )
    page_ids = (
        select(Order.id)
        .where(*predicates)
        .order_by(Order.order_date.desc(), Order.id.desc())
        .offset(offset)
        .limit(limit)
    )
    query = (
        select(Order, summary)
        .select_from(summary)
        .outerjoin(Order, Order.id.in_(page_ids))
        .options(joinedload(Order.instrument))
        .order_by(Order.order_date.desc(), Order.id.desc())
    )
    rows = (await session.execute(query)).unique().all()
    metadata = rows[0]._mapping
    items = []
    for row in rows:
        order = row[0]
        if order is not None:
            item = OrderPageItem.model_validate(order)
            if item.cost_proceeds_gbp is None:
                item.cost_proceeds_gbp_reason = "missing_amounts"
            elif not math.isfinite(item.cost_proceeds_gbp):
                item.cost_proceeds_gbp = None
                item.cost_proceeds_gbp_reason = "non_finite_amounts"
            item.is_drip = order.side.lower() == "buy" and order.is_drip
            items.append(item)
    totals: dict[str, float | None] = {}
    reasons: dict[str, AmountReason | None] = {}
    for key in ("buy_gbp", "sell_gbp", "drip_gbp"):
        value = metadata[key]
        reason: AmountReason | None = None
        if metadata[key + "_invalid"]:
            reason = "non_finite_amounts"
        elif metadata[key + "_missing"]:
            reason = "missing_amounts"
        elif value is None or not math.isfinite(value):
            reason = "non_finite_total"
        totals[key] = None if reason else value
        reasons[key] = reason
    count = metadata["total_count"]
    return OrderPage(
        items=items,
        total_count=count,
        offset=offset,
        limit=limit,
        has_more=offset + len(items) < count,
        totals_reasons=OrderPageTotalReasons(**reasons),
        totals=OrderPageTotals(**totals),
    )

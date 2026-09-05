"""Calendar-matched recorded purchase proxy. No dividend or completeness inference."""

import calendar
import datetime as dt
import math
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.income_schemas import IncomeAnalysis, IncomeDriver, IncomeMonth
from app.models import Order
from app.services.order_scope_service import order_account_scope
from app.services.portfolio_service import get_current_snapshots


def recorded_total(orders: list[Order]) -> float | None:
    if any(
        o.cost_proceeds_gbp is None
        or not math.isfinite(o.cost_proceeds_gbp)
        or o.cost_proceeds_gbp < 0
        for o in orders
    ):
        return None
    value = sum(o.cost_proceeds_gbp or 0 for o in orders)
    return value if math.isfinite(value) else None


async def get_income_analysis(
    session: AsyncSession, *, account_name: str | None = None, as_of: dt.date | None = None
) -> IncomeAnalysis:
    end = as_of or dt.datetime.now(dt.UTC).date()
    start = dt.date(end.year, 1, 1)
    prior_start = dt.date(end.year - 1, 1, 1)
    prior_end = dt.date(
        end.year - 1, end.month, min(end.day, calendar.monthrange(end.year - 1, end.month)[1])
    )
    query = (
        select(Order).options(joinedload(Order.instrument))
        .where(Order.order_date < dt.datetime.combine(end + dt.timedelta(days=1), dt.time()))
        .order_by(Order.order_date, Order.id)
    )
    if account_name is not None:
        query = query.where(order_account_scope(account_name))
    orders = list((await session.scalars(query)).all())
    proxy = [o for o in orders if o.is_drip and o.side.lower() == "buy"]
    current = [o for o in proxy if start <= o.order_date.date() <= end]
    prior = [o for o in proxy if prior_start <= o.order_date.date() <= prior_end]
    snapshots = await get_current_snapshots(session)
    active = {s.instrument_id for s in snapshots if not s.instrument.is_cash}
    groups: dict[str, list[Order]] = defaultdict(list)
    for o in current + prior:
        groups[
            f"instrument:{o.instrument_id}"
            if o.instrument_id is not None
            else f"unlinked-order:{o.id}"
        ].append(o)
    drivers = []
    for key, rows in sorted(groups.items()):
        latest = rows[-1]
        c = recorded_total([o for o in rows if start <= o.order_date.date() <= end])
        p = recorded_total([o for o in rows if prior_start <= o.order_date.date() <= prior_end])
        drivers.append(
            IncomeDriver(
                key=key,
                instrument_id=latest.instrument_id,
                account_name=latest.account_name,
                navigation_account=latest.instrument.account_name if latest.instrument else "all",
                name=latest.security_name,
                holding_status="unlinked"
                if latest.instrument_id is None
                else "current"
                if latest.instrument_id in active
                else "closed",
                current_recorded_gbp=c,
                prior_recorded_gbp=p,
                change_gbp=c - p if c is not None and p is not None else None,
                order_ids=sorted(o.id for o in rows),
            )
        )
    c, p = recorded_total(current), recorded_total(prior)
    months = []
    for month in range(1, end.month + 1):
        cr = [o for o in current if o.order_date.month == month]
        pr = [o for o in prior if o.order_date.month == month]
        months.append(
            IncomeMonth(
                month=month,
                current_recorded_gbp=recorded_total(cr) if cr else None,
                prior_recorded_gbp=recorded_total(pr) if pr else None,
                current_count=len(cr),
                prior_count=len(pr),
            )
        )
    warnings = [
        "Reinvestment proxy, not a dividend ledger. Stored import-time classifications are used; today's threshold does not reclassify purchases.",
        "Transaction completeness is unknown. Unrecorded months are not confirmed zero income; totals describe recorded purchases only.",
        "Today-based calendar year to date versus the same calendar period last year; independent of the historical performance period. Leap-day comparison clamps to 28 February when needed.",
    ]
    if not current:
        warnings.append(
            "No reinvestment-proxy purchases recorded in the current comparison window; this does not prove no income."
        )
    if orders and orders[-1].order_date.date() < end:
        warnings.append(
            "Latest recorded transaction precedes the comparison end; newer transactions may be missing."
        )
    if c is None or p is None:
        warnings.append(
            "Missing, negative or non-finite purchase amounts block complete totals and change."
        )
    return IncomeAnalysis(
        account_name=account_name,
        as_of=end,
        current_start=start,
        prior_start=prior_start,
        prior_end=prior_end,
        first_transaction_date=orders[0].order_date.date() if orders else None,
        latest_transaction_date=orders[-1].order_date.date() if orders else None,
        current_recorded_gbp=c,
        prior_recorded_gbp=p,
        change_gbp=c - p if c is not None and p is not None else None,
        current_count=len(current),
        prior_count=len(prior),
        warnings=warnings,
        months=months,
        drivers=drivers,
    )

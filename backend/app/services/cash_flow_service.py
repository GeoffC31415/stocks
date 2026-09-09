"""Account-level funding: use verified cash history instead of trade proxies."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import and_, func, or_, select

from app.models import (
    CashFlowCoverage,
    ExternalCashFlow,
    HoldingSnapshot,
    ImportBatch,
    Instrument,
    Order,
)
from app.services.order_scope_service import order_account_scope

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class CashFlowCoverageError(ValueError):
    pass


@dataclass
class ExternalFlows:
    contributions: float
    withdrawals: float
    signed_flows: list[tuple[dt.date, float]]
    ledger_accounts: set[str]
    notes: list[str]


async def external_flows_for_period(
    session: AsyncSession,
    *,
    start: dt.date,
    end: dt.date,
    account_name: str | None = None,
    through_batch: ImportBatch | None = None,
) -> ExternalFlows:
    # Local import avoids the portfolio-service import cycle.
    from app.services.portfolio_service import classify_external_flows

    coverage_query = select(CashFlowCoverage)
    if account_name is not None:
        coverage_query = coverage_query.where(CashFlowCoverage.account_name == account_name)
    else:
        coverage_query = coverage_query.where(
            CashFlowCoverage.account_name.in_(select(Instrument.account_name))
        )
    coverage = list((await session.scalars(coverage_query)).all())
    closing_cutoffs: dict[str, dt.datetime] = {}
    for row in coverage:
        batch_query = (
            select(ImportBatch)
            .join(HoldingSnapshot)
            .join(Instrument)
            .where(Instrument.account_name == row.account_name, ImportBatch.as_of_date <= end)
            .order_by(ImportBatch.as_of_date.desc(), ImportBatch.id.desc())
        )
        if through_batch is not None:
            batch_query = batch_query.where(
                or_(
                    ImportBatch.as_of_date < through_batch.as_of_date,
                    and_(
                        ImportBatch.as_of_date == through_batch.as_of_date,
                        ImportBatch.id <= through_batch.id,
                    ),
                )
            )
        batch = await session.scalar(batch_query.limit(1))
        cutoff = dt.datetime.combine(end, dt.time.max)
        if batch is not None:
            cutoff = dt.datetime.combine(batch.as_of_date, dt.time.max)
            if (
                batch.filename == "trading212-api-portfolio.json"
                and batch.created_at.date() == batch.as_of_date
            ):
                cutoff = batch.created_at.replace(tzinfo=None)
        closing_cutoffs[row.account_name] = cutoff
        if row.fetched_at.replace(tzinfo=None) < cutoff:
            raise CashFlowCoverageError(
                "Cash history does not cover the closing snapshot time; sync cash flows again."
            )
    accounts = {row.account_name for row in coverage}
    query = (
        select(Order, func.coalesce(Instrument.account_name, Order.account_name))
        .outerjoin(Instrument, Instrument.id == Order.instrument_id)
        .where(
            Order.order_date > dt.datetime.combine(start, dt.time.max),
            Order.order_date <= dt.datetime.combine(end, dt.time.max),
        )
    )
    if account_name is not None:
        query = query.where(order_account_scope(account_name))
    orders = [
        order
        for order, effective_account in (await session.execute(query)).all()
        if effective_account not in accounts
    ]
    contributions, withdrawals, signed_flows = classify_external_flows(orders)
    cash_query = select(ExternalCashFlow).where(
        ExternalCashFlow.account_name.in_(accounts),
        ExternalCashFlow.occurred_at > dt.datetime.combine(start, dt.time.max),
        ExternalCashFlow.occurred_at <= dt.datetime.combine(end, dt.time.max),
    )
    for cash_event in (await session.scalars(cash_query)).all():
        if cash_event.occurred_at.replace(tzinfo=None) > closing_cutoffs[cash_event.account_name]:
            continue
        signed_flows.append((cash_event.occurred_at.date(), cash_event.amount_gbp))
        if cash_event.amount_gbp > 0:
            contributions += cash_event.amount_gbp
        else:
            withdrawals -= cash_event.amount_gbp
    notes = [
        "Accounts with synced cash history use API deposits less withdrawals; purchases and sales are internal and are not counted again.",
        "Accounts without synced cash history retain buy/sell contribution/withdrawal proxies; these are not verified external cash movements.",
        "Opening-date cash flows are assumed included in the opening valuation. API closing snapshots use their recorded observation time; file snapshots use end of day. Cash history must cover that cutoff.",
    ]
    return ExternalFlows(contributions, withdrawals, sorted(signed_flows), accounts, notes)

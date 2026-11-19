"""Account-level funding: use verified cash history instead of trade proxies."""

from __future__ import annotations

import datetime as dt
from bisect import bisect_left
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import and_, func, or_, select

from app.models import (
    AccountAlias,
    CashFlowCoverage,
    ExternalCashFlow,
    HoldingSnapshot,
    ImportBatch,
    Instrument,
    Order,
    OrderImportBatch,
)
from app.services.order_scope_service import order_account_scope
from app.services.trading212_valuation import (
    PORTFOLIO_FILENAME,
    ValuationObservation,
    ledger_scope,
    utc,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

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
    # Ranges of valuation dates [cash event, first observation reflecting it)
    # that an adjusted curve must bridge. Never shift the date of a cash flow.
    unaligned_spans: set[tuple[dt.date, dt.date]] = field(default_factory=set)


async def _boundary_batches(
    session: AsyncSession,
    canonical: str,
    start: dt.date,
    end: dt.date,
    opening_batch: ImportBatch | None,
    through_batch: ImportBatch | None,
    daily: bool,
) -> Sequence[ImportBatch]:
    # Select the same daily correction IDs as valuation reconstruction. Only
    # the chain-linked curve consumes intermediate points.
    ids = (
        select(func.max(ImportBatch.id))
        .select_from(ImportBatch)
        .join(HoldingSnapshot)
        .join(Instrument)
        .where(Instrument.account_name == canonical)
        .group_by(ImportBatch.as_of_date)
    )

    def boundary(day: dt.date, selected: ImportBatch | None, *, first: bool = False):
        q = ids.where(ImportBatch.as_of_date <= day)
        if selected is not None:
            q = q.where(
                or_(
                    ImportBatch.as_of_date < selected.as_of_date,
                    and_(
                        ImportBatch.as_of_date == selected.as_of_date, ImportBatch.id <= selected.id
                    ),
                )
            )
        order = ImportBatch.as_of_date if first else ImportBatch.as_of_date.desc()
        return q.order_by(order).limit(1).correlate(None).scalar_subquery()

    # If the account isn't in the opening state, its first selected daily
    # valuation is the scope baseline, even for an endpoint-only return.
    wanted = [
        ImportBatch.id
        == func.coalesce(boundary(start, opening_batch), boundary(end, through_batch, first=True)),
        ImportBatch.id == boundary(end, through_batch),
    ]
    if daily:
        wanted.append(
            ImportBatch.id.in_(
                ids.where(ImportBatch.as_of_date > start, ImportBatch.as_of_date < end)
            )
        )
    return (
        await session.scalars(
            select(ImportBatch).where(or_(*wanted)).order_by(ImportBatch.as_of_date, ImportBatch.id)
        )
    ).all()


async def external_flows_for_period(
    session: AsyncSession,
    *,
    start: dt.date,
    end: dt.date,
    account_name: str | None = None,
    through_batch: ImportBatch | None = None,
    opening_batch: ImportBatch | None = None,
    daily: bool = False,
) -> ExternalFlows:
    # Local import avoids the portfolio-service import cycle.
    from app.services.portfolio_service import classify_external_flows

    coverage = {r.account_name: r for r in (await session.scalars(select(CashFlowCoverage))).all()}
    t212_ledgers = {ledger_scope(k): r for k, r in coverage.items() if r.source == "trading212"}
    holding_accounts = set(
        (await session.scalars(select(Instrument.account_name).distinct())).all()
    )
    opening_cutoffs: dict[str, dt.datetime] = {}
    closing_cutoffs: dict[str, dt.datetime] = {}
    daily_cutoffs: dict[str, list[dt.datetime]] = {}
    worker_windows: dict[tuple[str, dt.date], ValuationObservation] = {}
    accounts: set[str] = set()
    for canonical in {account_name} if account_name is not None else holding_accounts:
        row = coverage.get(canonical)
        verified_alias = False
        batches = await _boundary_batches(
            session, canonical, start, end, opening_batch, through_batch, daily
        )
        if not batches:
            if row is not None:
                accounts.add(row.account_name)  # Still suppress this ledger's trade proxies.
            continue  # No selected valuation for this account by the closing boundary.
        cutoffs: dict[dt.date, dt.datetime] = {}
        for batch in batches:
            cutoff = dt.datetime.combine(batch.as_of_date, dt.time.max, dt.UTC)
            try:
                observation = ValuationObservation.from_batch(batch)
            except ValueError as exc:
                raise CashFlowCoverageError(
                    "Unusable Trading 212 valuation timing evidence."
                ) from exc
            if observation is not None:
                # Holdings may be canonicalized, whereas historical ledgers keep
                # their source key. Neither rewrite those rows nor guess an owner.
                bound = t212_ledgers.get(observation.ledger_scope_sha256)
                if bound is None or (row is not None and row is not bound):
                    raise CashFlowCoverageError("Missing or conflicting Trading 212 ledger scope.")
                row = bound
                if row.account_name != canonical and not verified_alias:
                    aliases = (
                        await session.scalars(
                            select(AccountAlias.canonical_account_name).where(
                                AccountAlias.source_account_name == row.account_name
                            )
                        )
                    ).all()
                    if aliases != [canonical] or row.account_name in holding_accounts:
                        raise CashFlowCoverageError("Ambiguous Trading 212 ledger account alias.")
                    verified_alias = True
                cutoff = observation.account_summary_received_at
                worker_windows[row.account_name, batch.as_of_date] = observation
            else:
                if verified_alias:
                    raise CashFlowCoverageError(
                        "The selected valuation has no matching ledger scope evidence."
                    )
                if (
                    batch.filename == PORTFOLIO_FILENAME
                    and utc(batch.created_at).date() == batch.as_of_date
                ):
                    cutoff = utc(batch.created_at)
            cutoffs[batch.as_of_date] = cutoff
        if row is None:
            continue
        accounts.update((canonical, row.account_name))
        opening_cutoffs[row.account_name] = cutoffs[batches[0].as_of_date]
        cutoff = cutoffs[batches[-1].as_of_date]
        closing_cutoffs[row.account_name] = cutoff
        if daily:
            daily_cutoffs[row.account_name] = sorted(cutoffs.values())
        if utc(row.fetched_at) < cutoff:
            raise CashFlowCoverageError(
                "Cash history does not cover the closing snapshot time; sync cash flows again."
            )

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
    if worker_windows:
        # A fill between positions and cash can also make the combined value
        # inconsistent. This is not an external flow. Use the original order
        # account/filename, independent of any subsequent instrument linking.
        fills = (
            select(Order.account_name, Order.order_date)
            .join(OrderImportBatch)
            .where(
                OrderImportBatch.filename == "trading212-api-orders.json",
                Order.account_name.in_({name for name, _ in worker_windows}),
                Order.order_date.between(
                    min(w.positions_requested_at for w in worker_windows.values()),
                    max(w.account_summary_received_at for w in worker_windows.values()),
                ),
            )
        )
        for name, timestamp in await session.execute(fills):
            when = utc(timestamp)
            w = worker_windows.get((name, when.date()))
            if w and w.positions_requested_at <= when <= w.account_summary_received_at:
                raise CashFlowCoverageError(
                    "A trade overlaps the separate Trading 212 valuation requests."
                )
    opening_eod = dt.datetime.combine(start, dt.time.max, dt.UTC)
    # A carried opening can predate the aggregate window. Inspect cash since
    # that valuation, not just cash since the aggregate opening date.
    cash_query = select(ExternalCashFlow).where(
        ExternalCashFlow.account_name.in_(closing_cutoffs),
        ExternalCashFlow.occurred_at
        >= min(
            [
                opening_eod,
                *opening_cutoffs.values(),
                *(w.positions_requested_at for w in worker_windows.values()),
            ]
        ),
        ExternalCashFlow.occurred_at <= dt.datetime.combine(end, dt.time.max),
    )
    unaligned_spans: set[tuple[dt.date, dt.date]] = set()
    for cash_event in (await session.scalars(cash_query)).all():
        occurred = utc(cash_event.occurred_at)
        window = worker_windows.get((cash_event.account_name, occurred.date()))
        if (
            window
            and window.positions_requested_at <= occurred <= window.account_summary_received_at
        ):
            raise CashFlowCoverageError(
                "Cash moved during separate Trading 212 valuation requests."
            )
        cutoff = closing_cutoffs[cash_event.account_name]
        opening = opening_cutoffs[cash_event.account_name]
        late_join = account_name is None and opening.date() > start
        if late_join and occurred <= opening:
            continue  # The caller already adds the account's first value as funding.
        if occurred > cutoff:
            continue
        if opening.date() < start and opening < occurred <= opening_eod:
            raise CashFlowCoverageError("Cash moved after the valuation carried into the opening.")
        if opening < occurred <= opening_eod:
            # Date-only weighting cannot put a cash movement after the opening
            # valuation on its own start date. Preserve the requested boundary.
            raise CashFlowCoverageError(
                "A same-day cash movement follows an intraday Trading 212 valuation."
            )
        if occurred <= opening_eod:
            continue
        event_day = occurred.date()
        if daily:
            cutoffs_for_account = daily_cutoffs[cash_event.account_name]
            # The closing cutoff above already passed. A same-day snapshot
            # can precede the event, and other accounts can produce points
            # while this account's old balance is carried forward.
            reflected_day = cutoffs_for_account[bisect_left(cutoffs_for_account, occurred)].date()
            if event_day < reflected_day:
                unaligned_spans.add((event_day, reflected_day))
        signed_flows.append((event_day, cash_event.amount_gbp))
        if cash_event.amount_gbp > 0:
            contributions += cash_event.amount_gbp
        else:
            withdrawals -= cash_event.amount_gbp
    notes = [
        "Accounts with synced cash history use API deposits less withdrawals; purchases and sales are internal and are not counted again.",
        "Accounts without synced cash history retain buy/sell contribution/withdrawal proxies; these are not verified external cash movements.",
        "Opening-date cash flows are assumed included in the opening valuation. API closing snapshots use their recorded observation time; file snapshots use end of day. Cash history must cover that cutoff.",
    ]
    if worker_windows:
        notes.append(
            "Worker valuation timing bounds the separate positions and account-summary requests; it is not a broker as-of time."
        )
    return ExternalFlows(
        contributions, withdrawals, sorted(signed_flows), accounts, notes, unaligned_spans
    )

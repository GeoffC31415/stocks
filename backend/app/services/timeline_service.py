"""Recorded events only. A buy/sell is a trade, never proof of a deposit/withdrawal."""
import datetime as dt
import math
from collections import Counter, defaultdict
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import HoldingSnapshot, ImportBatch, Instrument, Order, OrderImportBatch
from app.services.performance_service import build_value_series, resolve_period_start

NOTES = [
    "Events provide context, not proof that a transaction caused a market movement.",
    "Deposits and withdrawals require explicit stored transaction types; buys and sells remain trades.",
    "Snapshot markers use valuation dates. Import markers use file import timestamps and may lie outside the covered performance window.",
]


def _source_href(source: str, record_id: int, account: str | None, period: str) -> str:
    return "/activity?" + urlencode({"tab": "source", "source": source, "record": record_id,
                                    "account": account or "all", "period": period})


def order_event(order: Order, account: str | None, period: str) -> dict:
    side = order.side.lower()
    kind = side if side in {"deposit", "withdrawal"} else "trade" if side in {"buy", "sell"} else "transaction"
    amount = order.cost_proceeds_gbp
    return {
        "id": f"order:{order.id}", "kind": kind, "date": order.order_date.date(), "occurred_at": order.order_date,
        "valuation_date": None, "account_names": [order.account_name], "instrument_id": order.instrument_id,
        "title": f"{order.side} ({order.order_status}): {order.security_name}", "amount_gbp": amount if amount is not None and math.isfinite(amount) else None,
        "source_type": "order", "source_id": order.id, "source_href": _source_href("order", order.id, account, period),
        "details": {"Original security name": order.security_name, "Side": order.side, "Status": order.order_status,
                    "Quantity": str(order.quantity) if order.quantity is not None else None,
                    "Source order import": str(order.order_import_batch_id), "Matching status": order.match_status},
        "note": "Recorded transaction; a reinvestment flag is a proxy, not a dividend ledger." if order.is_drip else "Recorded transaction, not a causal explanation of portfolio movement.",
    }


def import_event(batch: ImportBatch | OrderImportBatch, accounts: list[str], account: str | None, period: str, *, snapshot: bool = False) -> dict:
    kind = "snapshot" if snapshot else "import"
    source = "import" if isinstance(batch, ImportBatch) else "order-import"
    valuation_date = batch.as_of_date if isinstance(batch, ImportBatch) else None
    if snapshot and valuation_date is None:
        raise ValueError("Transaction imports cannot create snapshot valuation events")
    return {
        "id": f"{'snapshot' if snapshot else source}:{batch.id}", "kind": kind, "date": valuation_date if snapshot else batch.created_at.date(),
        "occurred_at": None if snapshot else batch.created_at, "valuation_date": valuation_date,
        "account_names": accounts, "instrument_id": None,
        "title": "Snapshot valuation" if snapshot else "Snapshot file imported" if source == "import" else "Transactions file imported",
        "amount_gbp": None, "source_type": source, "source_id": batch.id,
        "source_href": _source_href(source, batch.id, account, period),
        "details": {"Filename": batch.filename, "File SHA-256": batch.file_sha256},
        "note": "A valuation observation, not an economic transaction." if snapshot else "Import time is an administrative event, not a trade or valuation date.",
    }


async def _batch_memberships(session: AsyncSession) -> dict[int, dict[int, str]]:
    rows = (await session.execute(select(HoldingSnapshot.import_batch_id, Instrument.id, Instrument.account_name)
                                  .join(Instrument, Instrument.id == HoldingSnapshot.instrument_id))).all()
    memberships: dict[int, dict[int, str]] = defaultdict(dict)
    for batch, instrument, account in rows:
        memberships[batch][instrument] = account
    # Closure-only imports still have real instrument/account source identities.
    instruments = dict((await session.execute(select(Instrument.id, Instrument.account_name))).tuples().all())
    batches = (await session.scalars(select(ImportBatch))).all()
    for batch in batches:
        for closed in (batch.diff_summary or {}).get("closed", []):
            instrument = closed.get("instrument_id")
            if instrument in instruments:
                memberships[batch.id][instrument] = instruments[instrument]
    return memberships


async def _order_batch_memberships(session: AsyncSession) -> dict[int, list[tuple[int | None, str]]]:
    memberships: dict[int, list[tuple[int | None, str]]] = defaultdict(list)
    for batch, instrument, account in (await session.execute(select(Order.order_import_batch_id, Order.instrument_id, Order.account_name))).all():
        memberships[batch].append((instrument, account))
    return memberships


async def get_timeline(
    session: AsyncSession, *, account_name: str | None = None, period: str = "ALL", instrument_id: int | None = None,
) -> dict:
    series, coverage_start = await build_value_series(session, account_name=account_name)
    end = series[-1]["as_of_date"] if series else None
    requested_start = resolve_period_start(period, end) if end else None
    start = max(filter(None, [requested_start, coverage_start]), default=None)
    window = [row for row in series if start is None or row["as_of_date"] >= start]
    effective_start = window[0]["as_of_date"] if window else None
    scope = {"account_name": account_name, "requested_start": requested_start, "requested_end": None,
             "effective_start": effective_start, "effective_end": end,
             "valuation_dates": series[-1].get("valuation_dates", []) if series else [], "warnings": []}
    if len({row["date"] for row in scope["valuation_dates"]}) > 1:
        scope["warnings"].append("Account valuation dates differ; some snapshots are carried forward.")
    if coverage_start is not None:
        scope["warnings"].append("The event window begins only once every selected account has snapshot coverage.")
    events: list[dict] = []
    if effective_start is not None and end is not None:
        query = select(Order).where(Order.order_date >= dt.datetime.combine(effective_start, dt.time.min),
                                    Order.order_date <= dt.datetime.combine(end, dt.time.max))
        if account_name is not None:
            query = query.where(Order.account_name == account_name)
        if instrument_id is not None:
            query = query.where(Order.instrument_id == instrument_id)
        events.extend(order_event(order, account_name, period) for order in (await session.scalars(query.order_by(Order.order_date, Order.id))).all())
        memberships = await _batch_memberships(session)
        for batch in (await session.scalars(select(ImportBatch))).all():
            members = memberships.get(batch.id, {})
            if instrument_id is not None:
                members = {key: value for key, value in members.items() if key == instrument_id}
            accounts = sorted(set(members.values()))
            if not accounts or (account_name is not None and account_name not in accounts):
                continue
            for snapshot in (True, False):
                event = import_event(batch, accounts, account_name, period, snapshot=snapshot)
                if effective_start <= event["date"] <= end:
                    events.append(event)
        order_memberships = await _order_batch_memberships(session)
        for order_batch in (await session.scalars(select(OrderImportBatch))).all():
            accounts = sorted({account for instrument, account in order_memberships.get(order_batch.id, [])
                               if instrument_id is None or instrument == instrument_id})
            if not accounts or (account_name is not None and account_name not in accounts):
                continue
            event = import_event(order_batch, accounts, account_name, period)
            if effective_start <= event["date"] <= end:
                events.append(event)
    events.sort(key=lambda event: (event["date"], event["id"]))
    return {"scope": scope, "events": events, "event_count": len(events),
            "counts_by_kind": dict(Counter(event["kind"] for event in events)), "notes": NOTES + scope["warnings"]}


async def get_timeline_source(session: AsyncSession, source: str, record_id: int, account_name: str | None = None) -> dict | None:
    if source not in {"order", "import", "order-import"}:
        return None
    if source == "order":
        order = await session.get(Order, record_id)
        if order is None or (account_name is not None and order.account_name != account_name):
            return None
        return order_event(order, account_name, "ALL")
    if source == "order-import":
        order_batch = await session.get(OrderImportBatch, record_id)
        if order_batch is None:
            return None
        accounts = sorted({account for _, account in (await _order_batch_memberships(session)).get(record_id, [])})
        if account_name is not None and account_name not in accounts:
            return None
        return import_event(order_batch, accounts, account_name, "ALL")
    batch = await session.get(ImportBatch, record_id)
    if batch is None:
        return None
    accounts = sorted(set((await _batch_memberships(session)).get(batch.id, {}).values()))
    if account_name is not None and account_name not in accounts:
        return None
    return import_event(batch, accounts, account_name, "ALL")

"""Atomic, fail-closed import of a Barclays holdings + order-history pair.

Used by the automated Barclays fetcher. Stricter than the manual upload path:

- Both files are validated completely *before* any database write. Any row the
  existing parsers would silently skip or half-read (missing identifier,
  unparseable quantity/value, non-finite numbers, undated or unsided completed
  orders, foreign account) rejects the whole pair.
- Holdings and orders are written in ONE transaction: a failure in the second
  half rolls back the first, so a snapshot is never recorded without the
  orders that explain it (and vice versa).
- A snapshot that would close more than a small number of positions not
  explained by sells in the order history is refused. A partial export must
  never be recorded as "you sold everything".
- Re-running with the same files is a no-op (hash dedupe per half).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import math
from dataclasses import dataclass
from typing import Any

from python_calamine import CalamineWorkbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002 - runtime annotations

from app.models import ImportBatch, OrderImportBatch
from app.services.barclays_order_parser import parse_barclays_order_xls_bytes
from app.services.barclays_parser import parse_barclays_xls_bytes
from app.services.import_service import import_holding_snapshot, resolve_account_name
from app.services.matching.normalisation import normalise_name
from app.services.order_service import ingest_parsed_orders
from app.services.portfolio_service import get_latest_batch_for_account

DRIP_THRESHOLD_GBP = 1000.0
# Positions that may disappear without a matching sell (e.g. a fund merger or a
# corporate action) before the import is held for review.
MAX_UNEXPLAINED_CLOSURES = 2


class BarclaysExportInvalid(ValueError):  # noqa: N818 - domain wording
    """The export pair is incomplete or malformed; nothing was written."""


@dataclass(frozen=True)
class PairResult:
    account_name: str
    holdings: str  # imported | unchanged
    orders: str  # imported | unchanged
    holding_rows: int
    new_orders: int
    closed: int


def _finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


def _table(data: bytes) -> list[tuple[str, list[list[Any]]]]:
    wb = CalamineWorkbook.from_filelike(io.BytesIO(data))
    return [(name, wb.get_sheet_by_name(name).to_python()) for name in wb.sheet_names]


def _raw_order_rows(data: bytes) -> list[dict[str, object]]:
    """Every non-blank row under the order header, independent of the parser."""
    out: list[dict[str, object]] = []
    for _, table in _table(data):
        for i, row in enumerate(table[:6]):
            cells = [str(c).strip().lower() if c is not None else "" for c in row]
            if "investment" in cells and "date" in cells:
                for raw in table[i + 1 :]:
                    if raw and any(c not in (None, "") for c in raw):
                        out.append(
                            {h: raw[j] if j < len(raw) else None for j, h in enumerate(cells)}
                        )
                break
    return out


def validate_pair(holdings_data: bytes, orders_data: bytes):
    rows, _ = parse_barclays_xls_bytes(holdings_data)
    accounts = {r.account_name for r in rows}
    if not rows:
        raise BarclaysExportInvalid("Holdings export has no holdings.")
    if len(accounts) != 1:
        raise BarclaysExportInvalid("Holdings export must cover exactly one account.")
    account = accounts.pop()
    securities = [r for r in rows if not r.is_cash]
    if not securities:
        raise BarclaysExportInvalid("Holdings export has no holdings.")
    # Rows the parser dropped (no investment name) would silently vanish.
    raw_count = 0
    for _, table in _table(holdings_data):
        for i, row in enumerate(table[:6]):
            cells = [str(c).strip().lower() if c is not None else "" for c in row]
            if "investment" in cells and "identifier" in cells:
                raw_count += sum(
                    1 for r in table[i + 1 :] if r and any(c not in (None, "") for c in r)
                )
                break
    if raw_count != len(rows):
        raise BarclaysExportInvalid("Holdings export has unreadable rows.")
    for r in rows:
        if not _finite(r.value_gbp):
            raise BarclaysExportInvalid("Holdings export has a row without a GBP value.")
        if r.is_cash:
            continue
        if not r.identifier or not _finite(r.quantity):
            raise BarclaysExportInvalid("Holdings export has an incomplete security row.")

    raw_orders = _raw_order_rows(orders_data)
    completed_raw = [
        r for r in raw_orders if str(r.get("order status") or "").strip().lower() == "completed"
    ]
    for r in completed_raw:
        if not isinstance(r.get("date"), dt.datetime):
            raise BarclaysExportInvalid("Order history has an undated completed order.")
        if str(r.get("buy/sell") or "").strip().lower() not in {"buy", "sell"}:
            raise BarclaysExportInvalid("Order history has an order without buy/sell.")
        cost = r.get("cost/proceeds")
        if not isinstance(cost, (int, float)) or not math.isfinite(float(cost)):
            raise BarclaysExportInvalid("Order history has an order without a value.")
    try:
        orders = parse_barclays_order_xls_bytes(orders_data, drip_threshold_gbp=DRIP_THRESHOLD_GBP)
    except (TypeError, ValueError) as exc:
        raise BarclaysExportInvalid("Order history could not be read.") from exc
    if len(orders) != len(completed_raw):
        raise BarclaysExportInvalid("Order history has unreadable completed orders.")
    # Holdings sheet "ID…-001 (Investment ISA)"; orders column "Investment ISA".
    for o in orders:
        if not o.account_name or f"({o.account_name})" not in account:
            raise BarclaysExportInvalid("Order history belongs to a different account.")
    return account, rows, orders


async def _hash_seen(session: AsyncSession, model: type, sha: str) -> bool:
    found = await session.execute(select(model.id).where(model.file_sha256 == sha).limit(1))
    return found.scalar_one_or_none() is not None


async def _guard_closures(session: AsyncSession, account: str, rows, orders) -> None:
    previous = await get_latest_batch_for_account(session, account)
    if previous is None:
        return
    from app.services.import_service import _snapshots_for_batch

    current = {r.identifier for r in rows}
    since = dt.datetime.combine(previous.as_of_date, dt.time.min, tzinfo=dt.UTC)
    sold = {
        normalise_name(o.security_name)
        for o in orders
        if o.side.lower() == "sell" and o.order_date >= since
    }
    unexplained = [
        s
        for s in await _snapshots_for_batch(session, previous.id)
        if s.instrument.account_name == account
        and s.instrument.identifier not in current
        and normalise_name(s.instrument.security_name) not in sold
        and normalise_name(s.investment_label or "") not in sold
    ]
    if len(unexplained) > MAX_UNEXPLAINED_CLOSURES:
        raise BarclaysExportInvalid(
            f"Snapshot would close {len(unexplained)} holdings with no matching sells; held for review."
        )


async def import_barclays_pair(
    session: AsyncSession,
    holdings_data: bytes,
    orders_data: bytes,
    *,
    as_of: dt.date,
    filename_prefix: str = "barclays-auto",
) -> PairResult:
    """Validate then import both halves in a single transaction."""
    account, rows, orders = validate_pair(holdings_data, orders_data)
    account = await resolve_account_name(session, account)
    h_sha = hashlib.sha256(holdings_data).hexdigest()
    o_sha = hashlib.sha256(orders_data).hexdigest()
    try:
        holdings_new = not await _hash_seen(session, ImportBatch, h_sha)
        orders_new = not await _hash_seen(session, OrderImportBatch, o_sha)
        new_orders = closed = 0
        # Orders first so sells are linked before the snapshot marks closures.
        if orders_new:
            _, new_orders = await ingest_parsed_orders(
                session,
                parsed=orders,
                file_bytes=orders_data,
                filename=f"{filename_prefix}-orders-{as_of.isoformat()}.xls",
                commit=False,
            )
        if holdings_new:
            await _guard_closures(session, account, rows, orders)
            _, summary = await import_holding_snapshot(
                session,
                parsed_rows=rows,
                as_of_date=as_of,
                filename=f"{filename_prefix}-holdings-{as_of.isoformat()}.xls",
                file_sha256=h_sha,
                commit=False,
            )
            closed = len(summary["closed"])
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    return PairResult(
        account_name=account,
        holdings="imported" if holdings_new else "unchanged",
        orders="imported" if orders_new else "unchanged",
        holding_rows=len(rows),
        new_orders=new_orders,
        closed=closed,
    )

"""Strict validation and transactional import of a single Barclays export pair.

Automated imports are stricter than the legacy manual upload parsers. Preserve
order account labels for legacy fingerprints; do not silently rewrite history.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import math
import re
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from python_calamine import CalamineWorkbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccountAlias, HoldingSnapshot, Instrument, OrderImportBatch
from app.services.barclays_order_parser import ParsedOrderRow, parse_barclays_order_xls_bytes
from app.services.barclays_parser import ParsedHoldingRow, parse_barclays_xls_bytes
from app.services.import_service import import_holding_snapshot, resolve_account_name
from app.services.order_service import ingest_parsed_orders
from app.services.portfolio_service import get_latest_batch_for_account

if TYPE_CHECKING:
    from collections.abc import Callable


class BarclaysPairError(ValueError):
    """Safe fixed message; never contains workbook values or account identifiers."""


@dataclass(frozen=True)
class FetchedPair:
    """Private in-memory transport, never included in public reports or logs."""

    holdings: bytes = field(repr=False)
    orders: bytes = field(repr=False)
    observed_at: dt.datetime
    acknowledge: Callable[[], None] = field(repr=False)

    @property
    def as_of(self) -> dt.date:
        if self.observed_at.tzinfo is None:
            raise BarclaysPairError("Barclays observation time must include a timezone.")
        return self.observed_at.astimezone(ZoneInfo("Europe/London")).date()


@dataclass
class ValidatedPair:
    account_name: str
    holdings: list[ParsedHoldingRow]
    orders: list[ParsedOrderRow]
    cancelled_orders: int


def _rows(workbook, required: set[str]) -> list[dict]:
    table = workbook.get_sheet_by_index(0).to_python()
    for index, row in enumerate(table[:6]):
        header = [str(cell).strip().lower() for cell in row]
        if required <= set(header):
            nonempty = [h for h in header if h]
            if len(nonempty) != len(set(nonempty)):
                raise BarclaysPairError("Barclays export has duplicate columns.")
            return [
                {key: values[i] if i < len(values) else None for i, key in enumerate(header) if key}
                for values in table[index + 1 :]
                if any(value not in (None, "") for value in values)
            ]
    raise BarclaysPairError("Barclays export is missing required columns.")


def _number(value) -> float:
    if isinstance(value, bool) or value in (None, ""):
        raise BarclaysPairError("Barclays export is missing a numeric value.")
    try:
        result = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        raise BarclaysPairError("Barclays export contains an invalid numeric value.") from None
    if not math.isfinite(result):
        raise BarclaysPairError("Barclays export contains a non-finite numeric value.")
    return result


def _validate_holdings(rows: list[dict]) -> None:
    seen = set()
    cash = 0
    numeric = {
        "quantity held",
        "last price",
        "value",
        "fx rate",
        "last price (p)",
        "value (£)",
        "book cost",
        "average fx rate",
        "book cost (£)",
        "% change",
    }
    for row in rows:
        name = str(row.get("investment") or "").strip()
        is_cash = name.lower() == "cash"
        ident = "CASH" if is_cash else str(row.get("identifier") or "").strip()
        if not name or not ident or ident in seen:
            raise BarclaysPairError("Barclays snapshot has missing or duplicate positions.")
        seen.add(ident)
        cash += is_cash
        _number(row.get("value (£)"))
        if not is_cash and not str(row.get("value ccy") or "").strip():
            raise BarclaysPairError("Barclays snapshot is missing currency.")
        if is_cash:
            # Real exports leave Cash's original-currency cells empty, but
            # supply its value in the explicitly GBP-denominated Value (£).
            if row.get("value ccy") not in (None, "", "GBP"):
                raise BarclaysPairError("Barclays cash currency is not supported.")
        elif _number(row.get("quantity held")) < 0:
            raise BarclaysPairError("Barclays snapshot quantity is invalid.")
        for key in numeric:
            if row.get(key) not in (None, ""):
                _number(row[key])
    if cash != 1:
        raise BarclaysPairError("Barclays snapshot requires exactly one verified cash row.")


def _validate_orders(rows: list[dict], account: str, as_of: dt.date) -> int:
    suffix = re.search(r"\(([^)]+)\)$", account)
    names = {account, suffix.group(1) if suffix else account}
    cancelled = 0
    for row in rows:
        when = row.get("date")
        if (
            not str(row.get("investment") or "").strip()
            or row.get("account") not in names
            or not isinstance(when, dt.date)
            or (when.date() if isinstance(when, dt.datetime) else when) > as_of
            or str(row.get("buy/sell") or "").lower() not in {"buy", "sell"}
        ):
            raise BarclaysPairError("Barclays order identity, side or date is invalid.")
        status = str(row.get("order status") or "").lower()
        if status == "cancelled":
            # Preserve the existing Completed-only import contract, but report
            # cancelled rows explicitly. Unknown/partial statuses fail closed.
            cancelled += 1
        elif status == "completed":
            if not str(row.get("country") or "").strip():
                raise BarclaysPairError("Barclays completed order is missing fingerprint identity.")
            if _number(row.get("quantity")) <= 0 or _number(row.get("cost/proceeds")) < 0:
                raise BarclaysPairError("Barclays completed order amounts are invalid.")
        else:
            raise BarclaysPairError("Barclays order status needs review.")
    return cancelled


def validate_pair(holdings: bytes, orders: bytes, *, as_of: dt.date) -> ValidatedPair:
    try:
        hw = CalamineWorkbook.from_filelike(io.BytesIO(holdings))
        ow = CalamineWorkbook.from_filelike(io.BytesIO(orders))
        if len(hw.sheet_names) != 1 or hw.sheet_names != ow.sheet_names:
            raise BarclaysPairError("Barclays export account identity is not verified.")
        holding_rows = _rows(
            hw, {"investment", "identifier", "quantity held", "value (£)", "value ccy"}
        )
        order_rows = _rows(
            ow,
            {
                "investment",
                "date",
                "order status",
                "account",
                "buy/sell",
                "quantity",
                "cost/proceeds",
                "country",
            },
        )
        _validate_holdings(holding_rows)
        cancelled = _validate_orders(order_rows, hw.sheet_names[0], as_of)
        h, _ = parse_barclays_xls_bytes(holdings, default_as_of_date=as_of)
        o = parse_barclays_order_xls_bytes(orders)
        if len(h) != len(holding_rows) or len(o) + cancelled != len(order_rows):
            raise BarclaysPairError("Barclays export contains unrepresented rows.")
        return ValidatedPair(hw.sheet_names[0], h, o, cancelled)
    except BarclaysPairError:
        raise
    except Exception:
        raise BarclaysPairError("Barclays export pair could not be validated.") from None


async def import_pair(
    session: AsyncSession, holdings: bytes, orders: bytes, *, as_of: dt.date
) -> dict:
    """Own one transaction for the pair, containing legacy matcher's commits.

    Validate everything before opening a transaction. The joined session cannot
    commit the owning connection: a late order/matching failure rolls back the
    holdings too. Never combine this operation with caller-owned pending writes.
    """
    pair = validate_pair(holdings, orders, as_of=as_of)
    if session.new or session.dirty or session.deleted:
        raise BarclaysPairError("Barclays pair import requires a clean session.")
    connection = await session.connection()
    result = {
        "snapshot": "unchanged",
        "orders": "unchanged",
        "orders_imported": 0,
        "cancelled_orders": pair.cancelled_orders,
    }
    try:
        async with AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="rollback_only"
        ) as worker:
            canonical = await resolve_account_name(worker, pair.account_name)
            latest = await get_latest_batch_for_account(worker, canonical)
            if latest is not None:
                if as_of < latest.as_of_date:
                    raise BarclaysPairError("Barclays observation predates the latest snapshot.")
                previous_identifiers = set(
                    (
                        await worker.scalars(
                            select(Instrument.identifier)
                            .join(HoldingSnapshot, HoldingSnapshot.instrument_id == Instrument.id)
                            .where(
                                HoldingSnapshot.import_batch_id == latest.id,
                                Instrument.account_name == canonical,
                            )
                        )
                    ).all()
                )
                if previous_identifiers - {row.identifier for row in pair.holdings}:
                    # The export has no independently verified total/count. A
                    # missing row alone cannot prove a sale or close a position.
                    raise BarclaysPairError(
                        "Barclays positions disappeared; operator review required."
                    )
            for name in {row.account_name for row in pair.orders}:
                alias = await worker.scalar(
                    select(AccountAlias).where(
                        AccountAlias.source == "barclays_orders",
                        AccountAlias.source_account_name == name,
                    )
                )
                if alias is None or alias.canonical_account_name != canonical:
                    raise BarclaysPairError("Barclays order account alias needs review.")
            # Daily observations remain distinct; same-day unchanged snapshots
            # and provider row reorderings are idempotent. Scope is in each row.
            payload = {
                "provider": "barclays-live-v1",
                "account": canonical,
                "as_of": as_of.isoformat(),
                "rows": sorted(
                    [asdict(row) for row in pair.holdings], key=lambda row: row["identifier"]
                ),
            }
            snapshot_hash = hashlib.sha256(
                json.dumps(payload, sort_keys=True, allow_nan=False).encode()
            ).hexdigest()
            # Compare only the latest account observation: A -> B -> A is a
            # new correction, not a historical duplicate. Retain its semantic
            # hash even when an older observation had the same bytes/values.
            if latest is None or latest.file_sha256 != snapshot_hash:
                await import_holding_snapshot(
                    worker,
                    parsed_rows=pair.holdings,
                    as_of_date=as_of,
                    filename=f"barclays-holdings-{as_of.isoformat()}.xls",
                    file_sha256=snapshot_hash,
                    force=True,
                    commit=False,
                )
                result["snapshot"] = "imported"
            order_hash = hashlib.sha256(orders).hexdigest()
            exists = await worker.scalar(
                select(OrderImportBatch.id).where(OrderImportBatch.file_sha256 == order_hash)
            )
            if exists is None:
                _, count = await ingest_parsed_orders(
                    worker,
                    parsed=pair.orders,
                    file_bytes=orders,
                    filename=f"barclays-orders-{as_of.isoformat()}.xls",
                    commit=False,
                )
                result["orders"] = "imported" if count else "unchanged"
                result["orders_imported"] = count
            await worker.commit()
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    return result

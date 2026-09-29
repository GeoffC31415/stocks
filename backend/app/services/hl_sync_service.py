"""Coherent HL export pairs: in-memory staging and one owning transaction."""

from __future__ import annotations

import datetime as dt  # noqa: TC003 - public transport annotations
import hashlib
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.hl_parser import (
    HLParseError,
    parse_hl_activity_csv_bytes,
    parse_hl_holdings_csv_bytes,
    validate_hl_pair_metadata,
)
from app.services.import_service import DuplicateImportError, import_holding_snapshot
from app.services.order_service import DuplicateOrderImportError, ingest_parsed_orders


@dataclass(frozen=True)
class FetchedHLPair:
    """Private transport; never publish either half into the unpaired inbox."""

    holdings: bytes = field(repr=False)
    orders: bytes = field(repr=False)
    observed_at: dt.datetime

    @property
    def as_of(self) -> dt.date:
        if self.observed_at.tzinfo is None:
            raise HLParseError("HL pair observation time requires a timezone.")
        return self.observed_at.astimezone(ZoneInfo("Europe/London")).date()


async def import_pair(
    session: AsyncSession, holdings: bytes, orders: bytes, *, as_of: dt.date
) -> dict[str, str | int]:
    """Validate both halves before writing; rollback both on errors/cancellation.

    Requires a clean session. Owns the caller transaction and contains legacy
    matcher's internal commits using a rollback-only joined session. The caller
    can catch a failure and run another broker with the same session safely.
    """
    validate_hl_pair_metadata(holdings, orders, as_of=as_of)
    parsed, inferred_as_of = parse_hl_holdings_csv_bytes(holdings)
    trades = parse_hl_activity_csv_bytes(orders)
    if any(row.order_date.date() > as_of for row in trades):
        raise HLParseError("HL pair contains future activity.")
    if not parsed or inferred_as_of != as_of:
        raise HLParseError("HL pair snapshot observation is empty or incoherent.")
    accounts = {row.account_name for row in parsed}
    if len(accounts) != 1 or any(row.account_name not in accounts for row in trades):
        raise HLParseError("HL pair account identity does not match.")
    if session.new or session.dirty or session.deleted:
        raise HLParseError("HL pair import requires a clean session.")
    result: dict[str, str | int] = {
        "snapshot": "unchanged",
        "orders": "unchanged",
        "orders_imported": 0,
    }
    try:
        async with AsyncSession(
            bind=await session.connection(),
            expire_on_commit=False,
            join_transaction_mode="rollback_only",
        ) as worker:
            try:
                await import_holding_snapshot(
                    worker,
                    parsed_rows=parsed,
                    as_of_date=as_of,
                    filename="hl-pair-holdings.csv",
                    file_sha256=hashlib.sha256(holdings).hexdigest(),
                    commit=False,
                )
                result["snapshot"] = "imported"
            except DuplicateImportError:
                pass
            try:
                _, inserted = await ingest_parsed_orders(
                    worker,
                    parsed=trades,
                    file_bytes=orders,
                    filename="hl-pair-activity.csv",
                    commit=False,
                )
                result.update(orders="imported", orders_imported=inserted)
            except DuplicateOrderImportError:
                pass
        await session.commit()
        session.expire_all()
        return result
    except BaseException:
        await session.rollback()
        raise

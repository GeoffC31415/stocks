"""Coherent HL export pairs: in-memory staging and one owning transaction."""

from __future__ import annotations

import datetime as dt  # noqa: TC003 - public transport annotations
import hashlib
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccountAlias
from app.services.hl_parser import (
    HLParseError,
    parse_hl_activity_csv_bytes,
    parse_hl_holdings_csv_bytes,
    validate_hl_pair_metadata,
)
from app.services.import_service import (
    DuplicateImportError,
    import_holding_snapshot,
    resolve_account_name,
)
from app.services.order_service import DuplicateOrderImportError, ingest_parsed_orders


@dataclass(frozen=True)
class FetchedHLPair:
    """Private transport; never publish either half into the unpaired inbox."""

    holdings: bytes = field(repr=False)
    orders: bytes = field(repr=False)
    observed_at: dt.datetime
    activity_start: dt.date | None = None
    activity_end: dt.date | None = None

    @property
    def as_of(self) -> dt.date:
        if self.observed_at.tzinfo is None:
            raise HLParseError("HL pair observation time requires a timezone.")
        return self.observed_at.astimezone(ZoneInfo("Europe/London")).date()


async def import_pair(
    session: AsyncSession, holdings: bytes, orders: bytes, *, as_of: dt.date,
    activity_start: dt.date | None = None, activity_end: dt.date | None = None,
) -> dict[str, str | int]:
    """Validate both halves before writing; rollback both on errors/cancellation.

    Requires a clean session. Owns the caller transaction and contains legacy
    matcher's internal commits using a rollback-only joined session. The caller
    can catch a failure and run another broker with the same session safely.
    """
    identity_key = validate_hl_pair_metadata(holdings, orders, as_of=as_of)
    parsed, inferred_as_of = parse_hl_holdings_csv_bytes(holdings)
    trades = parse_hl_activity_csv_bytes(orders)
    if (activity_start is not None or activity_end is not None) and (
        activity_start is None or activity_end is None or not activity_start <= activity_end <= as_of
        or any(not activity_start <= row.order_date.date() <= activity_end for row in trades)
    ):
        raise HLParseError("HL activity does not match its verified fetch window.")
    if any(row.order_date.date() > as_of for row in trades):
        raise HLParseError("HL pair contains future activity.")
    if not parsed or inferred_as_of > as_of:
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
        "valuation_at": inferred_as_of.isoformat(),
    }
    try:
        # Pin validation and mutation must share SQLite's writer reservation.
        await session.execute(text("UPDATE import_batches SET id = id WHERE 0"))
        canonical = await resolve_account_name(session, next(iter(accounts)))
        pins = list((await session.scalars(select(AccountAlias).where(
            AccountAlias.source == "hl-client-identity",
            AccountAlias.canonical_account_name == canonical,
        ))).all())
        if len(pins) != 1 or pins[0].source_account_name != identity_key:
            raise HLParseError("HL owner identity is unverified or changed; operator review required.")
        async with AsyncSession(
            bind=await session.connection(),
            expire_on_commit=False,
            join_transaction_mode="rollback_only",
        ) as worker:
            try:
                await import_holding_snapshot(
                    worker,
                    parsed_rows=parsed,
                    as_of_date=inferred_as_of,
                    filename="hl-pair-holdings.csv",
                    file_sha256=hashlib.sha256(holdings).hexdigest(),
                    commit=False,
                    latest_observation=True,
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

from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import HoldingSnapshot, ImportBatch, Instrument
from app.services.barclays_parser import ParsedHoldingRow, parse_barclays_xls_bytes


class DuplicateImportError(Exception):
    def __init__(self, batch_id: int) -> None:
        self.batch_id = batch_id
        super().__init__(f"Identical file already imported as batch {batch_id}")


async def _latest_batch(session: AsyncSession) -> ImportBatch | None:
    q = await session.execute(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(1))
    return q.scalar_one_or_none()


async def _snapshots_for_batch(session: AsyncSession, batch_id: int) -> list[HoldingSnapshot]:
    q = await session.execute(
        select(HoldingSnapshot)
        .where(HoldingSnapshot.import_batch_id == batch_id)
        .options(selectinload(HoldingSnapshot.instrument))
    )
    return list(q.scalars().all())


async def get_or_create_instrument(
    session: AsyncSession,
    row: ParsedHoldingRow,
) -> Instrument:
    stmt = select(Instrument).where(
        Instrument.account_name == row.account_name,
        Instrument.identifier == row.identifier,
    )
    inst = (await session.execute(stmt)).scalar_one_or_none()
    if inst:
        inst.security_name = row.investment
        inst.is_cash = row.is_cash
        return inst
    inst = Instrument(
        account_name=row.account_name,
        identifier=row.identifier,
        security_name=row.investment,
        is_cash=row.is_cash,
        closed_at=None,
    )
    session.add(inst)
    await session.flush()
    return inst


def _qty_changed(a: float | None, b: float | None) -> bool:
    if a is None and b is None:
        return False
    if a is None or b is None:
        return True
    return abs(a - b) > 1e-6


async def import_barclays_xls(
    session: AsyncSession,
    *,
    file_bytes: bytes,
    filename: str | None,
    as_of_date: dt.date | None,
    file_metadata_as_of: dt.date | None = None,
    force: bool = False,
) -> tuple[ImportBatch, dict[str, Any]]:
    sha = hashlib.sha256(file_bytes).hexdigest()
    if not force:
        dup = (
            await session.execute(select(ImportBatch).where(ImportBatch.file_sha256 == sha))
        ).scalar_one_or_none()
        if dup is not None:
            raise DuplicateImportError(dup.id)

    parsed_rows, inferred_as_of = parse_barclays_xls_bytes(
        file_bytes,
        default_as_of_date=as_of_date,
    )
    effective_date = as_of_date or file_metadata_as_of or inferred_as_of

    prev_batch = await _latest_batch(session)
    prev_by_instrument: dict[int, HoldingSnapshot] = {}
    if prev_batch is not None:
        for s in await _snapshots_for_batch(session, prev_batch.id):
            prev_by_instrument[s.instrument_id] = s

    batch = ImportBatch(
        as_of_date=effective_date,
        file_sha256=sha,
        filename=filename,
        diff_summary=None,
    )
    session.add(batch)
    await session.flush()

    paired: list[tuple[HoldingSnapshot, Instrument]] = []
    for row in parsed_rows:
        inst = await get_or_create_instrument(session, row)
        snap = HoldingSnapshot(
            import_batch_id=batch.id,
            instrument_id=inst.id,
            investment_label=row.investment,
            quantity=row.quantity,
            last_price=row.last_price,
            last_price_ccy=row.last_price_ccy,
            value=row.value,
            value_ccy=row.value_ccy,
            fx_rate=row.fx_rate,
            last_price_pence=row.last_price_pence,
            value_gbp=row.value_gbp,
            book_cost=row.book_cost,
            book_cost_ccy=row.book_cost_ccy,
            average_fx_rate=row.average_fx_rate,
            book_cost_gbp=row.book_cost_gbp,
            pct_change=row.pct_change,
        )
        session.add(snap)
        paired.append((snap, inst))

    await session.flush()

    curr_ids = {inst.id for _, inst in paired}
    new_ids: list[int] = []
    closed: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []

    for iid, prev_s in prev_by_instrument.items():
        if iid not in curr_ids:
            inst = prev_s.instrument
            closed.append(
                {
                    "instrument_id": iid,
                    "identifier": inst.identifier,
                    "account_name": inst.account_name,
                    "security_name": inst.security_name,
                }
            )
            inst.closed_at = dt.datetime.now(dt.UTC)

    for snap, inst in paired:
        iid = inst.id
        if iid not in prev_by_instrument:
            new_ids.append(iid)
            inst.closed_at = None
            continue
        prev_s = prev_by_instrument[iid]
        inst.closed_at = None
        if _qty_changed(prev_s.quantity, snap.quantity) or (
            prev_s.value_gbp is not None
            and snap.value_gbp is not None
            and abs(prev_s.value_gbp - snap.value_gbp) > 0.01
        ):
            changed.append(
                {
                    "instrument_id": iid,
                    "identifier": inst.identifier,
                    "account_name": inst.account_name,
                    "quantity_before": prev_s.quantity,
                    "quantity_after": snap.quantity,
                }
            )

    from app.services.instrument_matcher import link_orders_to_instruments
    orders_linked = await link_orders_to_instruments(session)

    summary: dict[str, Any] = {
        "new_instrument_ids": new_ids,
        "closed": closed,
        "changed": changed,
        "row_count": len(parsed_rows),
        "orders_linked": orders_linked,
    }
    batch.diff_summary = summary
    await session.commit()
    await session.refresh(batch)
    return batch, summary

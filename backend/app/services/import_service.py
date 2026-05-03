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


async def get_import_batch(session: AsyncSession, batch_id: int) -> ImportBatch | None:
    return await session.get(ImportBatch, batch_id)


async def get_import_diff_summary(session: AsyncSession, batch_id: int) -> dict[str, Any] | None:
    batch = await get_import_batch(session, batch_id)
    if batch is None:
        return None

    summary = batch.diff_summary or {}
    previous_batch_id = summary.get("previous_batch_id")
    previous_as_of_date = summary.get("previous_as_of_date")
    if previous_batch_id is not None and previous_as_of_date is None:
        prev_batch = await get_import_batch(session, int(previous_batch_id))
        previous_as_of_date = prev_batch.as_of_date if prev_batch is not None else None

    return {
        "batch_id": batch.id,
        "as_of_date": batch.as_of_date,
        "previous_batch_id": previous_batch_id,
        "previous_as_of_date": previous_as_of_date,
        "new_instrument_ids": summary.get("new_instrument_ids", []),
        "closed": summary.get("closed", []),
        "changed": summary.get("changed", []),
        "row_count": summary.get("row_count"),
        "orders_linked": summary.get("orders_linked"),
    }


def _delta(after: float | None, before: float | None) -> float | None:
    if after is None or before is None:
        return None
    return after - before


async def compare_import_batches(
    session: AsyncSession,
    *,
    from_batch_id: int,
    to_batch_id: int,
) -> dict[str, Any] | None:
    from_batch = await get_import_batch(session, from_batch_id)
    to_batch = await get_import_batch(session, to_batch_id)
    if from_batch is None or to_batch is None:
        return None

    from_snapshots = await _snapshots_for_batch(session, from_batch_id)
    to_snapshots = await _snapshots_for_batch(session, to_batch_id)
    from_by_instrument = {s.instrument_id: s for s in from_snapshots}
    to_by_instrument = {s.instrument_id: s for s in to_snapshots}
    total_from = sum(s.value_gbp or 0.0 for s in from_snapshots)
    total_to = sum(s.value_gbp or 0.0 for s in to_snapshots)

    rows: list[dict[str, Any]] = []
    for instrument_id in sorted(set(from_by_instrument) | set(to_by_instrument)):
        from_snap = from_by_instrument.get(instrument_id)
        to_snap = to_by_instrument.get(instrument_id)
        snap = to_snap or from_snap
        if snap is None:
            continue

        inst = snap.instrument
        value_from = from_snap.value_gbp if from_snap is not None else None
        value_to = to_snap.value_gbp if to_snap is not None else None
        weight_from = ((value_from or 0.0) / total_from * 100.0) if total_from > 0 else None
        weight_to = ((value_to or 0.0) / total_to * 100.0) if total_to > 0 else None
        rows.append(
            {
                "instrument_id": instrument_id,
                "identifier": inst.identifier,
                "security_name": inst.security_name,
                "account_name": inst.account_name,
                "quantity_from": from_snap.quantity if from_snap is not None else None,
                "quantity_to": to_snap.quantity if to_snap is not None else None,
                "delta_quantity": _delta(
                    to_snap.quantity if to_snap is not None else None,
                    from_snap.quantity if from_snap is not None else None,
                ),
                "value_from_gbp": value_from,
                "value_to_gbp": value_to,
                "delta_value_gbp": _delta(value_to, value_from),
                "price_from": from_snap.last_price if from_snap is not None else None,
                "price_to": to_snap.last_price if to_snap is not None else None,
                "delta_price": _delta(
                    to_snap.last_price if to_snap is not None else None,
                    from_snap.last_price if from_snap is not None else None,
                ),
                "weight_from_pct": weight_from,
                "weight_to_pct": weight_to,
                "delta_weight_pct": _delta(weight_to, weight_from),
                "status": (
                    "new"
                    if from_snap is None
                    else "closed"
                    if to_snap is None
                    else "changed"
                    if _delta(value_to, value_from) or _delta(to_snap.quantity, from_snap.quantity)
                    else "unchanged"
                ),
            }
        )

    rows.sort(key=lambda row: abs(row["delta_value_gbp"] or 0.0), reverse=True)
    return {"from_batch": from_batch, "to_batch": to_batch, "rows": rows}


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
                    "security_name": inst.security_name,
                    "quantity_before": prev_s.quantity,
                    "quantity_after": snap.quantity,
                    "value_before": prev_s.value_gbp,
                    "value_after": snap.value_gbp,
                    "delta_value_gbp": _delta(snap.value_gbp, prev_s.value_gbp),
                }
            )

    from app.services.instrument_matcher import link_orders_to_instruments
    orders_linked = await link_orders_to_instruments(session)

    summary: dict[str, Any] = {
        "previous_batch_id": prev_batch.id if prev_batch is not None else None,
        "previous_as_of_date": prev_batch.as_of_date.isoformat() if prev_batch is not None else None,
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

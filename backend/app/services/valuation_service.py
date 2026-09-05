"""Canonical snapshot states ordered by valuation date, then correction ID.

Snapshot imports contain complete account positions. Replace each touched
account as a unit, carry untouched accounts forward, and emit only one state
per selected valuation date. No order estimates or current prices enter here.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from itertools import groupby
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import HoldingSnapshot, ImportBatch, Instrument

if TYPE_CHECKING:
    import datetime as dt

    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ValuationState:
    date: dt.date
    snapshots: list[HoldingSnapshot]
    account_dates: dict[str, dt.date]

    @property
    def value(self) -> float | None:
        values = [snapshot.value_gbp for snapshot in self.snapshots]
        if any(value is None or not math.isfinite(value) for value in values):
            return None
        return sum(value for value in values if value is not None)


async def valuation_states(
    session: AsyncSession, *, account_name: str | None = None
) -> tuple[list[ValuationState], dt.date | None]:
    batches = list((await session.scalars(
        select(ImportBatch).order_by(ImportBatch.as_of_date, ImportBatch.id)
    )).all())
    query = (select(HoldingSnapshot).join(Instrument)
             .options(selectinload(HoldingSnapshot.instrument)))
    if account_name is not None:
        query = query.where(Instrument.account_name == account_name)
    by_batch: dict[int, dict[str, list[HoldingSnapshot]]] = defaultdict(lambda: defaultdict(list))
    account_by_instrument: dict[int, str] = {}
    for snapshot in (await session.scalars(query)).all():
        account = snapshot.instrument.account_name
        by_batch[snapshot.import_batch_id][account].append(snapshot)
        account_by_instrument[snapshot.instrument_id] = account
    accounts = set(account_by_instrument.values())
    current: dict[str, dict[int, HoldingSnapshot]] = {}
    account_dates: dict[str, dt.date] = {}
    states = []
    coverage_start = None
    for date, daily_batches in groupby(batches, key=lambda batch: batch.as_of_date):
        changed = False
        for batch in daily_batches:
            for account, snapshots in by_batch[batch.id].items():
                current[account] = {snapshot.instrument_id: snapshot for snapshot in snapshots}
                account_dates[account] = date
                changed = True
            for closed in (batch.diff_summary or {}).get("closed", []):
                instrument_id = closed.get("instrument_id")
                closed_account = account_by_instrument.get(instrument_id)
                if closed_account is not None:
                    current.setdefault(closed_account, {}).pop(instrument_id, None)
                    account_dates[closed_account] = date
                    changed = True
        if not changed:
            continue
        if coverage_start is None and len(accounts) > 1 and accounts <= account_dates.keys():
            coverage_start = date
        states.append(ValuationState(
            date=date,
            snapshots=[snapshot for positions in current.values() for snapshot in positions.values()],
            account_dates=dict(account_dates),
        ))
    return states, coverage_start

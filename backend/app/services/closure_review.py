"""Offline, single-observation operator review; no credentials or broker calls."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.import_service import get_latest_observation_for_account, resolve_account_name
from app.services.trading212 import Trading212DataError, sync_portfolio_snapshot

if TYPE_CHECKING:
    import datetime as dt
    from collections.abc import Mapping


@dataclass(frozen=True)
class ReviewedObservation:
    positions: list[Mapping[str, Any]]
    account_summary: Mapping[str, Any]

    async def fetch_positions(self) -> list[Mapping[str, Any]]:
        return self.positions

    async def fetch_account_summary(self) -> Mapping[str, Any]:
        return self.account_summary

    async def fetch_historical_orders(self) -> list[Mapping[str, Any]]:
        raise Trading212DataError("Closure review does not import order history.")


async def review_closure_observation(
    session: AsyncSession,
    *,
    account_name: str,
    expected_batch_id: int,
    expected_batch_sha256: str,
    observation_sha256: str,
    identifiers: frozenset[str],
    positions: list[Mapping[str, Any]],
    account_summary: Mapping[str, Any],
    apply: bool = False,
    observation_date: dt.date | None = None,
) -> dict[str, Any]:
    """Preview by default; apply only exact missing securities against latest state.

    The operator must independently review sale evidence and staged account
    ownership. A review is not durable authority, a provider inference or force.
    """
    if session.new or session.dirty or session.deleted:
        raise Trading212DataError("Closure review requires a clean session.")
    try:
        canonical = await resolve_account_name(session, account_name)
        latest = await get_latest_observation_for_account(session, canonical)
        if (
            latest is None
            or latest.id != expected_batch_id
            or latest.file_sha256 != expected_batch_sha256
            or latest.filename != "trading212-api-portfolio.json"
        ):
            raise Trading212DataError(
                "Closure review account or latest observation does not match."
            )
        if observation_date is not None and observation_date < latest.as_of_date:
            raise Trading212DataError("Closure review observation predates retained valuation.")
        if not identifiers or not isinstance(identifiers, frozenset):
            raise Trading212DataError("Closure review requires an explicit nonempty allowlist.")
        payload = json.dumps(
            {
                "account_name": canonical,
                "account": account_summary,
                "positions": sorted(positions, key=lambda item: json.dumps(item, sort_keys=True)),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        if hashlib.sha256(payload).hexdigest() != observation_sha256:
            raise Trading212DataError("Closure review staged observation does not match.")
        async with AsyncSession(
            bind=await session.connection(),
            expire_on_commit=False,
            join_transaction_mode="rollback_only",
        ) as worker:
            batch, summary = await sync_portfolio_snapshot(
                worker,
                ReviewedObservation(positions, account_summary),
                account_name=canonical,
                reviewed_closed_identifiers=identifiers,
                commit=False,
            )
            if observation_date is not None:
                batch.as_of_date = observation_date
            await worker.flush()
        if apply:
            await session.commit()
        else:
            await session.rollback()
        session.expire_all()
        return {
            "applied": apply,
            "account_name": canonical,
            "closed": summary["closed"],
            "expected_batch_id": expected_batch_id,
            "observation_sha256": observation_sha256,
        }
    except BaseException:
        await session.rollback()
        raise

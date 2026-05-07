"""
Candidate generation for instrument matching.

Finds potential instrument matches for a given order by:
1. Checking instrument aliases (manual/reusable)
2. Looking at same canonical account instruments
3. Looking at other account instruments (lower priority)
4. Filtering closed instruments based on order date
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Instrument, InstrumentAlias, AccountAlias
from app.services.matching.normalisation import normalise_name


async def resolve_canonical_account(
    session: AsyncSession,
    source: str,
    account_name: str,
) -> str:
    """
    Resolve an account name to its canonical form using account_aliases.
    Falls back to the original name if no alias exists.
    """
    stmt = (
        select(AccountAlias.canonical_account_name)
        .where(
            AccountAlias.source == source,
            AccountAlias.source_account_name == account_name,
        )
    )
    result = await session.execute(stmt)
    canonical = result.scalar_one_or_none()
    return canonical or account_name


async def find_alias_match(
    session: AsyncSession,
    source: str,
    account_name: str,
    security_name: str,
) -> Instrument | None:
    """
    Check if a manual/reusable instrument alias exists for this order.
    This is the highest-priority match path.
    """
    norm_name = normalise_name(security_name)
    if not norm_name:
        return None

    # Try with account scope first
    stmt = (
        select(InstrumentAlias.instrument_id)
        .where(
            InstrumentAlias.source == source,
            InstrumentAlias.source_account_name == account_name,
            InstrumentAlias.source_security_name_norm == norm_name,
        )
    )
    result = await session.execute(stmt)
    inst_id = result.scalar_one_or_none()

    if inst_id is not None:
        return await session.get(Instrument, inst_id)

    # Try without account scope (source + name only)
    stmt = (
        select(InstrumentAlias.instrument_id)
        .where(
            InstrumentAlias.source == source,
            InstrumentAlias.source_account_name.is_(None),
            InstrumentAlias.source_security_name_norm == norm_name,
        )
    )
    result = await session.execute(stmt)
    inst_id = result.scalar_one_or_none()

    if inst_id is not None:
        return await session.get(Instrument, inst_id)

    return None


async def build_candidates(
    session: AsyncSession,
    source: str,
    account_name: str,
    security_name: str,
    order_date: dt.datetime | None = None,
) -> list[Instrument]:
    """
    Build a list of candidate instruments for a given order.

    Returns instruments ordered by relevance:
    1. Same canonical account instruments first
    2. Open instruments preferred over closed ones
    3. Closed instruments included only if order date is before closed_at
    """
    canonical_account = await resolve_canonical_account(session, source, account_name)

    # Load all non-cash instruments
    stmt = select(Instrument).where(Instrument.is_cash == False)  # noqa: E712
    result = await session.execute(stmt)
    all_instruments = list(result.scalars().all())

    same_account: list[Instrument] = []
    other_account: list[Instrument] = []

    for inst in all_instruments:
        # Check if instrument is compatible with order date
        if inst.closed_at is not None:
            if order_date is not None and order_date > inst.closed_at:
                # Order is after instrument was closed - skip unless very close
                continue
            # Include closed instruments but deprioritize them
            other_account.append(inst)
            continue

        if inst.account_name == canonical_account:
            same_account.append(inst)
        else:
            other_account.append(inst)

    # Return same-account candidates first, then other-account
    return same_account + other_account

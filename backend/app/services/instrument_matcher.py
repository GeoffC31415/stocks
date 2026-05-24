"""
Single unified matcher that resolves an order's security_name to an Instrument.

Called once at import/backfill time so all queries can use FK joins.

This module delegates to the new matching engine in services/matching/.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order


async def link_orders_to_instruments(
    session: AsyncSession,
    orders: Sequence[Order] | None = None,
) -> int:
    """
    Resolve instrument_id for orders that don't have one yet.
    If *orders* is None, loads all unlinked orders from the DB.
    Returns the number of orders that were linked.

    Delegates to the new matching engine.
    """
    from app.services.matching.resolver import resolve_batch

    result = await resolve_batch(
        session,
        source="barclays_orders",
        mode="unmatched_only",
    )
    return result["orders_linked"]

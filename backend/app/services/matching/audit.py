"""
Audit logging for order-instrument matching decisions.

Every change to orders.instrument_id, match_status, etc. should be recorded here.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, OrderMatchAudit


async def write_audit(
    session: AsyncSession,
    order: Order,
    new_instrument_id: int | None,
    new_status: str | None,
    method: str | None = None,
    confidence: float | None = None,
    evidence: dict | None = None,
    changed_by: str = "system",
    reason: str | None = None,
) -> OrderMatchAudit:
    """
    Record an audit entry for a matching change.

    Captures the old state before the change is applied.
    """
    audit = OrderMatchAudit(
        order_id=order.id,
        old_instrument_id=order.instrument_id,
        new_instrument_id=new_instrument_id,
        old_status=order.match_status,
        new_status=new_status,
        method=method,
        confidence=confidence,
        evidence=evidence,
        changed_by=changed_by,
        reason=reason,
    )
    session.add(audit)
    await session.flush()
    return audit

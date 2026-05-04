"""
Single unified matcher that resolves an order's security_name to an Instrument.

Called once at import/backfill time so all queries can use FK joins.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Instrument, Order

_NOISE = frozenset(
    {
        "plc",
        "ord",
        "group",
        "holdings",
        "holding",
        "limited",
        "ltd",
        "inc",
        "corp",
        "the",
        "and",
        "of",
        "co",
        "new",
        "np",
        "di",
        "corporation",
        "company",
        "common",
        "shares",
        "share",
        "etf",
        "ucits",
        "fund",
        "funds",
        "public",
    }
)

_NORMALISE_RE = re.compile(r"[^a-z0-9 ]+")


def _normalise(name: str) -> str:
    return _NORMALISE_RE.sub(" ", name.lower()).strip()


def _meaningful_tokens(name: str) -> frozenset[str]:
    return frozenset(t for t in _normalise(name).split() if t not in _NOISE and len(t) > 1)


def match_order_to_instrument(
    order_name: str,
    order_account: str,
    instruments: Sequence[Instrument],
) -> Instrument | None:
    """
    Match an order security_name against a set of instruments.

    Priority:
      1. Same account + exact normalised name  (best)
      2. Any account + exact normalised name
      3. Same account + substring containment
      4. Any account + substring containment
      5. Same account + strict meaningful-token overlap (≥80%, min 2)
      6. Any account + strict meaningful-token overlap (≥80%, min 2)

    Returns None if no confident match is found.
    """
    o_norm = _normalise(order_name)
    if not o_norm:
        return None

    o_tokens = _meaningful_tokens(order_name)

    same_acct: list[Instrument] = []
    other_acct: list[Instrument] = []
    for inst in instruments:
        if inst.is_cash:
            continue
        if inst.account_name == order_account:
            same_acct.append(inst)
        else:
            other_acct.append(inst)

    def _try_exact(candidates: Sequence[Instrument]) -> Instrument | None:
        for inst in candidates:
            if _normalise(inst.security_name) == o_norm:
                return inst
        return None

    def _try_substring(candidates: Sequence[Instrument]) -> Instrument | None:
        best: Instrument | None = None
        best_len = 0
        for inst in candidates:
            i_norm = _normalise(inst.security_name)
            if (o_norm in i_norm or i_norm in o_norm) and len(i_norm) > best_len:
                # prefer the longer instrument name (more specific match)
                best = inst
                best_len = len(i_norm)
        return best

    def _try_token(candidates: Sequence[Instrument]) -> Instrument | None:
        if len(o_tokens) < 2:
            return None
        best: Instrument | None = None
        best_score = 0
        for inst in candidates:
            i_tokens = _meaningful_tokens(inst.security_name)
            if not i_tokens:
                continue
            overlap = len(o_tokens & i_tokens)
            min_len = min(len(o_tokens), len(i_tokens))
            threshold = max(2, int(min_len * 0.8))
            if overlap >= threshold and overlap > best_score:
                best = inst
                best_score = overlap
        return best

    for try_fn in (_try_exact, _try_substring, _try_token):
        result = try_fn(same_acct)
        if result:
            return result
        result = try_fn(other_acct)
        if result:
            return result

    return None


async def link_orders_to_instruments(
    session: AsyncSession,
    orders: Sequence[Order] | None = None,
) -> int:
    """
    Resolve instrument_id for orders that don't have one yet.
    If *orders* is None, loads all unlinked orders from the DB.
    Returns the number of orders that were linked.
    """
    instruments = list((await session.execute(select(Instrument))).scalars().all())
    if not instruments:
        return 0

    if orders is None:
        result = await session.execute(select(Order).where(Order.instrument_id.is_(None)))
        orders = list(result.scalars().all())

    linked = 0
    for order in orders:
        if order.instrument_id is not None:
            continue
        match = match_order_to_instrument(
            order.security_name,
            order.account_name,
            instruments,
        )
        if match:
            order.instrument_id = match.id
            linked += 1

    return linked

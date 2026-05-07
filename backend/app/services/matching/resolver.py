"""
Order-to-instrument resolver.

Orchestrates the matching flow:
1. Normalize source account using account_aliases
2. Check manual/reusable aliases first
3. Build candidate instruments
4. Score each candidate
5. Decide status (auto_high / auto_review / unmatched)
6. Persist match metadata
7. Write audit event
"""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Instrument, InstrumentAlias, Order
from app.services.matching.candidates import (
    resolve_canonical_account,
    find_alias_match,
    build_candidates,
)
from app.services.matching.scoring import (
    score_candidate,
    classify_score,
    determine_method,
    CONFIDENCE_HIGH,
)
from app.services.matching.normalisation import normalise_name
from app.services.matching.audit import write_audit


async def resolve_order(
    session: AsyncSession,
    order: Order,
    *,
    source: str = "barclays_orders",
    dry_run: bool = False,
    min_auto_confidence: float = CONFIDENCE_HIGH,
    overwrite_manual: bool = False,
) -> dict:
    """
    Resolve a single order to an instrument.

    Returns a dict with:
    - order_id
    - instrument_id (new or unchanged)
    - match_status
    - match_method
    - match_confidence
    - evidence
    - changed (bool)
    """
    # Skip manual/ignored orders unless explicitly allowed
    if order.match_status in ("manual", "ignored") and not overwrite_manual:
        return {
            "order_id": order.id,
            "instrument_id": order.instrument_id,
            "match_status": order.match_status,
            "match_method": order.match_method,
            "match_confidence": order.match_confidence,
            "evidence": None,
            "changed": False,
            "skipped": True,
            "skip_reason": f"status is {order.match_status}",
        }

    order_name = order.security_name
    order_account = order.account_name
    order_date = order.order_date

    # Step 1: Resolve canonical account
    canonical_account = await resolve_canonical_account(session, source, order_account)

    # Step 2: Check alias match (highest priority)
    alias_inst = await find_alias_match(session, source, order_account, order_name)
    if alias_inst is not None:
        old_instrument_id = order.instrument_id
        old_status = order.match_status
        changed = (old_instrument_id != alias_inst.id) or (old_status != "alias_exact")

        if changed and not dry_run:
            await write_audit(
                session, order,
                new_instrument_id=alias_inst.id,
                new_status="auto_high",
                method="alias_exact",
                confidence=1.0,
                changed_by="system_resolver",
                reason="Exact alias match",
            )
            order.instrument_id = alias_inst.id
            order.match_status = "auto_high"
            order.match_method = "alias_exact"
            order.match_confidence = 1.0
            order.matched_at = None  # Will be set by commit
            order.matched_by = "system_resolver"

        return {
            "order_id": order.id,
            "instrument_id": alias_inst.id,
            "match_status": "auto_high",
            "match_method": "alias_exact",
            "match_confidence": 1.0,
            "evidence": {
                "method": "alias_exact",
                "canonical_account": canonical_account,
            },
            "changed": changed,
            "dry_run": dry_run,
        }

    # Step 3: Build candidates
    candidates = await build_candidates(
        session, source, order_account, order_name, order_date
    )

    if not candidates:
        return {
            "order_id": order.id,
            "instrument_id": None,
            "match_status": "unmatched",
            "match_method": None,
            "match_confidence": None,
            "evidence": {"reason": "no_candidates"},
            "changed": False,
        }

    # Step 4: Score each candidate
    scored: list[tuple[float, dict]] = []
    for inst in candidates:
        s, ev = score_candidate(inst, order_name, order_account, canonical_account, order_date)
        scored.append((s, ev))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        return {
            "order_id": order.id,
            "instrument_id": None,
            "match_status": "unmatched",
            "match_method": None,
            "match_confidence": None,
            "evidence": {"reason": "no_scores"},
            "changed": False,
        }

    best_score, best_evidence = scored[0]
    best_method = determine_method(best_score, best_evidence)
    best_status = classify_score(best_score)

    # Build evidence with alternatives
    alternatives = []
    for s, ev in scored[1:4]:  # Top 3 alternatives
        alternatives.append({
            "instrument_id": ev["instrument_id"],
            "security_name": ev["instrument_name"],
            "score": ev["final_score"],
        })

    evidence = {
        "order": {
            "security_name": order_name,
            "account_name": order_account,
            "canonical_account_name": canonical_account,
            "normalised_name": normalise_name(order_name),
        },
        "selected_candidate": {
            "instrument_id": best_evidence["instrument_id"],
            "security_name": best_evidence["instrument_name"],
            "score": best_evidence["final_score"],
        },
        "method": best_method,
        "scores": best_evidence.get("scores", {}),
        "alternatives": alternatives,
    }

    old_instrument_id = order.instrument_id
    old_status = order.match_status

    # Determine if we should link
    should_link = False
    if best_status == "auto_high":
        should_link = True
    elif best_status == "auto_review" and best_score >= min_auto_confidence:
        should_link = True

    changed = False
    if should_link:
        new_inst_id = best_evidence["instrument_id"]
        changed = (old_instrument_id != new_inst_id) or (old_status != best_status)

        if changed and not dry_run:
            await write_audit(
                session, order,
                new_instrument_id=new_inst_id,
                new_status=best_status,
                method=best_method,
                confidence=best_score,
                evidence=evidence,
                changed_by="system_resolver",
                reason=f"Auto match: {best_method} (score={best_score:.3f})",
            )
            order.instrument_id = new_inst_id
            order.match_status = best_status
            order.match_method = best_method
            order.match_confidence = best_score
            order.match_evidence = evidence
            order.matched_by = "system_resolver"
    elif best_status == "auto_review":
        # Store candidates in evidence but don't link
        changed = (old_status != "auto_review")
        if changed and not dry_run:
            await write_audit(
                session, order,
                new_instrument_id=order.instrument_id,  # unchanged
                new_status="auto_review",
                method=best_method,
                confidence=best_score,
                evidence=evidence,
                changed_by="system_resolver",
                reason=f"Review candidate: {best_method} (score={best_score:.3f})",
            )
            order.match_status = "auto_review"
            order.match_method = best_method
            order.match_confidence = best_score
            order.match_evidence = evidence
    else:
        # Unmatched
        changed = (old_status != "unmatched")
        if changed and not dry_run:
            await write_audit(
                session, order,
                new_instrument_id=None,
                new_status="unmatched",
                method=None,
                confidence=best_score,
                evidence=evidence,
                changed_by="system_resolver",
                reason="No confident match found",
            )
            order.match_status = "unmatched"
            order.match_evidence = evidence

    return {
        "order_id": order.id,
        "instrument_id": order.instrument_id if should_link else order.instrument_id,
        "match_status": best_status if not dry_run else order.match_status,
        "match_method": best_method,
        "match_confidence": best_score,
        "evidence": evidence,
        "changed": changed,
        "dry_run": dry_run,
    }


async def resolve_batch(
    session: AsyncSession,
    *,
    source: str = "barclays_orders",
    mode: str = "unmatched_only",
    min_auto_confidence: float = CONFIDENCE_HIGH,
    overwrite_manual: bool = False,
) -> dict:
    """
    Resolve a batch of orders.

    Modes:
    - unmatched_only: Only orders with no instrument
    - review_only: Re-score review candidates
    - all_non_manual: Everything except manual/ignored
    - all: Full rematch
    """
    # Build query based on mode
    if mode == "unmatched_only":
        q = select(Order).where(
            (Order.instrument_id.is_(None)) | (Order.match_status == "unmatched")
        )
    elif mode == "review_only":
        q = select(Order).where(Order.match_status == "auto_review")
    elif mode == "all_non_manual":
        q = select(Order).where(
            Order.match_status.not_in(["manual", "ignored"])
        )
    else:  # all
        q = select(Order)

    result = await session.execute(q)
    orders = list(result.scalars().all())

    results = []
    linked = 0
    review = 0
    unmatched = 0
    skipped = 0

    for order in orders:
        r = await resolve_order(
            session, order,
            source=source,
            dry_run=False,
            min_auto_confidence=min_auto_confidence,
            overwrite_manual=overwrite_manual,
        )
        results.append(r)

        if r.get("skipped"):
            skipped += 1
        elif r.get("match_status") in ("auto_high",) and r.get("changed"):
            linked += 1
        elif r.get("match_status") == "auto_review":
            review += 1
        elif r.get("match_status") == "unmatched":
            unmatched += 1

    await session.commit()

    return {
        "orders_examined": len(orders),
        "orders_linked": linked,
        "orders_review": review,
        "orders_unmatched": unmatched,
        "orders_skipped": skipped,
        "results": results,
    }


async def dry_run_resolve(
    session: AsyncSession,
    *,
    source: str = "barclays_orders",
    mode: str = "unmatched_only",
    min_auto_confidence: float = CONFIDENCE_HIGH,
) -> dict:
    """
    Dry-run resolution: score all candidates without persisting changes.
    """
    if mode == "unmatched_only":
        q = select(Order).where(
            (Order.instrument_id.is_(None)) | (Order.match_status == "unmatched")
        )
    elif mode == "review_only":
        q = select(Order).where(Order.match_status == "auto_review")
    elif mode == "all_non_manual":
        q = select(Order).where(
            Order.match_status.not_in(["manual", "ignored"])
        )
    else:
        q = select(Order)

    result = await session.execute(q)
    orders = list(result.scalars().all())

    results = []
    would_link = 0
    would_review = 0
    would_unmatched = 0
    skipped = 0

    for order in orders:
        r = await resolve_order(
            session, order,
            source=source,
            dry_run=True,
            min_auto_confidence=min_auto_confidence,
        )
        results.append(r)

        if r.get("skipped"):
            skipped += 1
        elif r.get("match_status") in ("auto_high",) or (r.get("match_confidence", 0) >= min_auto_confidence):
            would_link += 1
        elif r.get("match_confidence", 0) >= 0.75:
            would_review += 1
        else:
            would_unmatched += 1

    # Return summary + examples
    examples = []
    for r in results:
        if not r.get("skipped") and r.get("evidence"):
            examples.append({
                "order_id": r["order_id"],
                "security_name": r["evidence"].get("order", {}).get("security_name", ""),
                "would_link": r.get("match_status") == "auto_high" or r.get("match_confidence", 0) >= min_auto_confidence,
                "best_score": r.get("match_confidence"),
                "best_method": r.get("match_method"),
                "best_instrument_id": r["evidence"].get("selected_candidate", {}).get("instrument_id"),
            })

    return {
        "dry_run": True,
        "orders_examined": len(orders),
        "would_auto_match": would_link,
        "would_mark_review": would_review,
        "would_remain_unmatched": would_unmatched,
        "orders_skipped": skipped,
        "examples": examples[:20],  # Limit examples
    }

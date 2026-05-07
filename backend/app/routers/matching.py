"""
Matching admin API endpoints.

Provides endpoints for:
- Matching summary
- Unmatched groups
- Candidate suggestions
- Group/order resolution
- Alias CRUD
- Reconciliation
- Audit log
- Backfill/dry-run
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import (
    AccountAlias,
    Instrument,
    InstrumentAlias,
    Order,
    OrderMatchAudit,
    HoldingSnapshot,
)
from app.schemas import (
    AccountAliasIn,
    AccountAliasOut,
    BackfillRequest,
    BackfillResult,
    CreateHistoricalInstrumentBody,
    InstrumentAliasIn,
    InstrumentAliasOut,
    MatchCandidate,
    MatchSummary,
    OrderMatchAuditOut,
    ReconciliationRow,
    ResolveGroupBody,
    ResolveOrderBody,
    UnmatchedGroup,
)
from app.services.matching.normalisation import normalise_name
from app.services.matching.candidates import (
    resolve_canonical_account,
    build_candidates,
    find_alias_match,
)
from app.services.matching.scoring import score_candidate, determine_method
from app.services.matching.resolver import resolve_order, resolve_batch, dry_run_resolve
from app.services.matching.audit import write_audit

router = APIRouter(prefix="/api/matching", tags=["matching"])


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

@router.get("/summary", response_model=MatchSummary)
async def get_matching_summary(
    session: AsyncSession = Depends(get_session),
) -> MatchSummary:
    """Get overall matching health summary."""
    total = (await session.execute(select(func.count()).select_from(Order))).scalar_one()
    matched = (await session.execute(
        select(func.count()).select_from(Order).where(Order.instrument_id.isnot(None))
    )).scalar_one()
    unmatched = total - matched

    status_counts = {}
    for status in ["auto_high", "auto_review", "manual", "ignored", "unmatched", "legacy_matched"]:
        cnt = (await session.execute(
            select(func.count()).select_from(Order).where(Order.match_status == status)
        )).scalar_one()
        status_counts[status] = cnt

    # Count unmatched groups
    unmatched_groups_result = await session.execute(
        select(
            Order.account_name,
            Order.security_name,
        ).where(
            Order.instrument_id.is_(None)
        ).group_by(
            Order.account_name,
            Order.security_name,
        )
    )
    unmatched_group_count = len(unmatched_groups_result.all())

    return MatchSummary(
        orders_total=total,
        orders_matched=matched,
        orders_unmatched=unmatched,
        orders_auto_high=status_counts.get("auto_high", 0),
        orders_auto_review=status_counts.get("auto_review", 0),
        orders_manual=status_counts.get("manual", 0),
        orders_ignored=status_counts.get("ignored", 0),
        orders_legacy=status_counts.get("legacy_matched", 0),
        unmatched_groups=unmatched_group_count,
    )


# ---------------------------------------------------------------------------
# Unmatched groups
# ---------------------------------------------------------------------------

@router.get("/unmatched-groups", response_model=list[UnmatchedGroup])
async def get_unmatched_groups(
    limit: int = 100,
    account: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[UnmatchedGroup]:
    """Get unmatched orders grouped by account + security name.

    Includes orders where:
    - instrument_id IS NULL (never matched)
    - match_status IS NULL (pre-migration, instrument linked but not validated)
    - match_status = 'unmatched' (explicitly unmatched)
    """
    unmatched_clause = (
        Order.instrument_id.is_(None)
        | (Order.match_status.is_(None))
        | (Order.match_status == "unmatched")
    )

    q = select(
        Order.account_name,
        Order.security_name,
        func.count().label("order_count"),
        func.min(Order.order_date).label("first_date"),
        func.max(Order.order_date).label("last_date"),
        func.coalesce(
            func.sum(
                case((Order.side == "Buy", Order.quantity), else_=-Order.quantity)
            ), 0.0
        ).label("net_qty"),
        func.coalesce(
            func.sum(
                case((Order.side == "Buy", Order.cost_proceeds_gbp), else_=0.0)
            ), 0.0
        ).label("buy_total"),
        func.coalesce(
            func.sum(
                case((Order.side == "Sell", Order.cost_proceeds_gbp), else_=0.0)
            ), 0.0
        ).label("sell_total"),
    ).where(unmatched_clause)

    if account:
        q = q.where(Order.account_name == account)

    q = q.group_by(
        Order.account_name,
        Order.security_name,
    ).order_by(
        func.count().desc()
    ).limit(limit)

    rows = (await session.execute(q)).all()

    groups: list[UnmatchedGroup] = []
    for row in rows:
        acct, sec_name, count, first_d, last_d, net_qty, buy_tot, sell_tot = row
        norm = normalise_name(sec_name)
        canonical = await resolve_canonical_account(session, "barclays_orders", acct)

        # Find best candidate
        candidates = await build_candidates(
            session, "barclays_orders", acct, sec_name
        )
        best_candidate: MatchCandidate | None = None
        candidate_count = len(candidates)

        if candidates:
            best_score = 0.0
            best_ev = {}
            for inst in candidates:  # Score all candidates so newly created historical instruments are always considered
                s, ev = score_candidate(inst, sec_name, acct, canonical)
                if s > best_score:
                    best_score = s
                    best_ev = ev
            if best_ev:
                best_candidate = MatchCandidate(
                    instrument_id=best_ev["instrument_id"],
                    security_name=best_ev["instrument_name"],
                    score=best_ev["final_score"],
                    method=determine_method(best_score, best_ev),
                )

        groups.append(UnmatchedGroup(
            group_key=f"barclays_orders|{acct}|{norm}",
            source="barclays_orders",
            account_name=acct,
            canonical_account_name=canonical,
            security_name=sec_name,
            normalised_name=norm,
            order_count=count,
            first_order_date=first_d.isoformat() if first_d else None,
            last_order_date=last_d.isoformat() if last_d else None,
            net_quantity=net_qty,
            buy_total_gbp=buy_tot,
            sell_total_gbp=sell_tot,
            candidate_count=candidate_count,
            best_candidate=best_candidate,
        ))

    return groups


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------

@router.get("/candidates")
async def get_candidates(
    security_name: str,
    account_name: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get ranked candidate instruments for a security name + account."""
    canonical = await resolve_canonical_account(session, "barclays_orders", account_name)
    candidates = await build_candidates(
        session, "barclays_orders", account_name, security_name
    )

    scored = []
    for inst in candidates[:20]:
        s, ev = score_candidate(inst, security_name, account_name, canonical)
        scored.append({
            "instrument_id": inst.id,
            "security_name": inst.security_name,
            "account_name": inst.account_name,
            "score": ev["final_score"],
            "method": determine_method(s, ev),
            "scores": ev.get("scores", {}),
            "is_closed": inst.closed_at is not None,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)

    return {
        "security_name": security_name,
        "account_name": account_name,
        "canonical_account_name": canonical,
        "candidates": scored,
    }


# ---------------------------------------------------------------------------
# Resolve group
# ---------------------------------------------------------------------------

@router.post("/resolve-group")
async def resolve_group(
    body: ResolveGroupBody,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Resolve an unmatched group to an instrument."""
    # Verify instrument exists
    inst = await session.get(Instrument, body.instrument_id)
    if inst is None:
        raise HTTPException(status_code=404, detail=f"Instrument {body.instrument_id} not found")

    norm_name = normalise_name(body.security_name)
    canonical = await resolve_canonical_account(session, body.source, body.account_name)

    # Create alias if requested
    if body.create_alias:
        alias = InstrumentAlias(
            instrument_id=body.instrument_id,
            source=body.source,
            source_account_name=body.account_name,
            canonical_account_name=canonical,
            source_security_name=body.security_name,
            source_security_name_norm=norm_name,
            alias_type="manual",
            confidence=1.0,
            created_by="admin",
            notes=body.reason or "Manual admin resolution",
        )
        session.add(alias)
        await session.flush()

    # Update matching orders
    q = select(Order).where(
        Order.source_account_name == body.account_name if hasattr(Order, "source_account_name")
        else Order.account_name == body.account_name,
        Order.security_name == body.security_name,
        Order.instrument_id.is_(None),
    )
    # Simpler query
    q = select(Order).where(
        Order.account_name == body.account_name,
        Order.security_name == body.security_name,
        Order.instrument_id.is_(None),
    )
    result = await session.execute(q)
    orders = list(result.scalars().all())

    affected = 0
    for order in orders:
        await write_audit(
            session, order,
            new_instrument_id=body.instrument_id,
            new_status="manual",
            method="admin_group_resolve",
            confidence=1.0,
            changed_by="admin",
            reason=body.reason or "Admin group resolution",
        )
        order.instrument_id = body.instrument_id
        order.match_status = "manual"
        order.match_method = "admin_group_resolve"
        order.match_confidence = 1.0
        order.matched_by = "admin"
        affected += 1

    await session.commit()

    return {
        "affected_orders": affected,
        "instrument_id": body.instrument_id,
        "alias_created": body.create_alias,
    }


# ---------------------------------------------------------------------------
# Resolve individual order
# ---------------------------------------------------------------------------

@router.post("/orders/{order_id}/resolve")
async def resolve_order_endpoint(
    order_id: int,
    body: ResolveOrderBody,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Resolve an individual order."""
    order = await session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    new_instrument_id = body.instrument_id
    new_status = body.match_status or ("manual" if body.instrument_id else "unmatched")

    if body.instrument_id is not None:
        inst = await session.get(Instrument, body.instrument_id)
        if inst is None:
            raise HTTPException(status_code=404, detail=f"Instrument {body.instrument_id} not found")

    await write_audit(
        session, order,
        new_instrument_id=new_instrument_id,
        new_status=new_status,
        method="admin_manual",
        changed_by="admin",
        reason=body.reason,
    )

    order.instrument_id = new_instrument_id
    order.match_status = new_status
    order.match_method = "admin_manual"
    order.match_confidence = 1.0 if new_instrument_id else None
    order.matched_by = "admin"

    await session.commit()

    return {
        "order_id": order_id,
        "instrument_id": new_instrument_id,
        "match_status": new_status,
    }


# ---------------------------------------------------------------------------
# Unmatch
# ---------------------------------------------------------------------------

@router.post("/orders/{order_id}/unmatch")
async def unmatch_order(
    order_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Clear instrument match for an order."""
    order = await session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    await write_audit(
        session, order,
        new_instrument_id=None,
        new_status="unmatched",
        method="admin_unmatch",
        changed_by="admin",
        reason="Admin unmatched",
    )

    order.instrument_id = None
    order.match_status = "unmatched"
    order.match_method = None
    order.match_confidence = None
    order.match_evidence = None
    order.matched_by = "admin"

    await session.commit()

    return {"order_id": order_id, "instrument_id": None, "match_status": "unmatched"}


# ---------------------------------------------------------------------------
# Ignore
# ---------------------------------------------------------------------------

@router.post("/ignore-group")
async def ignore_group(
    body: ResolveGroupBody,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Ignore an unmatched group."""
    q = select(Order).where(
        Order.account_name == body.account_name,
        Order.security_name == body.security_name,
        Order.instrument_id.is_(None),
    )
    result = await session.execute(q)
    orders = list(result.scalars().all())

    affected = 0
    for order in orders:
        await write_audit(
            session, order,
            new_instrument_id=None,
            new_status="ignored",
            method="admin_ignore",
            changed_by="admin",
            reason=body.reason or "Admin ignored group",
        )
        order.match_status = "ignored"
        order.match_method = "admin_ignore"
        order.matched_by = "admin"
        affected += 1

    await session.commit()
    return {"affected_orders": affected}


# ---------------------------------------------------------------------------
# Create historical instrument
# ---------------------------------------------------------------------------

@router.post("/create-instrument")
async def create_historical_instrument(
    body: CreateHistoricalInstrumentBody,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Create a new historical instrument for order-only securities.

    Generates a MANUAL:<slug> identifier if none provided.
    Creates the instrument, an alias, and links all matching unmatched orders.
    """
    import re
    norm_re = re.compile(r"[^a-z0-9]+")
    slug = norm_re.sub("-", body.security_name.lower().strip())[:64]
    identifier = body.identifier or f"MANUAL:{slug}"
    account_name = body.account_name or "Historical"

    # Check for duplicates
    existing = await session.execute(
        select(Instrument).where(
            Instrument.account_name == account_name,
            Instrument.identifier == identifier,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Instrument {identifier} already exists for account {account_name}",
        )

    inst = Instrument(
        account_name=account_name,
        identifier=identifier,
        security_name=body.security_name,
        is_cash=False,
        closed_at=dt.datetime.now(dt.UTC) if body.closed else None,
    )
    session.add(inst)
    await session.flush()

    # Create alias
    norm_name = normalise_name(body.security_name)
    alias = InstrumentAlias(
        instrument_id=inst.id,
        source="barclays_orders",
        source_account_name=account_name,
        canonical_account_name=account_name,
        source_security_name=body.security_name,
        source_security_name_norm=norm_name,
        alias_type="manual",
        confidence=1.0,
        created_by="admin",
        notes=body.reason or "Historical instrument created from Matching Admin",
    )
    session.add(alias)

    # Link all matching unmatched orders
    q = select(Order).where(
        Order.account_name == account_name,
        Order.security_name == body.security_name,
        Order.instrument_id.is_(None),
    )
    result = await session.execute(q)
    orders = list(result.scalars().all())

    affected = 0
    for order in orders:
        await write_audit(
            session, order,
            new_instrument_id=inst.id,
            new_status="manual",
            method="admin_historical_instrument",
            confidence=1.0,
            changed_by="admin",
            reason=body.reason or "Matched to newly created historical instrument",
        )
        order.instrument_id = inst.id
        order.match_status = "manual"
        order.match_method = "admin_historical_instrument"
        order.match_confidence = 1.0
        order.matched_by = "admin"
        affected += 1

    await session.commit()
    await session.refresh(inst)

    return {
        "instrument_id": inst.id,
        "identifier": identifier,
        "security_name": inst.security_name,
        "affected_orders": affected,
    }


@router.post("/orders/{order_id}/ignore")
async def ignore_order(
    order_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Ignore an individual order."""
    order = await session.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    await write_audit(
        session, order,
        new_instrument_id=None,
        new_status="ignored",
        method="admin_ignore",
        changed_by="admin",
        reason="Admin ignored order",
    )
    order.match_status = "ignored"
    order.match_method = "admin_ignore"
    order.matched_by = "admin"

    await session.commit()
    return {"order_id": order_id, "match_status": "ignored"}


# ---------------------------------------------------------------------------
# Backfill / dry-run
# ---------------------------------------------------------------------------

@router.post("/backfill", response_model=BackfillResult)
async def run_backfill(
    body: BackfillRequest,
    session: AsyncSession = Depends(get_session),
) -> BackfillResult:
    """Run matching backfill (dry-run or actual)."""
    if body.dry_run:
        result = await dry_run_resolve(
            session,
            source="barclays_orders",
            mode=body.mode,
            min_auto_confidence=body.min_auto_confidence,
        )
        return BackfillResult(
            dry_run=True,
            orders_examined=result["orders_examined"],
            would_auto_match=result["would_auto_match"],
            would_mark_review=result["would_mark_review"],
            would_remain_unmatched=result["would_remain_unmatched"],
            examples=result.get("examples", []),
        )
    else:
        result = await resolve_batch(
            session,
            source="barclays_orders",
            mode=body.mode,
            min_auto_confidence=body.min_auto_confidence,
        )
        return BackfillResult(
            dry_run=False,
            orders_examined=result["orders_examined"],
            actually_linked=result["orders_linked"],
            examples=result.get("results", [])[:20],
        )


# ---------------------------------------------------------------------------
# Account aliases
# ---------------------------------------------------------------------------

@router.get("/account-aliases", response_model=list[AccountAliasOut])
async def list_account_aliases(
    session: AsyncSession = Depends(get_session),
) -> list[AccountAliasOut]:
    result = await session.execute(select(AccountAlias))
    return list(result.scalars().all())


@router.post("/account-aliases", response_model=AccountAliasOut, status_code=201)
async def create_account_alias(
    body: AccountAliasIn,
    session: AsyncSession = Depends(get_session),
) -> AccountAliasOut:
    alias = AccountAlias(
        source=body.source,
        source_account_name=body.source_account_name,
        canonical_account_name=body.canonical_account_name,
        created_by="admin",
        notes=body.notes,
    )
    session.add(alias)
    await session.commit()
    await session.refresh(alias)
    return alias


@router.delete("/account-aliases/{alias_id}")
async def delete_account_alias(
    alias_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    alias = await session.get(AccountAlias, alias_id)
    if alias is None:
        raise HTTPException(status_code=404, detail=f"Account alias {alias_id} not found")
    await session.delete(alias)
    await session.commit()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Instrument aliases
# ---------------------------------------------------------------------------

@router.get("/instrument-aliases", response_model=list[InstrumentAliasOut])
async def list_instrument_aliases(
    session: AsyncSession = Depends(get_session),
) -> list[InstrumentAliasOut]:
    result = await session.execute(select(InstrumentAlias))
    return list(result.scalars().all())


@router.post("/instrument-aliases", response_model=InstrumentAliasOut, status_code=201)
async def create_instrument_alias(
    body: InstrumentAliasIn,
    session: AsyncSession = Depends(get_session),
) -> InstrumentAliasOut:
    # Verify instrument exists
    inst = await session.get(Instrument, body.instrument_id)
    if inst is None:
        raise HTTPException(status_code=404, detail=f"Instrument {body.instrument_id} not found")

    norm = normalise_name(body.source_security_name)
    alias = InstrumentAlias(
        instrument_id=body.instrument_id,
        source=body.source,
        source_account_name=body.source_account_name,
        canonical_account_name=body.canonical_account_name,
        source_security_name=body.source_security_name,
        source_security_name_norm=norm,
        alias_type=body.alias_type,
        confidence=body.confidence,
        created_by="admin",
        notes=body.notes,
    )
    session.add(alias)
    await session.commit()
    await session.refresh(alias)
    return alias


@router.delete("/instrument-aliases/{alias_id}")
async def delete_instrument_alias(
    alias_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    alias = await session.get(InstrumentAlias, alias_id)
    if alias is None:
        raise HTTPException(status_code=404, detail=f"Instrument alias {alias_id} not found")
    await session.delete(alias)
    await session.commit()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

@router.get("/reconciliation", response_model=list[ReconciliationRow])
async def get_reconciliation(
    session: AsyncSession = Depends(get_session),
) -> list[ReconciliationRow]:
    """Get per-instrument reconciliation rows."""
    instruments = (await session.execute(
        select(Instrument).where(Instrument.is_cash == False)  # noqa: E712
    )).scalars().all()

    rows: list[ReconciliationRow] = []
    for inst in instruments:
        # Latest snapshot
        snap_q = await session.execute(
            select(HoldingSnapshot)
            .where(HoldingSnapshot.instrument_id == inst.id)
            .order_by(HoldingSnapshot.id.desc())
            .limit(1)
        )
        latest_snap = snap_q.scalar_one_or_none()

        # Order stats
        order_q = await session.execute(
            select(
                func.count().label("total"),
                func.count(Order.instrument_id).label("matched"),
                func.coalesce(func.sum(
                    case((Order.side == "Buy", Order.quantity), else_=-Order.quantity)
                ), 0.0).label("net_qty"),
                func.coalesce(func.sum(
                    case((Order.side == "Buy", Order.cost_proceeds_gbp), else_=0.0)
                ), 0.0).label("buy_total"),
                func.coalesce(func.sum(
                    case((Order.side == "Sell", Order.cost_proceeds_gbp), else_=0.0)
                ), 0.0).label("sell_total"),
                func.coalesce(func.sum(
                    case(
                        (Order.is_drip == True and Order.side == "Buy", Order.cost_proceeds_gbp),  # noqa: E712
                        else_=0.0
                    )
                ), 0.0).label("drip_total"),
            ).where(Order.instrument_id == inst.id)
        )
        order_stats = order_q.one()

        # Match status summary
        status_summary: dict[str, int] = {}
        for status in ["auto_high", "auto_review", "manual", "ignored", "unmatched", "legacy_matched"]:
            cnt = (await session.execute(
                select(func.count()).where(
                    Order.instrument_id == inst.id,
                    Order.match_status == status,
                )
            )).scalar_one()
            if cnt > 0:
                status_summary[status] = cnt

        # Unmatched orders for likely same security
        unmatched_count = (await session.execute(
            select(func.count()).where(
                Order.instrument_id.is_(None),
                Order.account_name == inst.account_name,
            )
        )).scalar_one()

        # Determine status
        snap_qty = latest_snap.quantity if latest_snap else None
        order_qty = order_stats.net_qty
        qty_delta = (abs(snap_qty - order_qty) if snap_qty is not None and order_qty is not None else None)

        status = "ok"
        if unmatched_count > 0:
            status = "unmatched_orders"
        if qty_delta is not None and qty_delta > max(1, (snap_qty or 0) * 0.05):
            status = "quantity_mismatch"

        rows.append(ReconciliationRow(
            instrument_id=inst.id,
            security_name=inst.security_name,
            account_name=inst.account_name,
            is_closed=inst.closed_at is not None,
            latest_snapshot_date=latest_snap.batch.as_of_date.isoformat() if latest_snap else None,
            snapshot_quantity=snap_qty,
            order_derived_quantity=order_qty,
            quantity_delta=qty_delta,
            snapshot_book_cost_gbp=latest_snap.book_cost_gbp if latest_snap else None,
            order_net_cost_gbp=order_stats.buy_total,
            drip_total_gbp=order_stats.drip_total,
            buy_total_gbp=order_stats.buy_total,
            sell_total_gbp=order_stats.sell_total,
            unmatched_order_count=unmatched_count,
            matched_order_count=order_stats.matched,
            match_status_summary=status_summary,
            latest_value_gbp=latest_snap.value_gbp if latest_snap else None,
            status=status,
        ))

    return rows


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

@router.get("/audit", response_model=list[OrderMatchAuditOut])
async def get_audit_log(
    order_id: int | None = None,
    instrument_id: int | None = None,
    limit: int = 200,
    session: AsyncSession = Depends(get_session),
) -> list[OrderMatchAuditOut]:
    q = select(OrderMatchAudit).order_by(OrderMatchAudit.changed_at.desc())

    if order_id is not None:
        q = q.where(OrderMatchAudit.order_id == order_id)
    if instrument_id is not None:
        q = q.where(
            (OrderMatchAudit.old_instrument_id == instrument_id) |
            (OrderMatchAudit.new_instrument_id == instrument_id)
        )

    q = q.limit(limit)
    result = await session.execute(q)
    return list(result.scalars().all())

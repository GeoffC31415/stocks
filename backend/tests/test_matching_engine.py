"""Tests for the new matching engine and admin API."""
from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, AccountAlias, Instrument, InstrumentAlias, Order, OrderMatchAudit
from app.services.matching.normalisation import (
    character_similarity,
    is_etf,
    is_preference_share,
    issuer_prefix,
    instrument_type_compatibility,
    meaningful_tokens,
    normalise_name,
    token_similarity,
)
from app.services.matching.scoring import (
    classify_score,
    determine_method,
    score_candidate,
)


# ---------------------------------------------------------------------------
# Normalisation tests
# ---------------------------------------------------------------------------

class TestNormalisation:
    def test_basic_normalisation(self) -> None:
        # Normaliser keeps all words (including plc) but lowercases and strips punctuation
        assert normalise_name("Big Yellow Group PLC ORD 10P") == "big yellow group plc ord 10p"

    def test_ampersand(self) -> None:
        assert normalise_name("JPMorgan & Co") == "jpmorgan and co"

    def test_punctuation_stripping(self) -> None:
        # S&P becomes sandp because & -> and, then punctuation stripped
        assert normalise_name("Vanguard S&P 500 UCITS ETF") == "vanguard sandp 500 ucits etf"

    def test_numeric_tokens_preserved(self) -> None:
        """Numeric tokens must be preserved to distinguish share classes."""
        tokens = meaningful_tokens("Big Yellow Group PLC ORD 10P")
        assert "10p" in tokens

    def test_etf_detection(self) -> None:
        assert is_etf("iShares Core S&P 500 UCITS ETF") is True
        assert is_etf("Vanguard FTSE 100 UCITS ETF") is True
        assert is_etf("BP PLC ORD 25 3/4P") is False

    def test_preference_share_detection(self) -> None:
        assert is_preference_share("Aviva PLC 8 3/8% CUM IRRD PRF #1") is True
        assert is_preference_share("BP PLC 9% CUM 2ND PRF #1") is True
        assert is_preference_share("Big Yellow Group PLC ORD 10P") is False

    def test_issuer_prefix(self) -> None:
        # plc is now treated as a share-class indicator and stripped
        assert issuer_prefix("Big Yellow Group PLC ORD 10P") == "big yellow group"
        assert issuer_prefix("Vanguard Funds PLC VANGUARD S&P 500") == "vanguard funds"

    def test_type_compatibility(self) -> None:
        # ETF vs ETF
        assert instrument_type_compatibility("ETF A", "ETF B") == 1.0
        # ETF vs ordinary
        assert instrument_type_compatibility("ETF A", "BP PLC ORD 10P") < 0.5
        # Pref vs ordinary
        assert instrument_type_compatibility("PRF Shares", "ORD Shares") < 0.5

    def test_token_similarity(self) -> None:
        s = token_similarity("Big Yellow Group PLC ORD 10P", "Big Yellow Group PLC ORD 10P")
        assert s == 1.0

    def test_character_similarity(self) -> None:
        s = character_similarity("Vanguard FTSE", "Vanguard FTSE")
        assert s == 1.0
        s = character_similarity("Vanguard FTSE", "FTSE 100")
        assert s < 1.0

    def test_empty_name(self) -> None:
        assert normalise_name("") == ""
        assert normalise_name(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Scoring tests
# ---------------------------------------------------------------------------

class TestScoring:
    def test_exact_match_same_account(self) -> None:
        inst = Instrument(
            id=1,
            account_name="ID1585211-001 (Investment ISA)",
            identifier="ID1",
            security_name="Big Yellow Group PLC ORD 10P",
            is_cash=False,
        )
        score, evidence = score_candidate(
            inst,
            "Big Yellow Group PLC ORD 10P",
            "Investment ISA",
            "ID1585211-001 (Investment ISA)",
        )
        assert score >= 0.95
        assert evidence["scores"]["name_exact"] == 1.0
        assert evidence["scores"]["account"] == 1.0

    def test_exact_name_different_account(self) -> None:
        inst = Instrument(
            id=1,
            account_name="General Investment Account",
            identifier="ID1",
            security_name="Big Yellow Group PLC ORD 10P",
            is_cash=False,
        )
        score, evidence = score_candidate(
            inst,
            "Big Yellow Group PLC ORD 10P",
            "Investment ISA",
            "ID1585211-001 (Investment ISA)",
        )
        assert score >= 0.8
        assert evidence["scores"]["name_exact"] == 1.0
        assert evidence["scores"]["account"] == 0.0

    def test_closed_instrument_penalty(self) -> None:
        inst = Instrument(
            id=1,
            account_name="ID1585211-001 (Investment ISA)",
            identifier="ID1",
            security_name="Big Yellow Group PLC ORD 10P",
            is_cash=False,
            closed_at=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        )
        score_open, _ = score_candidate(
            Instrument(id=1, account_name="ID1585211-001 (Investment ISA)", identifier="ID1",
                       security_name="Big Yellow Group PLC ORD 10P", is_cash=False),
            "Big Yellow Group PLC ORD 10P",
            "Investment ISA",
            "ID1585211-001 (Investment ISA)",
        )
        score_closed, _ = score_candidate(
            inst,
            "Big Yellow Group PLC ORD 10P",
            "Investment ISA",
            "ID1585211-001 (Investment ISA)",
            order_date=dt.datetime(2023, 6, 1, tzinfo=dt.UTC),
        )
        assert score_closed < score_open

    def test_classify_score(self) -> None:
        assert classify_score(0.95) == "auto_high"
        assert classify_score(0.92) == "auto_high"
        assert classify_score(0.85) == "auto_review"
        assert classify_score(0.75) == "auto_review"
        assert classify_score(0.50) == "unmatched"

    def test_determine_method(self) -> None:
        ev_exact_account = {"scores": {"name_exact": 1.0, "account": 1.0, "token_similarity": 0.9}}
        assert determine_method(0.95, ev_exact_account) == "exact_account"

        ev_exact_cross = {"scores": {"name_exact": 1.0, "account": 0.0, "token_similarity": 0.9}}
        assert determine_method(0.85, ev_exact_cross) == "exact_cross_account"

        ev_fuzzy = {"scores": {"name_exact": 0.0, "account": 0.0, "token_similarity": 0.4}}
        assert determine_method(0.5, ev_fuzzy) == "fuzzy"


# ---------------------------------------------------------------------------
# Async integration tests for resolver
# ---------------------------------------------------------------------------

@pytest.fixture
async def async_db():
    """In-memory SQLite database for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


@pytest.mark.anyio
async def test_alias_match_wins_over_fuzzy(async_db: AsyncSession) -> None:
    """Manual alias should always win over fuzzy matching."""
    inst = Instrument(
        id=1,
        account_name="ID1585211-001 (Investment ISA)",
        identifier="ID1",
        security_name="Big Yellow Group PLC ORD 10P",
        is_cash=False,
    )
    async_db.add(inst)

    order = Order(
        id=1,
        order_import_batch_id=1,
        security_name="Big Yellow Group PLC ORD 10P",
        order_date=dt.datetime(2023, 6, 1, tzinfo=dt.UTC),
        order_status="Completed",
        account_name="Investment ISA",
        side="Buy",
        quantity=100.0,
        cost_proceeds_gbp=5000.0,
        country="UK",
        is_drip=False,
        order_fingerprint="fp1",
        match_status="unmatched",
    )
    async_db.add(order)

    alias = AccountAlias(
        source="barclays_orders",
        source_account_name="Investment ISA",
        canonical_account_name="ID1585211-001 (Investment ISA)",
    )
    async_db.add(alias)

    inst_alias = InstrumentAlias(
        instrument_id=1,
        source="barclays_orders",
        source_account_name="Investment ISA",
        canonical_account_name="ID1585211-001 (Investment ISA)",
        source_security_name="Big Yellow Group PLC ORD 10P",
        source_security_name_norm="big yellow group plc ord 10p",
        alias_type="manual",
        confidence=1.0,
    )
    async_db.add(inst_alias)
    await async_db.commit()

    from app.services.matching.resolver import resolve_order
    result = await resolve_order(async_db, order)

    assert result["instrument_id"] == 1
    assert result["match_status"] == "auto_high"
    # Alias match should resolve immediately
    assert result["match_method"] == "alias_exact"
    assert result["match_confidence"] == 1.0

    # Verify audit was written
    audit_count = (await async_db.execute(
        select(func.count()).select_from(OrderMatchAudit)
    )).scalar_one()
    assert audit_count >= 1


@pytest.mark.anyio
async def test_manual_status_not_overwritten(async_db: AsyncSession) -> None:
    """Orders with manual status should be skipped during auto resolution."""
    inst = Instrument(
        id=1,
        account_name="ID1585211-001 (Investment ISA)",
        identifier="ID1",
        security_name="Big Yellow Group PLC ORD 10P",
        is_cash=False,
    )
    async_db.add(inst)

    order = Order(
        id=1,
        order_import_batch_id=1,
        security_name="Big Yellow Group PLC ORD 10P",
        order_date=dt.datetime(2023, 6, 1, tzinfo=dt.UTC),
        order_status="Completed",
        account_name="Investment ISA",
        side="Buy",
        quantity=100.0,
        cost_proceeds_gbp=5000.0,
        country="UK",
        is_drip=False,
        order_fingerprint="fp1",
        match_status="manual",
        instrument_id=1,
    )
    async_db.add(order)
    await async_db.commit()

    from app.services.matching.resolver import resolve_order
    result = await resolve_order(async_db, order)

    assert result.get("skipped") is True
    assert result["match_status"] == "manual"


@pytest.mark.anyio
async def test_dry_run_does_not_persist(async_db: AsyncSession) -> None:
    """Dry run should not change order state."""
    inst = Instrument(
        id=1,
        account_name="ID1585211-001 (Investment ISA)",
        identifier="ID1",
        security_name="Big Yellow Group PLC ORD 10P",
        is_cash=False,
    )
    async_db.add(inst)

    order = Order(
        id=1,
        order_import_batch_id=1,
        security_name="Big Yellow Group PLC ORD 10P",
        order_date=dt.datetime(2023, 6, 1, tzinfo=dt.UTC),
        order_status="Completed",
        account_name="Investment ISA",
        side="Buy",
        quantity=100.0,
        cost_proceeds_gbp=5000.0,
        country="UK",
        is_drip=False,
        order_fingerprint="fp1",
        match_status="unmatched",
    )
    async_db.add(order)

    alias = AccountAlias(
        source="barclays_orders",
        source_account_name="Investment ISA",
        canonical_account_name="ID1585211-001 (Investment ISA)",
    )
    async_db.add(alias)

    inst_alias = InstrumentAlias(
        instrument_id=1,
        source="barclays_orders",
        source_account_name="Investment ISA",
        canonical_account_name="ID1585211-001 (Investment ISA)",
        source_security_name="Big Yellow Group PLC ORD 10P",
        source_security_name_norm="big yellow group plc ord 10p",
        alias_type="manual",
        confidence=1.0,
    )
    async_db.add(inst_alias)
    await async_db.commit()

    from app.services.matching.resolver import resolve_order
    result = await resolve_order(async_db, order, dry_run=True)

    # Order should still be unmatched in DB
    await async_db.refresh(order)
    assert order.match_status == "unmatched"
    assert order.instrument_id is None
    assert result["dry_run"] is True


@pytest.mark.anyio
async def test_batch_resolve_unmatched_only(async_db: AsyncSession) -> None:
    """Batch resolve should only process unmatched orders in unmatched_only mode."""
    inst = Instrument(
        id=1,
        account_name="ID1585211-001 (Investment ISA)",
        identifier="ID1",
        security_name="Big Yellow Group PLC ORD 10P",
        is_cash=False,
    )
    async_db.add(inst)

    # Manually matched order - should be skipped
    order1 = Order(
        id=1,
        order_import_batch_id=1,
        security_name="Big Yellow Group PLC ORD 10P",
        order_date=dt.datetime(2023, 6, 1, tzinfo=dt.UTC),
        order_status="Completed",
        account_name="Investment ISA",
        side="Buy",
        quantity=100.0,
        cost_proceeds_gbp=5000.0,
        country="UK",
        is_drip=False,
        order_fingerprint="fp1",
        match_status="manual",
        instrument_id=1,
    )
    async_db.add(order1)

    # Unmatched order - should be processed
    order2 = Order(
        id=2,
        order_import_batch_id=1,
        security_name="Big Yellow Group PLC ORD 10P",
        order_date=dt.datetime(2023, 7, 1, tzinfo=dt.UTC),
        order_status="Completed",
        account_name="Investment ISA",
        side="Buy",
        quantity=50.0,
        cost_proceeds_gbp=2500.0,
        country="UK",
        is_drip=False,
        order_fingerprint="fp2",
        match_status="unmatched",
    )
    async_db.add(order2)

    alias = AccountAlias(
        source="barclays_orders",
        source_account_name="Investment ISA",
        canonical_account_name="ID1585211-001 (Investment ISA)",
    )
    async_db.add(alias)

    inst_alias = InstrumentAlias(
        instrument_id=1,
        source="barclays_orders",
        source_account_name="Investment ISA",
        canonical_account_name="ID1585211-001 (Investment ISA)",
        source_security_name="Big Yellow Group PLC ORD 10P",
        source_security_name_norm="big yellow group plc ord 10p",
        alias_type="manual",
        confidence=1.0,
    )
    async_db.add(inst_alias)
    await async_db.commit()

    from app.services.matching.resolver import resolve_batch
    result = await resolve_batch(
        async_db,
        source="barclays_orders",
        mode="unmatched_only",
    )

    # Only order2 should have been examined and linked
    assert result["orders_examined"] == 1
    assert result["orders_linked"] >= 1

    # order1 should still be manual (never touched by unmatched_only mode)
    await async_db.refresh(order1)
    assert order1.match_status == "manual"

    # order2 should now be matched
    await async_db.refresh(order2)
    assert order2.instrument_id == 1


@pytest.mark.anyio
async def test_ignored_orders_not_overwritten(async_db: AsyncSession) -> None:
    """Ignored orders should never be auto-matched."""
    inst = Instrument(
        id=1,
        account_name="ID1585211-001 (Investment ISA)",
        identifier="ID1",
        security_name="Big Yellow Group PLC ORD 10P",
        is_cash=False,
    )
    async_db.add(inst)

    order = Order(
        id=1,
        order_import_batch_id=1,
        security_name="Big Yellow Group PLC ORD 10P",
        order_date=dt.datetime(2023, 6, 1, tzinfo=dt.UTC),
        order_status="Completed",
        account_name="Investment ISA",
        side="Buy",
        quantity=100.0,
        cost_proceeds_gbp=5000.0,
        country="UK",
        is_drip=False,
        order_fingerprint="fp1",
        match_status="ignored",
    )
    async_db.add(order)

    alias = AccountAlias(
        source="barclays_orders",
        source_account_name="Investment ISA",
        canonical_account_name="ID1585211-001 (Investment ISA)",
    )
    async_db.add(alias)

    inst_alias = InstrumentAlias(
        instrument_id=1,
        source="barclays_orders",
        source_account_name="Investment ISA",
        canonical_account_name="ID1585211-001 (Investment ISA)",
        source_security_name="Big Yellow Group PLC ORD 10P",
        source_security_name_norm="big yellow group plc ord 10p",
        alias_type="manual",
        confidence=1.0,
    )
    async_db.add(inst_alias)
    await async_db.commit()

    from app.services.matching.resolver import resolve_order
    result = await resolve_order(async_db, order)

    assert result.get("skipped") is True
    assert result["match_status"] == "ignored"
    await async_db.refresh(order)
    assert order.match_status == "ignored"
    assert order.instrument_id is None

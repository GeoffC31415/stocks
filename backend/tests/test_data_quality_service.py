import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data_quality_schemas import DataConfidence
from app.models import (
    Base,
    HoldingSnapshot,
    ImportBatch,
    Instrument,
    MarketPricePoint,
    Order,
    OrderImportBatch,
)
from app.services.data_quality_service import get_data_confidence
from app.services.market_data_service import SOURCE


@pytest.fixture
async def quality_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        session.add_all([Instrument(id=1, account_name="ISA", identifier="A", security_name="Asset", asset_class="Equity"),
                         Instrument(id=2, account_name="Other", identifier="B", security_name="Other")])
        session.add(OrderImportBatch(id=1, file_sha256="orders"))
        for batch_id, date in enumerate([dt.date(2026, 1, 1), dt.date(2026, 2, 1)], 1):
            session.add(ImportBatch(id=batch_id, as_of_date=date, file_sha256=str(batch_id)))
            session.add(HoldingSnapshot(import_batch_id=batch_id, instrument_id=1, investment_label="Asset", value_gbp=100, book_cost_gbp=100))
        for instrument_id, account in [(1, "ISA"), (None, "Other")]:
            session.add(Order(order_import_batch_id=1, instrument_id=instrument_id, account_name=account,
                              security_name="Asset", order_date=dt.datetime(2026, 1, 5), order_status="Executed",
                              side="buy", is_drip=True, cost_proceeds_gbp=1, order_fingerprint=account))
        await session.commit()
        yield session
    await engine.dispose()


async def test_scope_coverage_and_cache_only_get_are_truthful(quality_db):
    before = await quality_db.scalar(text("SELECT total_changes()"))
    result = DataConfidence(**await get_data_confidence(quality_db, account_name="ISA", today=dt.date(2026, 2, 5)))
    assert result.transactions.count == 1
    assert result.transactions.completeness == "unknown"
    assert result.transactions.first_date == dt.date(2026, 1, 5)
    assert result.transactions.unmatched_count == 0
    assert result.classification["asset_class"].classified_value_pct == 100
    assert result.classification["sector"].classified_value_pct == 0
    assert result.market_history.covered_pct == 0
    assert result.market_history.aligned_observations == 0
    assert not result.market_history.cache_gate_met
    assert result.market_history.validation_pending
    assert all("account=ISA" in item.action_href for item in result.attention)
    assert before == await quality_db.scalar(text("SELECT total_changes()"))


@pytest.mark.parametrize("currency,ready", [("GBP", True), ("GBp", True), ("USD", False)])
async def test_cached_thresholds_do_not_claim_provider_validation_and_missing_fx_is_not_cash(quality_db, currency, ready):
    instrument = await quality_db.get(Instrument, 1)
    instrument.ticker = "A"
    end = dt.date(2026, 2, 1)
    quality_db.add_all([MarketPricePoint(source=SOURCE, symbol="A", date=end - dt.timedelta(days=day),
                                        close=100, currency=currency) for day in range(-2, 126)])
    await quality_db.commit()
    data = await get_data_confidence(quality_db, account_name="ISA", today=end)
    assert data["market_history"]["cache_gate_met"] is ready
    assert data["market_history"]["aligned_observations"] == (126 if ready else 0)
    assert data["market_history"]["covered_pct"] == (100 if ready else 0)
    assert data["market_history"]["validation_pending"]


async def test_staleness_is_a_personal_rule_and_evidence_changes_with_tolerance(quality_db):
    recent = await get_data_confidence(quality_db, today=dt.date(2026, 2, 5))
    assert not any(item["id"] == "snapshot_freshness" for item in recent["attention"])
    stale = await get_data_confidence(quality_db, today=dt.date(2026, 3, 5))
    item = next(item for item in stale["attention"] if item["id"] == "snapshot_freshness")
    assert item["category"] == "rule" and item["dismissible"]
    changed = await get_data_confidence(quality_db, today=dt.date(2026, 3, 5), stale_after_days=20)
    assert next(row for row in changed["attention"] if row["id"] == "snapshot_freshness")["evidence_key"] != item["evidence_key"]
    with pytest.raises(ValueError):
        await get_data_confidence(quality_db, stale_after_days=0)


async def test_broken_calculation_cannot_be_dismissed_and_empty_is_not_healthy(quality_db):
    result = await get_data_confidence(quality_db, account_name="Empty", today=dt.date(2026, 2, 5))
    blocked = next(item for item in result["attention"] if item["id"] == "performance_unavailable")
    assert blocked["severity"] == "critical" and not blocked["dismissible"]
    assert result["transactions"]["first_date"] is None
    assert result["market_history"]["covered_pct"] is None
    assert result["metric_reasons"]

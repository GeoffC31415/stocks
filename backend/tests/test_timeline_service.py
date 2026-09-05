import datetime as dt

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, HoldingSnapshot, ImportBatch, Instrument, Order, OrderImportBatch
from app.services.timeline_service import get_timeline, get_timeline_source
from app.timeline_schemas import TimelineEvent, TimelineResponse


@pytest.fixture
async def timeline_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        session.add_all([Instrument(id=1, account_name="ISA", identifier="A", security_name="Asset"),
                         Instrument(id=2, account_name="Other", identifier="B", security_name="Other")])
        session.add(OrderImportBatch(id=1, file_sha256="orders", created_at=dt.datetime(2026, 1, 2)))
        for month in (1, 2):
            session.add(ImportBatch(id=month, as_of_date=dt.date(2026, month, 1), created_at=dt.datetime(2026, month, 3), file_sha256=str(month)))
            for instrument in (1, 2):
                session.add(HoldingSnapshot(import_batch_id=month, instrument_id=instrument, investment_label="Asset", value_gbp=100))
        for index, side in enumerate(["buy", "sell", "deposit", "withdrawal"], 1):
            session.add(Order(id=index, order_import_batch_id=1, instrument_id=1 if side in {"buy", "sell"} else None,
                              account_name="ISA", security_name="Recorded source", side=side, order_status="Completed",
                              order_date=dt.datetime(2026, 1, 10, index), cost_proceeds_gbp=10, order_fingerprint=str(index)))
        session.add(Order(id=5, order_import_batch_id=1, account_name="Other", security_name="Other", side="buy", order_status="Completed",
                          order_date=dt.datetime(2026, 1, 10), order_fingerprint="5"))
        session.add(Order(id=6, order_import_batch_id=1, account_name="ISA", security_name="Future", side="buy", order_status="Completed",
                          order_date=dt.datetime(2026, 2, 5), order_fingerprint="6"))
        await session.commit()
        yield session
    await engine.dispose()


async def test_event_types_and_source_ids_respect_account_window_without_writes(timeline_db):
    changes = await timeline_db.scalar(text("SELECT total_changes()"))
    timeline = TimelineResponse(**await get_timeline(timeline_db, account_name="ISA"))
    assert timeline.event_count == 8
    assert timeline.counts_by_kind == {"trade": 2, "deposit": 1, "withdrawal": 1, "snapshot": 2, "import": 2}
    assert not any(event.id in {"order:5", "order:6"} for event in timeline.events)
    assert timeline.scope.effective_end == dt.date(2026, 2, 1)
    assert all("account=ISA" in event.source_href for event in timeline.events)
    assert changes == await timeline_db.scalar(text("SELECT total_changes()"))


async def test_import_time_is_not_relabelled_as_the_valuation_date(timeline_db):
    events = (await get_timeline(timeline_db, account_name="ISA"))["events"]
    snapshot = next(event for event in events if event["id"] == "snapshot:1")
    imported = next(event for event in events if event["id"] == "import:1")
    assert snapshot["date"] == dt.date(2026, 1, 1)
    assert imported["date"] == dt.date(2026, 1, 3)
    assert imported["valuation_date"] == snapshot["date"]
    assert not any(event["id"] == "import:2" for event in events)  # After covered valuation.


async def test_instrument_filter_and_exact_source_lookup(timeline_db):
    events = (await get_timeline(timeline_db, account_name="ISA", instrument_id=1))["events"]
    assert {event["id"] for event in events if event["source_type"] == "order"} == {"order:1", "order:2"}
    source = TimelineEvent(**await get_timeline_source(timeline_db, "order", 1, "ISA"))
    assert source.kind == "trade"  # A purchase is not evidence of a deposit.
    assert source.details["Side"] == "buy"
    order_import = TimelineEvent(**await get_timeline_source(timeline_db, "order-import", 1, "ISA"))
    assert order_import.date == dt.date(2026, 1, 2)
    assert order_import.valuation_date is None
    assert order_import.id == "order-import:1"
    assert await get_timeline_source(timeline_db, "order", 1, "Other") is None
    assert await get_timeline_source(timeline_db, "import", 999, "ISA") is None

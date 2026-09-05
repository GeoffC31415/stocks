"""URL scope validation with synthetic memory-only data and no lifespan."""
import datetime as dt

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import get_session
from app.main import app
from app.models import Base, HoldingSnapshot, ImportBatch, Instrument


@pytest.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        instrument = Instrument(account_name="ISA & pension", identifier="SCOPE", security_name="Scope")
        session.add(instrument)
        await session.flush()
        for day in [dt.date(2025, 1, 1), dt.date(2026, 1, 1), dt.date(2026, 6, 30)]:
            batch = ImportBatch(as_of_date=day, file_sha256=day.isoformat(), filename="synthetic.csv")
            session.add(batch)
            await session.flush()
            session.add(HoldingSnapshot(instrument_id=instrument.id, import_batch_id=batch.id,
                                        investment_label="Scope", value_gbp=100, book_cost_gbp=100))
        await session.commit()

        async def override():
            yield session

        app.dependency_overrides[get_session] = override
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                         base_url="http://test") as handle:
                yield handle
        finally:
            app.dependency_overrides.pop(get_session, None)
    await engine.dispose()


@pytest.mark.parametrize("query", [
    "period=INVALID", "period=", "account_name=missing", "account_name=",
    "start=2026-02-01&end=2026-01-01", "start=2026-02-30", "start=2026-01-01",
    "period=1M&period=ALL",
])
async def test_reject_invalid_scope_instead_of_ignoring_it(client, query):
    response = await client.get(f"/api/portfolio/performance?include_benchmarks=false&{query}")
    assert response.status_code == 422


async def test_period_is_anchored_to_valuation_not_wall_clock(client):
    response = await client.get("/api/portfolio/performance", params={
        "account_name": "ISA & pension", "period": "YTD", "include_benchmarks": "false",
    })
    assert response.status_code == 200
    scope = response.json()["scope"]
    assert scope["requested_start"] == "2026-01-01"
    assert scope["effective_end"] == "2026-06-30"
    assert scope["account_name"] == "ISA & pension"


async def test_summary_and_instrument_list_share_account_scope(client):
    summary = await client.get("/api/portfolio/summary", params={"account_name": "ISA & pension"})
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["position_count"] == 1
    assert payload["invested_value_gbp"] == 100
    assert payload["scope"]["account_name"] == "ISA & pension"
    assert payload["scope"]["valuation_dates"] == [{"account_name": "ISA & pension", "date": "2026-06-30"}]
    empty = await client.get("/api/portfolio/summary", params={"account_name": "Empty"})
    assert empty.json()["total_value_gbp"] == 0
    assert empty.json()["position_count"] == 0
    instruments = await client.get("/api/instruments", params={"account_name": "Empty"})
    assert instruments.json() == []


async def test_confidence_endpoint_honours_scope_and_bounds_personal_rules(client):
    response = await client.get("/api/portfolio/data-confidence", params={"account_name": "ISA & pension", "period": "YTD"})
    assert response.status_code == 200
    assert response.json()["scope"]["account_name"] == "ISA & pension"
    assert response.json()["transactions"]["completeness"] == "unknown"
    invalid = await client.get("/api/portfolio/data-confidence", params={"stale_after_days": 0})
    assert invalid.status_code == 422


async def test_return_card_uses_same_shared_period(client):
    response = await client.get("/api/portfolio/returns", params={"period": "YTD"})
    assert response.status_code == 200
    assert response.json()["period_start"] == "2026-01-01"
    assert response.json()["period_end"] == "2026-06-30"

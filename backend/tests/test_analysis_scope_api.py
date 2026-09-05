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


async def test_return_card_uses_same_shared_period(client):
    response = await client.get("/api/portfolio/returns", params={"period": "YTD"})
    assert response.status_code == 200
    assert response.json()["period_start"] == "2026-01-01"
    assert response.json()["period_end"] == "2026-06-30"

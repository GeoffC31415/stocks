"""Allocation contract tests; all database access is in-memory."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import get_session
from app.main import app
from app.models import Base, HoldingSnapshot, ImportBatch, Instrument

GOLDEN = json.loads((Path(__file__).parent / "fixtures/allocation_golden.json").read_text())


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def client(db):
    async def override():
        yield db

    app.dependency_overrides[get_session] = override
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as handle:
            yield handle
    finally:
        app.dependency_overrides.pop(get_session, None)


async def test_empty_allocation_contract(client):
    response = await client.get("/api/portfolio/allocation")
    assert response.status_code == 200
    data = response.json()
    assert data["dimension"] == "asset_class"
    assert data["totalValue"] == 0
    assert data["holdings"] == data["categories"] == []
    assert data["hhi"] == data["top1Pct"] == data["top5Pct"] == 0
    assert data["cash_policy"] == "excluded_all_dimensions"
    assert data["classification"] == {
        "holding_count": 0,
        "classified_count": 0,
        "classified_count_pct": 0,
        "total_value_gbp": 0,
        "classified_value_gbp": 0,
        "classified_value_pct": 0,
    }
    assert "positive GBP" in data["denominator_description"]


async def seed(db, instruments):
    db.add(ImportBatch(id=1, as_of_date=dt.date(2026, 1, 1), file_sha256="a" * 64))
    db.add(ImportBatch(id=2, as_of_date=dt.date(2026, 2, 1), file_sha256="b" * 64))
    for row in instruments:
        db.add(
            Instrument(
                id=row["id"],
                account_name=row["account_name"],
                identifier=row["identifier"],
                security_name=row["security_name"],
                is_cash=row["is_cash"],
                closed_at=dt.datetime.fromisoformat(row["closed_at"]) if row["closed_at"] else None,
                asset_class=row["asset_class"],
                sector=row["sector"],
                region=row["region"],
            )
        )
        # Obsolete values must never leak into allocations; keep some accounts on batch 1.
        if row["account_name"] == "ISA":
            db.add(
                HoldingSnapshot(
                    import_batch_id=1,
                    instrument_id=row["id"],
                    investment_label="obsolete",
                    value_gbp=9999,
                    value_ccy="EUR",
                )
            )
        db.add(
            HoldingSnapshot(
                import_batch_id=2 if row["account_name"] == "ISA" else 1,
                instrument_id=row["id"],
                investment_label=row["security_name"],
                value_gbp=row["latest_value_gbp"],
                value_ccy=row["value_ccy"],
            )
        )
    await db.commit()


@pytest.mark.parametrize("case", GOLDEN)
async def test_legacy_golden_parity(client, db, case):
    await seed(db, case["instruments"])
    params = {"dimension": case["dimension"]}
    if case["account_name"] is not None:
        params["account_name"] = case["account_name"]
    response = await client.get("/api/portfolio/allocation", params=params)
    assert response.status_code == 200
    actual = response.json()
    assert {key: actual[key] for key in case["expected"]} == case["expected"]


@pytest.mark.parametrize(
    "dimension,labels",
    [
        ("account", {"ISA": 72, "SIPP": 32}),
        ("currency", {"USD": 62, "GBP": 42}),
    ],
)
async def test_snapshot_dimensions(client, db, dimension, labels):
    await seed(db, GOLDEN[0]["instruments"])
    response = await client.get("/api/portfolio/allocation", params={"dimension": dimension})
    assert response.status_code == 200
    data = response.json()
    assert {row["label"]: row["value"] for row in data["categories"]} == labels
    assert data["totalValue"] == 104
    assert data["classification"]["classified_count_pct"] == 100
    assert data["classification"]["classified_value_pct"] == 100


async def test_classification_completion_uses_filtered_count_and_gbp(client, db):
    await seed(db, GOLDEN[0]["instruments"])
    response = await client.get("/api/portfolio/allocation?dimension=asset_class&account_name=ISA")
    assert response.json()["classification"] == {
        "holding_count": 4,
        "classified_count": 1,
        "classified_count_pct": 25,
        "total_value_gbp": 72,
        "classified_value_gbp": 60,
        "classified_value_pct": 83.33,
    }


async def test_unknown_dimension_rejected(client):
    assert (await client.get("/api/portfolio/allocation?dimension=invalid")).status_code == 422

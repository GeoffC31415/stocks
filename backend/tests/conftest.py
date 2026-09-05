"""Target-set contracts use synthetic in-memory databases only."""

import datetime as dt

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import get_session
from app.main import app
from app.models import (
    Base,
    HoldingSnapshot,
    ImportBatch,
    Instrument,
    InstrumentGroup,
    InstrumentGroupMember,
)


@pytest.fixture
async def target_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        db.add(ImportBatch(id=1, as_of_date=dt.date(2026, 1, 1), file_sha256="t" * 64))
        for ident, account, value, cash in [
            (1, "ISA", 60, False),
            (2, "ISA", 40, False),
            (3, "SIPP", 100, False),
            (4, "ISA", 25, True),
        ]:
            db.add(
                Instrument(
                    id=ident,
                    account_name=account,
                    identifier=str(ident),
                    security_name=str(ident),
                    is_cash=cash,
                )
            )
            db.add(
                HoldingSnapshot(
                    import_batch_id=1,
                    instrument_id=ident,
                    investment_label=str(ident),
                    value_gbp=value,
                    value_ccy="GBP",
                )
            )
        db.add_all(
            [
                InstrumentGroup(id=1, name="Core", target_allocation_pct=50),
                InstrumentGroup(id=2, name="Satellite", target_allocation_pct=50),
            ]
        )
        db.add_all(
            [
                InstrumentGroupMember(group_id=1, instrument_id=1),
                InstrumentGroupMember(group_id=1, instrument_id=3),
                InstrumentGroupMember(group_id=2, instrument_id=2),
            ]
        )
        await db.commit()

        async def override():
            yield db

        app.dependency_overrides[get_session] = override
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                yield db, client
        finally:
            app.dependency_overrides.pop(get_session, None)
    await engine.dispose()



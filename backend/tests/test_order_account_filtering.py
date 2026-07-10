import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, Order, OrderImportBatch
from app.routers.orders import list_orders, order_positions


@pytest.fixture
async def async_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


async def add_order(
    session,
    *,
    account_name: str,
    security_name: str,
    order_date: dt.datetime,
    cost_gbp: float,
) -> None:
    batch = OrderImportBatch(
        file_sha256=f"{account_name}-{security_name}-{order_date.isoformat()}",
        filename=None,
        row_count=1,
    )
    session.add(batch)
    await session.flush()
    session.add(
        Order(
            order_import_batch_id=batch.id,
            security_name=security_name,
            order_date=order_date,
            order_status="Completed",
            account_name=account_name,
            side="Buy",
            quantity=1,
            cost_proceeds_gbp=cost_gbp,
            country="GB",
            is_drip=False,
            order_fingerprint=f"fp-{account_name}-{security_name}",
        )
    )
    await session.commit()


@pytest.mark.anyio
async def test_list_orders_filters_account_before_limit(async_db) -> None:
    await add_order(
        async_db,
        account_name="ISA",
        security_name="ISA Holding",
        order_date=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        cost_gbp=100,
    )
    await add_order(
        async_db,
        account_name="SIPP",
        security_name="Newer SIPP Holding",
        order_date=dt.datetime(2024, 2, 1, tzinfo=dt.UTC),
        cost_gbp=200,
    )

    orders = await list_orders(account_name="ISA", limit=1, session=async_db)

    assert [order.account_name for order in orders] == ["ISA"]
    assert [order.security_name for order in orders] == ["ISA Holding"]


@pytest.mark.anyio
async def test_order_positions_isolates_account_aggregation(async_db) -> None:
    order_date = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    await add_order(
        async_db,
        account_name="ISA",
        security_name="Shared Fund",
        order_date=order_date,
        cost_gbp=100,
    )
    await add_order(
        async_db,
        account_name="SIPP",
        security_name="Shared Fund",
        order_date=order_date + dt.timedelta(days=1),
        cost_gbp=900,
    )

    positions = await order_positions(account_name="ISA", session=async_db)

    assert len(positions) == 1
    assert positions[0].security_name == "Shared Fund"
    assert positions[0].total_buy_gbp == 100
    assert positions[0].order_count == 1

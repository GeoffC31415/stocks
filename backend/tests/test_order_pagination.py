import datetime as dt

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import get_session
from app.main import app
from app.models import (
    Base,
    Instrument,
    InstrumentGroup,
    InstrumentGroupMember,
    Order,
    OrderImportBatch,
)


@pytest.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        batch = OrderImportBatch(file_sha256="page", row_count=205)
        session.add(batch)
        await session.flush()
        for i in range(205):
            session.add(
                Order(
                    order_import_batch_id=batch.id,
                    security_name="Target" if i < 105 else "Other",
                    order_date=dt.datetime(2026, 1, 1, 23, 59),
                    order_status="Completed",
                    account_name="ISA",
                    side="Buy" if i < 105 else "Sell",
                    cost_proceeds_gbp=2000,
                    order_fingerprint=f"p{i}",
                )
            )
        await session.commit()

        async def override():
            yield session

        app.dependency_overrides[get_session] = override
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as handle:
                yield handle, session
        finally:
            app.dependency_overrides.pop(get_session, None)
    await engine.dispose()


async def test_page_filters_before_limit_stable_ties_full_totals(client):
    handle, _ = client
    query = {
        "search": "target",
        "kind": "buy",
        "account_name": "ISA",
        "from_date": "2026-01-01",
        "to_date": "2026-01-01",
        "limit": 100,
    }
    response = await handle.get("/api/orders/page", params=query)
    assert response.status_code == 200
    first = response.json()
    second = (await handle.get("/api/orders/page", params={**query, "offset": 100})).json()
    assert [o["id"] for o in first["items"] + second["items"]] == list(range(105, 0, -1))
    assert first["total_count"] == second["total_count"] == 105
    assert first["totals"] == second["totals"]
    assert first["totals"]["buy_gbp"] == 210000
    assert first["has_more"] is True
    assert second["has_more"] is False


async def test_legacy_side_filter_before_limit(client):
    handle, _ = client
    response = await handle.get("/api/orders", params={"side": "buy", "limit": 2})
    assert [o["id"] for o in response.json()] == [105, 104]


async def test_stored_proxy_ignores_current_threshold(client):
    handle, session = client
    order = await session.get(Order, 1)
    order.is_drip = True
    order.cost_proceeds_gbp = None
    await session.commit()
    data = (
        await handle.get("/api/orders/page", params={"kind": "drip", "drip_threshold": 0})
    ).json()
    assert [o["id"] for o in data["items"]] == [1]
    assert data["items"][0]["is_drip"] is True
    assert data["totals"]["drip_gbp"] is None
    assert data["totals_reasons"]["drip_gbp"] == "missing_amounts"
    assert data["items"][0]["cost_proceeds_gbp_reason"] == "missing_amounts"
    assert "Stored import-time" in data["classification_basis"]


async def test_linked_search_group_ids_and_exact_account(client):
    handle, session = client
    instrument = Instrument(
        account_name="ISA", identifier="GB-UNIQUE", ticker="XYZ.L", security_name="Linked name"
    )
    group = InstrumentGroup(name="Technology")
    session.add_all([instrument, group])
    await session.flush()
    session.add(InstrumentGroupMember(group_id=group.id, instrument_id=instrument.id))
    order = await session.get(Order, 1)
    order.instrument_id = instrument.id
    order.cost_proceeds_gbp = 10  # Explicit false purchase is not retrospectively DRIP.
    await session.commit()
    for params in [
        {"search": "xyz.l"},
        {"search": "gb-unique"},
        {"search": "linked name"},
        {"instrument_ids": instrument.id},
        {"group_ids": group.id},
    ]:
        data = (
            await handle.get("/api/orders/page", params={**params, "kind": "buy", "limit": 1})
        ).json()
        assert [o["id"] for o in data["items"]] == [1]
        assert data["total_count"] == 1
        assert data["items"][0]["is_drip"] is False
    data = (await handle.get("/api/orders/page", params={"account_name": "IS"})).json()
    assert data["total_count"] == 0 and data["totals"]["buy_gbp"] == 0


@pytest.mark.parametrize(
    "amounts,reason",
    [
        ([float("inf")], "non_finite_amounts"),
        ([float("-inf")], "non_finite_amounts"),
        ([float("inf"), float("-inf")], "non_finite_amounts"),
        ([1e308, 1e308], "non_finite_total"),
    ],
)
async def test_nonfinite_amounts_and_overflow_are_explained(client, amounts, reason):
    import json

    from sqlalchemy import event

    handle, session = client
    for index, amount in enumerate(amounts, 1):
        order = await session.get(Order, index)
        order.cost_proceeds_gbp = amount
    await session.commit()
    statements = []
    def listener(*args):
        statements.append(args[2])
    engine = session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", listener)
    try:
        # Bad amounts are off-page: explanations still derive from all matching rows.
        data = (await handle.get("/api/orders/page", params={"kind": "buy", "limit": 1})).json()
    finally:
        event.remove(engine, "before_cursor_execute", listener)
    assert len(statements) == 1
    assert data["items"][0]["cost_proceeds_gbp"] == 2000
    assert data["totals"]["buy_gbp"] is None
    assert data["totals_reasons"]["buy_gbp"] == reason
    last = (await handle.get("/api/orders/page", params={"kind": "buy", "offset": 104})).json()
    if reason == "non_finite_amounts":
        assert last["items"][0]["cost_proceeds_gbp"] is None
        assert last["items"][0]["cost_proceeds_gbp_reason"] == reason
    json.dumps(last, allow_nan=False)


async def test_missing_amount_reason_on_another_page(client):
    handle, session = client
    order = await session.get(Order, 1)
    order.cost_proceeds_gbp = None
    await session.commit()
    data = (await handle.get("/api/orders/page", params={"kind": "buy", "limit": 1})).json()
    assert data["items"][0]["cost_proceeds_gbp"] == 2000
    assert data["totals"]["buy_gbp"] is None
    assert data["totals_reasons"] == {
        "buy_gbp": "missing_amounts",
        "sell_gbp": None,
        "drip_gbp": None,
    }


async def test_null_totals_empty_page_and_validation(client):
    handle, session = client
    order = await session.get(Order, 1)
    order.cost_proceeds_gbp = None
    await session.commit()
    response = await handle.get("/api/orders/page", params={"offset": 999})
    data = response.json()
    assert data["items"] == [] and data["total_count"] == 205
    assert data["totals"]["buy_gbp"] is None
    assert data["totals"]["sell_gbp"] == 200000
    assert data["has_more"] is False
    for params in [
        {"limit": 0},
        {"offset": -1},
        {"kind": "unknown"},
        {"from_date": "2026-02-01", "to_date": "2026-01-01"},
    ]:
        assert (await handle.get("/api/orders/page", params=params)).status_code == 422


@pytest.mark.parametrize("query", ["instrument_ids=01", "instrument_ids=1e2", "group_ids=-1", "offset=00", "from_date=20260101", "kind=buy&kind=sell"])
async def test_noncanonical_or_ambiguous_page_tokens_are_rejected(client, query):
    handle,_=client
    response=await handle.get("/api/orders/page?"+query)
    assert response.status_code==422

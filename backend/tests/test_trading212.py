import datetime as dt

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.database import get_session
from app.main import app
from app.models import Base, HoldingSnapshot, Instrument, Order
from app.routers.trading212 import get_trading212_client, require_local_origin
from app.services.trading212 import (
    Trading212Client,
    Trading212CurrencyError,
    historical_orders_to_rows,
    positions_to_rows,
    sync_order_history,
    sync_portfolio_snapshot,
)

ACCOUNT_NAME = "Trading 212"


def test_positions_to_rows_maps_primary_currency_values_and_cash() -> None:
    positions = [
        {
            "averagePricePaid": 80.0,
            "currentPrice": 100.0,
            "instrument": {
                "currency": "USD",
                "isin": "US0378331005",
                "name": "Apple Inc.",
                "ticker": "AAPL_US_EQ",
            },
            "quantity": 2.5,
            "walletImpact": {
                "currency": "GBP",
                "currentValue": 195.0,
                "totalCost": 160.0,
                "unrealizedProfitLoss": 35.0,
            },
        }
    ]
    account = {
        "currency": "GBP",
        "cash": {
            "availableToTrade": 100.0,
            "inPies": 20.0,
            "reservedForOrders": 5.0,
        },
    }

    rows = positions_to_rows(positions, account, account_name=ACCOUNT_NAME)

    assert len(rows) == 2
    holding, cash = rows
    assert holding.account_name == ACCOUNT_NAME
    assert holding.identifier == "US0378331005"
    assert holding.investment == "Apple Inc."
    assert holding.quantity == 2.5
    assert holding.last_price == 100.0
    assert holding.last_price_ccy == "USD"
    assert holding.value_gbp == 195.0
    assert holding.book_cost_gbp == 160.0
    assert holding.pct_change == pytest.approx(21.875)
    assert cash.identifier == "CASH"
    assert cash.is_cash is True
    assert cash.value_gbp == 125.0


def test_positions_to_rows_rejects_non_gbp_account() -> None:
    with pytest.raises(Trading212CurrencyError, match="GBP"):
        positions_to_rows([], {"currency": "EUR", "cash": {}}, account_name=ACCOUNT_NAME)


def test_positions_without_account_scope_do_not_invent_cash() -> None:
    positions = [
        {
            "instrument": {"currency": "GBP", "isin": "GB00TEST", "name": "Test"},
            "quantity": 1,
            "walletImpact": {"currency": "GBP", "currentValue": 10, "totalCost": 9},
        }
    ]

    rows = positions_to_rows(positions, {"currency": "GBP"}, account_name=ACCOUNT_NAME)

    assert len(rows) == 1
    assert all(not row.is_cash for row in rows)


def test_positions_fail_closed_when_provider_row_has_no_identifier() -> None:
    positions = [
        {
            "instrument": {"currency": "GBP", "name": "Broken"},
            "quantity": 1,
            "walletImpact": {"currency": "GBP", "currentValue": 10, "totalCost": 9},
        }
    ]

    with pytest.raises(ValueError, match="position"):
        positions_to_rows(positions, {"currency": "GBP"}, account_name=ACCOUNT_NAME)


def test_historical_orders_to_rows_maps_only_filled_trade_events() -> None:
    items = [
        {
            "fill": {
                "id": 1,
                "filledAt": "2026-09-05T10:11:12Z",
                "quantity": 1.25,
                "type": "TRADE",
                "walletImpact": {"currency": "GBP", "netValue": -101.5},
            },
            "order": {
                "instrument": {"name": "Apple Inc.", "ticker": "AAPL_US_EQ"},
                "side": "BUY",
                "status": "FILLED",
            },
        },
        {
            "fill": {
                "filledAt": "2026-09-06T10:11:12Z",
                "quantity": 1,
                "type": "STOCK_SPLIT",
                "walletImpact": {"currency": "GBP", "netValue": 0},
            },
            "order": {
                "instrument": {"name": "Apple Inc.", "ticker": "AAPL_US_EQ"},
                "side": "BUY",
                "status": "FILLED",
            },
        },
    ]

    rows = historical_orders_to_rows(items, account_name=ACCOUNT_NAME)

    assert len(rows) == 1
    row = rows[0]
    assert row.security_name == "Apple Inc."
    assert row.order_date == dt.datetime(2026, 9, 5, 10, 11, 12, tzinfo=dt.UTC)
    assert row.order_status == "Completed"
    assert row.account_name == ACCOUNT_NAME
    assert row.side == "Buy"
    assert row.quantity == 1.25
    assert row.cost_proceeds_gbp == 101.5
    assert row.is_drip is False


def test_historical_orders_keeps_trade_fill_from_cancelled_order() -> None:
    items = [
        {
            "fill": {
                "id": 1,
                "filledAt": "2026-09-05T10:11:12Z",
                "quantity": 1,
                "type": "TRADE",
                "walletImpact": {"currency": "GBP", "netValue": 10},
            },
            "order": {
                "instrument": {"name": "Test plc"},
                "side": "SELL",
                "status": "CANCELLED",
            },
        }
    ]

    rows = historical_orders_to_rows(items, account_name=ACCOUNT_NAME)

    assert len(rows) == 1
    assert rows[0].side == "Sell"


def test_historical_orders_fail_closed_for_malformed_trade_fill() -> None:
    items = [
        {
            "fill": {
                "filledAt": "not-a-date",
                "type": "TRADE",
                "walletImpact": {"currency": "GBP", "netValue": 10},
            },
            "order": {"instrument": {"name": "Test plc"}, "side": "BUY"},
        }
    ]

    with pytest.raises(ValueError, match="order fill"):
        historical_orders_to_rows(items, account_name=ACCOUNT_NAME)


def test_historical_orders_preserve_fill_id_for_deduplication() -> None:
    item = {
        "fill": {
            "id": 123,
            "filledAt": "2026-09-05T10:11:12Z",
            "quantity": 1,
            "type": "TRADE",
            "walletImpact": {"currency": "GBP", "netValue": 10},
        },
        "order": {"instrument": {"name": "Test plc"}, "side": "BUY"},
    }

    rows = historical_orders_to_rows([item], account_name=ACCOUNT_NAME)

    assert rows[0].source_event_id == "123"


@pytest.mark.parametrize("fill_id", ["", "   ", [], {}])
def test_historical_orders_reject_malformed_fill_ids(fill_id) -> None:
    item = {
        "fill": {
            "id": fill_id,
            "filledAt": "2026-09-05T10:11:12Z",
            "quantity": 1,
            "type": "TRADE",
            "walletImpact": {"currency": "GBP", "netValue": 10},
        },
        "order": {"instrument": {"name": "Test plc"}, "side": "BUY"},
    }

    with pytest.raises(ValueError, match="order fill"):
        historical_orders_to_rows([item], account_name=ACCOUNT_NAME)


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_historical_orders_reject_non_finite_values(bad_value: float) -> None:
    item = {
        "fill": {
            "id": 123,
            "filledAt": "2026-09-05T10:11:12Z",
            "quantity": bad_value,
            "type": "TRADE",
            "walletImpact": {"currency": "GBP", "netValue": 10},
        },
        "order": {"instrument": {"name": "Test plc"}, "side": "BUY"},
    }

    with pytest.raises(ValueError, match="order fill"):
        historical_orders_to_rows([item], account_name=ACCOUNT_NAME)


@pytest.mark.asyncio
async def test_client_uses_basic_auth_and_follows_order_pagination() -> None:
    requests: list[httpx.Request] = []
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"].startswith("Basic ")
        if request.url.path.endswith("/history/orders") and "cursor" not in request.url.params:
            return httpx.Response(
                200,
                json={
                    "items": [{"order": {"id": 1}}],
                    "nextPagePath": "/api/v0/equity/history/orders?cursor=123&limit=50",
                },
            )
        if request.url.path.endswith("/history/orders"):
            return httpx.Response(200, json={"items": [{"order": {"id": 2}}]})
        raise AssertionError(f"Unexpected request: {request.url}")

    client = Trading212Client(
        api_key="test-key",
        api_secret="test-secret",
        transport=httpx.MockTransport(handler),
        page_delay=10.1,
        sleep=fake_sleep,
    )

    items = await client.fetch_historical_orders()

    assert [item["order"]["id"] for item in items] == [1, 2]
    assert len(requests) == 2
    assert delays == [10.1]


@pytest.mark.asyncio
async def test_client_rejects_external_pagination_url() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"items": [], "nextPagePath": "https://attacker.invalid/steal"},
        )

    client = Trading212Client(
        api_key="test-key",
        api_secret="test-secret",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ValueError, match="pagination"):
        await client.fetch_historical_orders()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "next_path",
    [
        "/api/v0/equity/history/orders-evil?cursor=1&limit=50",
        "/api/v0/equity/history/orders?cursor=1&limit=51",
        "/api/v0/equity/history/orders?cursor=bad&limit=50",
        "/api/v0/equity/history/orders?cursor=1&limit=50&unexpected=1",
        "/api/v0/equity/history/orders?cursor=%31&limit=50",
        "/api/v0/equity/history/orders?cursor=1&limit=50&",
        "/api/v0/equity/history/orders?cursor=1000000000000000001&limit=50",
    ],
)
async def test_client_rejects_invalid_pagination_path(next_path: str) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": [], "nextPagePath": next_path})

    client = Trading212Client(
        api_key="test-key",
        api_secret="test-secret",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ValueError, match="pagination"):
        await client.fetch_historical_orders()


@pytest.mark.asyncio
async def test_client_rejects_non_object_order_items() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": ["bad-entry"]})

    client = Trading212Client(
        api_key="test-key",
        api_secret="test-secret",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ValueError, match="order-history"):
        await client.fetch_historical_orders()


def test_settings_accept_trading212_read_only_credentials() -> None:
    configured = Settings(
        _env_file=None,
        trading212_api_key="key",
        trading212_api_secret="secret",
    )

    assert configured.trading212_api_key is not None
    assert configured.trading212_api_secret is not None
    assert configured.trading212_api_key.get_secret_value() == "key"
    assert configured.trading212_api_secret.get_secret_value() == "secret"
    assert configured.trading212_account_name == "Trading 212"


def test_local_origin_guard_rejects_remote_webpage() -> None:
    request = httpx.Request(
        "POST",
        "http://localhost:8000/api/trading212/sync/orders",
        headers={"Origin": "https://attacker.invalid"},
    )

    with pytest.raises(HTTPException) as exc_info:
        require_local_origin(request)

    assert exc_info.value.status_code == 403


def test_local_origin_guard_accepts_local_frontend() -> None:
    request = httpx.Request(
        "POST",
        "http://localhost:8000/api/trading212/sync/orders",
        headers={"Origin": "http://localhost:5173"},
    )

    require_local_origin(request)


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:9999",
        "https://localhost:5173",
        "http://127.0.0.1:3000",
        "HTTP://LOCALHOST:5173",
        "http://localhost:5173/",
    ],
)
def test_local_origin_guard_rejects_untrusted_local_ports_and_schemes(origin: str) -> None:
    request = httpx.Request(
        "POST",
        "http://localhost:8000/api/trading212/sync/orders",
        headers={"Origin": origin},
    )

    with pytest.raises(HTTPException) as exc_info:
        require_local_origin(request)

    assert exc_info.value.status_code == 403


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_positions_reject_non_finite_values(bad_value: float) -> None:
    positions = [
        {
            "instrument": {"currency": "GBP", "isin": "GB00TEST", "name": "Test"},
            "quantity": bad_value,
            "walletImpact": {"currency": "GBP", "currentValue": 10, "totalCost": 9},
        }
    ]

    with pytest.raises(ValueError, match="numeric"):
        positions_to_rows(positions, {"currency": "GBP"}, account_name=ACCOUNT_NAME)


def test_positions_reject_malformed_cash_bucket() -> None:
    with pytest.raises(ValueError, match="cash"):
        positions_to_rows(
            [],
            {
                "currency": "GBP",
                "cash": {
                    "availableToTrade": "bad",
                    "inPies": 0,
                    "reservedForOrders": 0,
                },
            },
            account_name=ACCOUNT_NAME,
        )


@pytest.mark.parametrize("cash", [None, "invalid", []])
def test_positions_reject_missing_cash_from_successful_account_summary(cash) -> None:
    with pytest.raises(ValueError, match="cash"):
        positions_to_rows(
            [],
            {"currency": "GBP", "cash": cash},
            account_name=ACCOUNT_NAME,
            require_cash=True,
        )


def test_positions_reject_successful_summary_without_cash_key() -> None:
    with pytest.raises(ValueError, match="cash"):
        positions_to_rows(
            [],
            {"currency": "GBP"},
            account_name=ACCOUNT_NAME,
            require_cash=True,
        )


class FakeTrading212Client:
    async def fetch_account_summary(self):
        return {
            "currency": "GBP",
            "cash": {"availableToTrade": 25, "inPies": 0, "reservedForOrders": 0},
        }

    async def fetch_positions(self):
        return [
            {
                "currentPrice": 10,
                "quantity": 3,
                "instrument": {
                    "currency": "GBP",
                    "isin": "GB00TEST0001",
                    "name": "Test plc",
                    "ticker": "TEST_EQ",
                },
                "walletImpact": {
                    "currency": "GBP",
                    "currentValue": 30,
                    "totalCost": 20,
                    "unrealizedProfitLoss": 10,
                },
            }
        ]

    async def fetch_historical_orders(self):
        return [
            {
                "fill": {
                    "id": 1,
                    "filledAt": "2026-09-01T12:00:00Z",
                    "quantity": 3,
                    "type": "TRADE",
                    "walletImpact": {"currency": "GBP", "netValue": -20},
                },
                "order": {
                    "instrument": {"name": "Test plc", "ticker": "TEST_EQ"},
                    "side": "BUY",
                    "status": "FILLED",
                },
            }
        ]


class PortfolioOnlyTrading212Client(FakeTrading212Client):
    async def fetch_account_summary(self):
        request = httpx.Request("GET", "https://live.trading212.com/api/v0/equity/account/summary")
        response = httpx.Response(403, request=request)
        raise httpx.HTTPStatusError("forbidden", request=request, response=response)


@pytest.mark.asyncio
async def test_account_summary_403_preserves_prior_cash_holding() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        await sync_portfolio_snapshot(
            session,
            FakeTrading212Client(),
            account_name=ACCOUNT_NAME,
        )
        fallback_batch, summary = await sync_portfolio_snapshot(
            session,
            PortfolioOnlyTrading212Client(),
            account_name=ACCOUNT_NAME,
            force=True,
        )
        cash = (
            await session.execute(
                select(Instrument).where(
                    Instrument.account_name == ACCOUNT_NAME,
                    Instrument.identifier == "CASH",
                )
            )
        ).scalar_one()
        fallback_cash_snapshots = list(
            (
                await session.execute(
                    select(HoldingSnapshot)
                    .join(Instrument)
                    .where(
                        HoldingSnapshot.import_batch_id == fallback_batch.id,
                        Instrument.identifier == "CASH",
                    )
                )
            ).scalars()
        )

    await engine.dispose()

    assert cash.closed_at is None
    assert fallback_cash_snapshots == []
    assert all(closed["identifier"] != "CASH" for closed in summary["closed"])


@pytest.mark.parametrize("bad_value", [True, False])
def test_positions_reject_boolean_cash_values(bad_value: bool) -> None:
    with pytest.raises(ValueError, match="cash"):
        positions_to_rows(
            [],
            {
                "currency": "GBP",
                "cash": {
                    "availableToTrade": bad_value,
                    "inPies": 0,
                    "reservedForOrders": 0,
                },
            },
            account_name=ACCOUNT_NAME,
            require_cash=True,
        )


@pytest.mark.asyncio
async def test_sync_portfolio_omits_cash_when_account_scope_is_forbidden() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        _, summary = await sync_portfolio_snapshot(
            session,
            PortfolioOnlyTrading212Client(),
            account_name=ACCOUNT_NAME,
        )
        snapshots = list((await session.execute(select(HoldingSnapshot))).scalars())

    await engine.dispose()

    assert summary["row_count"] == 1
    assert len(snapshots) == 1


@pytest.mark.asyncio
async def test_sync_imports_snapshot_and_links_order_to_instrument() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        batch, summary = await sync_portfolio_snapshot(
            session,
            FakeTrading212Client(),
            account_name=ACCOUNT_NAME,
        )
        order_batch, inserted = await sync_order_history(
            session,
            FakeTrading212Client(),
            account_name=ACCOUNT_NAME,
        )
        instruments = list((await session.execute(select(Instrument))).scalars())
        snapshots = list((await session.execute(select(HoldingSnapshot))).scalars())
        orders = list((await session.execute(select(Order))).scalars())

    await engine.dispose()

    assert batch.as_of_date == dt.datetime.now(dt.UTC).date()
    assert summary["row_count"] == 2
    assert len(instruments) == 2
    assert len(snapshots) == 2
    assert order_batch.row_count == 1
    assert inserted == 1
    assert len(orders) == 1
    assert orders[0].instrument_id == next(
        instrument.id for instrument in instruments if instrument.identifier == "GB00TEST0001"
    )
    assert orders[0].is_drip is False


@pytest.mark.asyncio
async def test_trading212_sync_endpoints_use_configured_reader(monkeypatch) -> None:
    from app.routers import trading212 as trading212_router

    monkeypatch.setattr(trading212_router.settings, "trading212_api_key", None)
    monkeypatch.setattr(trading212_router.settings, "trading212_api_secret", None)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        async def override_session():
            yield session

        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_trading212_client] = FakeTrading212Client
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                status_response = await client.get("/api/trading212/status")
                portfolio_response = await client.post("/api/trading212/sync/portfolio")
                orders_response = await client.post("/api/trading212/sync/orders")
        finally:
            app.dependency_overrides.pop(get_session, None)
            app.dependency_overrides.pop(get_trading212_client, None)

    await engine.dispose()

    assert status_response.status_code == 200
    assert status_response.json()["configured"] is False
    assert portfolio_response.status_code == 201
    assert portfolio_response.json()["summary"]["row_count"] == 2
    assert orders_response.status_code == 201
    assert orders_response.json()["row_count"] == 1

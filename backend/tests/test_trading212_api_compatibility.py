"""Compact, synthetic checks against the documented Trading 212 API contract."""

import httpx
import pytest

from app.services import trading212 as service

# Official Fill.type enum; keep this independent from the implementation allowlist.
FILL_TYPES = (
    "TRADE", "STOCK_SPLIT", "STOCK_DISTRIBUTION", "FOP", "FOP_CORRECTION",
    "CUSTOM_STOCK_DISTRIBUTION", "EQUITY_RIGHTS", "SCRIP_STOCK_DIVIDENDS",
    "STOCK_DIVIDENDS", "STOCK_ACQUISITION", "CASH_AND_STOCK_ACQUISITION", "SPIN_OFF",
)


def trade(side="BUY", quantity=1):
    return {
        "order": {"instrument": {"name": "Synthetic plc"}, "side": side},
        "fill": {
            "type": "TRADE", "id": 1, "filledAt": "2026-01-01T12:00:00Z",
            "quantity": quantity, "walletImpact": {"currency": "GBP", "netValue": 10},
        },
    }


def test_documented_fill_categories_preserve_corporate_action_skip():
    assert frozenset(FILL_TYPES) == service.DOCUMENTED_FILL_TYPES
    for kind in FILL_TYPES:
        item = trade()
        item["fill"]["type"] = kind
        rows = service.historical_orders_to_rows([item], account_name="Synthetic")
        assert len(rows) == (1 if kind == "TRADE" else 0), kind
    # Corporate actions are deliberately not validated/fabricated as trade rows.
    assert service.historical_orders_to_rows(
        [{"fill": {"type": kind}} for kind in FILL_TYPES if kind != "TRADE"],
        account_name="Synthetic",
    ) == []


@pytest.mark.parametrize("kind", ["PRIVATE_TYPE_SENTINEL", None, [], {}])
def test_unknown_fill_categories_reject_safely(kind):
    item = trade()
    item["fill"]["type"] = kind
    with pytest.raises(service.Trading212DataError) as rejected:
        service.historical_orders_to_rows([item], account_name="Synthetic")
    assert rejected.value.code == "invalid_order_fill_type"
    assert "PRIVATE_" not in str(rejected.value)



def test_buy_sell_quantity_conventions():
    for side, quantity, expected_side in (
        ("BUY", 2, "Buy"), ("buy", 2, "Buy"), ("SELL", 2, "Sell"),
        ("SELL", -2, "Sell"), ("sell", -2, "Sell"),
    ):
        row, = service.historical_orders_to_rows([trade(side, quantity)], account_name="Synthetic")
        assert (row.side, row.quantity, row.cost_proceeds_gbp) == (expected_side, 2, 10)


def test_documented_ignored_order_enums_do_not_change_valid_trade_fills():
    # Cover each documented value once, not a wasteful Cartesian product. Actual
    # fills, not order status/type/origin, prove the historical executed trade.
    enums = {
        "initiatedFrom": ("API", "IOS", "ANDROID", "WEB", "SYSTEM", "AUTOINVEST", "INSTRUMENT_AUTOINVEST"),
        "status": ("LOCAL", "UNCONFIRMED", "CONFIRMED", "NEW", "CANCELLING", "CANCELLED",
                   "PARTIALLY_FILLED", "FILLED", "REJECTED", "REPLACING", "REPLACED"),
        "strategy": ("QUANTITY", "VALUE"),
        "type": ("LIMIT", "STOP", "MARKET", "STOP_LIMIT"),
        "timeInForce": ("DAY", "GOOD_TILL_CANCEL"),
    }
    expected = service.historical_orders_to_rows([trade()], account_name="Synthetic")
    for field, values in enums.items():
        for value in values:
            item = trade()
            item["order"][field] = value
            assert service.historical_orders_to_rows([item], account_name="Synthetic") == expected, (field, value)
    for value in ("TOTV", "OTC"):
        item = trade()
        item["fill"]["tradingMethod"] = value
        assert service.historical_orders_to_rows([item], account_name="Synthetic") == expected


@pytest.mark.parametrize("query", ["cursor=123&limit=50", "limit=50&cursor=123"])
async def test_order_pagination_accepts_both_canonical_permutations(query):
    calls = []

    def transport(request):
        calls.append(request)
        return httpx.Response(200, json={
            "items": [{"order": {"id": len(calls)}}],
            "nextPagePath": f"/api/v0/equity/history/orders?{query}" if len(calls) == 1 else None,
        })

    client = service.Trading212Client(
        api_key="SYNTHETIC_KEY", api_secret="SYNTHETIC_SECRET", page_delay=0,
        transport=httpx.MockTransport(transport),
    )
    assert [item["order"]["id"] for item in await client.fetch_historical_orders()] == [1, 2]
    assert len(calls) == 2
    assert str(calls[1].url.query, "ascii") == query


@pytest.mark.parametrize("query", [
    "limit=50&cursor=%31", "limit=%35%30&cursor=1", "limit=50&cursor=01",
    "limit=050&cursor=1", "limit=50&cursor=1&", "limit=50&&cursor=1",
    "limit=50&cursor=1&cursor=1", "limit=50&limit=50&cursor=1",
    "limit=50&cursor=1&other=1", "limit=50&cursor=", "limit=0&cursor=1",
    "limit=51&cursor=1", "limit=50&cursor=-1", "limit=50&cursor=1000000000000000001",
])
async def test_order_pagination_rejects_noncanonical_queries_before_following(query):
    calls = []
    delays = []

    async def sleep(delay):
        delays.append(delay)

    def transport(request):
        calls.append(request)
        return httpx.Response(200, json={
            "items": [], "nextPagePath": f"/api/v0/equity/history/orders?{query}",
        })

    client = service.Trading212Client(
        api_key="SYNTHETIC_KEY", api_secret="SYNTHETIC_SECRET", sleep=sleep,
        transport=httpx.MockTransport(transport),
    )
    with pytest.raises(service.Trading212DataError) as rejected:
        await client.fetch_historical_orders()
    assert rejected.value.code == "invalid_order_pagination"
    assert len(calls) == 1
    assert delays == []

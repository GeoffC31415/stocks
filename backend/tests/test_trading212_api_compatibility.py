"""Compact, synthetic checks against the documented Trading 212 API contract."""

from collections import UserDict
from typing import Any

import httpx
import pytest

from app.services import trading212 as service

# Official Fill.type enum; keep this independent from the implementation allowlist.
FILL_TYPES = (
    "TRADE", "STOCK_SPLIT", "STOCK_DISTRIBUTION", "FOP", "FOP_CORRECTION",
    "CUSTOM_STOCK_DISTRIBUTION", "EQUITY_RIGHTS", "SCRIP_STOCK_DIVIDENDS",
    "STOCK_DIVIDENDS", "STOCK_ACQUISITION", "CASH_AND_STOCK_ACQUISITION", "SPIN_OFF",
)


def trade(side="BUY", quantity=1) -> dict[str, Any]:
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


@pytest.mark.parametrize("value", [["PRIVATE_FILL"], [], True, False, 1, 0, "PRIVATE_FILL", "", {}, None])
def test_fill_container_rejects_non_mappings_and_missing_type_safely(value):
    item = trade()
    item["fill"] = value
    with pytest.raises(service.Trading212DataError) as rejected:
        service.historical_orders_to_rows([item], account_name="Synthetic")
    assert rejected.value.code == "invalid_order_fill_type"
    assert "PRIVATE_" not in str(rejected.value)


def test_missing_fill_container_retains_type_error():
    item = trade()
    item.pop("fill")
    with pytest.raises(service.Trading212DataError) as rejected:
        service.historical_orders_to_rows([item], account_name="Synthetic")
    assert rejected.value.code == "invalid_order_fill_type"


@pytest.mark.parametrize("value", [["PRIVATE_ORDER"], [], True, False, 1, 0, "PRIVATE_ORDER", ""])
def test_trade_rejects_malformed_present_order_container(value):
    item = trade()
    item["order"] = value
    with pytest.raises(service.Trading212DataError) as rejected:
        service.historical_orders_to_rows([item], account_name="Synthetic")
    assert rejected.value.code == "invalid_order_fill_identity"
    assert "PRIVATE_" not in str(rejected.value)


@pytest.mark.parametrize("value", [None, {}, "missing"])
def test_absent_or_empty_order_retains_missing_name_error(value):
    item = trade()
    if value == "missing":
        item.pop("order")
    else:
        item["order"] = value
    with pytest.raises(service.Trading212DataError) as rejected:
        service.historical_orders_to_rows([item], account_name="Synthetic")
    assert rejected.value.code == "invalid_order_fill_name"


@pytest.mark.parametrize("value", [["PRIVATE_WALLET"], [], True, False, 1, 0, "PRIVATE_WALLET", ""])
def test_trade_rejects_malformed_present_wallet_container(value):
    item = trade()
    item["fill"]["walletImpact"] = value
    with pytest.raises(service.Trading212DataError) as rejected:
        service.historical_orders_to_rows([item], account_name="Synthetic")
    assert rejected.value.code == "invalid_order_fill_value"
    assert "PRIVATE_" not in str(rejected.value)


@pytest.mark.parametrize("value", [None, {}, "missing"])
def test_absent_or_empty_wallet_retains_currency_error(value):
    item = trade()
    if value == "missing":
        item["fill"].pop("walletImpact")
    else:
        item["fill"]["walletImpact"] = value
    with pytest.raises(service.Trading212CurrencyError) as rejected:
        service.historical_orders_to_rows([item], account_name="Synthetic")
    assert rejected.value.code == "non_gbp_currency"


def test_wallet_mapping_without_value_retains_fill_value_error():
    item = trade()
    item["fill"]["walletImpact"] = {"currency": "GBP", "extra": "ignored"}
    with pytest.raises(service.Trading212DataError) as rejected:
        service.historical_orders_to_rows([item], account_name="Synthetic")
    assert rejected.value.code == "invalid_order_fill_value"


def test_mapping_containers_with_unused_extras_preserve_valid_trade():
    plain = trade()
    item = trade()
    item["extra"] = {"ignored": True}
    item["order"] = UserDict({**item["order"], "extra": ["ignored"]})
    item["fill"]["walletImpact"] = UserDict({**item["fill"]["walletImpact"], "extra": True})
    item["fill"] = UserDict({**item["fill"], "extra": {"ignored": 1}})
    assert service.historical_orders_to_rows([item], account_name="Synthetic") == (
        service.historical_orders_to_rows([plain], account_name="Synthetic")
    )


@pytest.mark.parametrize("kind", [kind for kind in FILL_TYPES if kind != "TRADE"])
def test_non_trade_still_skips_malformed_unused_order_and_wallet(kind):
    item = {"order": ["PRIVATE_ORDER"], "fill": {"type": kind, "walletImpact": ["PRIVATE_WALLET"]}}
    assert service.historical_orders_to_rows([item], account_name="Synthetic") == []



@pytest.mark.parametrize("name", [123, ["Synthetic plc"], {}, False])
def test_trade_rejects_malformed_present_name_even_with_fallback(name):
    item = trade()
    item["order"]["instrument"]["name"] = name
    item["order"]["ticker"] = "SAFE_FALLBACK"
    with pytest.raises(service.Trading212DataError) as rejected:
        service.historical_orders_to_rows([item], account_name="Synthetic")
    assert rejected.value.code == "invalid_order_fill_name"
    assert str(rejected.value) == "Trading 212 returned an invalid order fill name."


@pytest.mark.parametrize("ticker", [123, ["SYNTHETIC"], {}, False])
def test_trade_rejects_malformed_ticker_needed_for_name(ticker):
    item = trade()
    item["order"]["instrument"].pop("name")
    item["order"]["ticker"] = ticker
    with pytest.raises(service.Trading212DataError) as rejected:
        service.historical_orders_to_rows([item], account_name="Synthetic")
    assert rejected.value.code == "invalid_order_fill_name"


def test_buy_sell_quantity_conventions():
    for side, quantity, expected_side in (
        ("BUY", 2, "Buy"), ("buy", 2, "Buy"), ("SELL", 2, "Sell"),
        ("SELL", -2, "Sell"), ("sell", -2, "Sell"),
    ):
        row, = service.historical_orders_to_rows([trade(side, quantity)], account_name="Synthetic")
        assert (row.side, row.quantity, row.cost_proceeds_gbp) == (expected_side, 2, 10)


@pytest.mark.parametrize("field", ["instrument_ticker", "order_ticker", "isin"])
@pytest.mark.parametrize("sequence", [(None, "A", "B"), ("A", None, "B"), ("A", "B")])
def test_duplicate_fill_rejects_conflicting_observed_instrument_identity(field, sequence):
    items = []
    for value in sequence:
        item = trade()
        if value is not None:
            if field == "order_ticker":
                item["order"]["ticker"] = value
            else:
                key = "ticker" if field == "instrument_ticker" else "isin"
                item["order"]["instrument"][key] = value
        items.append(item)
    with pytest.raises(service.Trading212DataError) as rejected:
        service.historical_orders_to_rows(items, account_name="Synthetic")
    assert rejected.value.code == "order_fill_identity_conflict"
    assert str(rejected.value) == "Trading 212 returned conflicting order fills."


@pytest.mark.parametrize("within_one_item", [True, False])
def test_documented_ticker_sources_cannot_disagree(within_one_item):
    first, second = trade(), trade()
    first["order"]["instrument"]["ticker"] = "PRIVATE_TICKER_A"
    (first if within_one_item else second)["order"]["ticker"] = "PRIVATE_TICKER_B"
    with pytest.raises(service.Trading212DataError) as rejected:
        service.historical_orders_to_rows(
            [first] if within_one_item else [first, second], account_name="Synthetic"
        )
    assert rejected.value.code == "order_fill_identity_conflict"
    assert "PRIVATE_" not in str(rejected.value)


@pytest.mark.parametrize("sequence", [(None, 123, 456), (123, None, "456"), (123, 456)])
def test_duplicate_fill_rejects_conflicting_parent_order_ids(sequence):
    items = []
    for value in sequence:
        item = trade()
        if value is not None:
            item["order"]["id"] = value
        items.append(item)
    with pytest.raises(service.Trading212DataError) as rejected:
        service.historical_orders_to_rows(items, account_name="Synthetic")
    assert rejected.value.code == "order_fill_identity_conflict"
    assert str(rejected.value) == "Trading 212 returned conflicting order fills."


@pytest.mark.parametrize("field", ["instrument_ticker", "order_ticker", "isin"])
@pytest.mark.parametrize("value", [123, True, ["PRIVATE_VALUE"], {"private": "PRIVATE_VALUE"}])
def test_trade_rejects_malformed_present_instrument_identity(field, value):
    item = trade()
    if field == "order_ticker":
        item["order"]["ticker"] = value
    else:
        item["order"]["instrument"]["ticker" if field == "instrument_ticker" else "isin"] = value
    with pytest.raises(service.Trading212DataError) as rejected:
        service.historical_orders_to_rows([item], account_name="Synthetic")
    assert rejected.value.code == "invalid_order_fill_identity"
    assert "PRIVATE_" not in str(rejected.value)


@pytest.mark.parametrize("value", [True, False, 1.2, "PRIVATE_ORDER", "1.2", "-", "+", "--1", [123], {"id": 123}])
def test_trade_rejects_malformed_present_parent_order_id(value):
    item = trade()
    item["order"]["id"] = value
    with pytest.raises(service.Trading212DataError) as rejected:
        service.historical_orders_to_rows([item], account_name="Synthetic")
    assert rejected.value.code == "invalid_order_fill_identity"
    assert "PRIVATE_" not in str(rejected.value)


@pytest.mark.parametrize("parent_id", [-(2**63), -123, -1, 0, 123, 2**63 - 1])
def test_integer_parent_id_matches_exact_signed_decimal_text(parent_id):
    first, second = trade(), trade()
    first["order"]["id"] = parent_id
    second["order"]["id"] = f" {parent_id} "
    expected = service.historical_orders_to_rows([trade()], account_name="Synthetic")
    assert service.historical_orders_to_rows([first, second], account_name="Synthetic") == expected * 2


@pytest.mark.parametrize("parent_id", [
    pytest.param(-(2**63) - 1, id="integer-below-min"),
    pytest.param(2**63, id="integer-above-max"),
    pytest.param(str(-(2**63) - 1), id="string-below-min"),
    pytest.param(f"+{2**63}", id="string-above-max"),
    pytest.param("9" * 5000, id="oversized-decimal-string"),
])
def test_out_of_range_parent_order_id_is_rejected_without_provider_value(parent_id):
    item = trade()
    item["order"]["id"] = parent_id
    with pytest.raises(service.Trading212DataError) as rejected:
        service.historical_orders_to_rows([item], account_name="Synthetic")
    assert rejected.value.code == "invalid_order_fill_identity"
    assert str(rejected.value) == "Trading 212 returned invalid order fill identity evidence."


@pytest.mark.parametrize("first_id,second_id", [
    (-123, "-124"), (-123, "-0123"), (123, "+123"), (0, "-0"), ("-001", "-1"), ("+0", "0"),
])
def test_distinct_signed_parent_order_spellings_conflict(first_id, second_id):
    first, second = trade(), trade()
    first["order"]["id"] = first_id
    second["order"]["id"] = second_id
    with pytest.raises(service.Trading212DataError) as rejected:
        service.historical_orders_to_rows([first, second], account_name="Synthetic")
    assert rejected.value.code == "order_fill_identity_conflict"
    assert str(rejected.value) == "Trading 212 returned conflicting order fills."


@pytest.mark.parametrize("fill_id", [-1, True])
def test_parent_id_compatibility_does_not_relax_fill_id_policy(fill_id):
    item = trade()
    item["fill"]["id"] = fill_id
    with pytest.raises(service.Trading212DataError) as rejected:
        service.historical_orders_to_rows([item], account_name="Synthetic")
    assert rejected.value.code == "invalid_order_fill_id"


@pytest.mark.parametrize("instrument", [[], ["PRIVATE_VALUE"], {}, "PRIVATE_VALUE", False])
def test_trade_rejects_malformed_instrument_container(instrument):
    if isinstance(instrument, dict):
        # Empty mapping is an absent name, so the legacy ticker fallback is valid.
        item = trade()
        item["order"].update(instrument=instrument, ticker="FALLBACK")
        row, = service.historical_orders_to_rows([item], account_name="Synthetic")
        assert row.security_name == "FALLBACK"
        return
    item = trade()
    item["order"].update(instrument=instrument, ticker="FALLBACK")
    with pytest.raises(service.Trading212DataError) as rejected:
        service.historical_orders_to_rows([item], account_name="Synthetic")
    assert rejected.value.code == "invalid_order_fill_identity"
    assert "PRIVATE_" not in str(rejected.value)


@pytest.mark.parametrize("name", [None, "", "missing"])
def test_missing_or_empty_name_preserves_order_ticker_fallback(name):
    item = trade()
    if name == "missing":
        item["order"]["instrument"].pop("name")
    else:
        item["order"]["instrument"]["name"] = name
    item["order"]["ticker"] = "FALLBACK"
    row, = service.historical_orders_to_rows([item], account_name="Synthetic")
    assert row.security_name == "FALLBACK"


def test_consistent_optional_claims_do_not_change_mapped_rows():
    plain = trade()
    enriched = trade()
    enriched["order"].update(id=123, ticker=" TEST_EQ ", extra={"ignored": True})
    enriched["order"]["instrument"].update(ticker="TEST_EQ", isin=" ISIN_A ")
    repeated = trade()
    repeated["order"].update(id=" 123 ")
    repeated["order"]["instrument"].update(ticker="TEST_EQ", isin="ISIN_A")
    blank = trade()
    blank["order"].update(id="", ticker=None)
    blank["order"]["instrument"].update(ticker="", isin=None)
    expected, = service.historical_orders_to_rows([plain], account_name="Synthetic")
    rows = service.historical_orders_to_rows(
        [plain, enriched, blank, repeated], account_name="Synthetic"
    )
    assert rows == [expected] * 4


@pytest.mark.parametrize("field", ["date", "name", "side", "quantity", "value"])
def test_duplicate_id_compares_all_mapped_trade_fields(field):
    first = trade()
    second = trade()
    # Fingerprints normalize string IDs with strip/casefold, and integer IDs via str.
    first["fill"]["id"] = "PRIVATE_ID_SENTINEL"
    second["fill"]["id"] = " private_id_sentinel "
    if field == "date":
        second["fill"]["filledAt"] = "2026-01-01T12:00:01Z"
    elif field == "name":
        second["order"]["instrument"]["name"] = "Another synthetic plc"
    elif field == "side":
        second["order"]["side"] = "SELL"
    elif field == "quantity":
        # Even a difference smaller than the legacy fingerprint rounding is a conflict.
        second["fill"]["quantity"] = 1.000000001
    else:
        second["fill"]["walletImpact"]["netValue"] = 11
    with pytest.raises(service.Trading212DataError) as rejected:
        service.historical_orders_to_rows([first, second], account_name="Synthetic")
    assert rejected.value.code == "order_fill_identity_conflict"
    assert "PRIVATE_" not in str(rejected.value)


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

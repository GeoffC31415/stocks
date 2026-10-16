import datetime as dt

import httpx
import pytest

from app.services import trading212


def transaction(reference="deposit-1", kind="DEPOSIT", amount=500, **overrides):
    return dict(
        reference=reference,
        type=kind,
        amount=amount,
        currency="GBP",
        dateTime="2026-09-08T10:00:00Z",
        **overrides,
    )


def test_cash_mapping_counts_only_deposits_and_withdrawals():
    rows = trading212.transactions_to_rows(
        [
            transaction(),
            transaction("withdraw-1", "WITHDRAW", -100),
            transaction("interest-1", "INTEREST_ON_FREE_CASH", 2),
            transaction("fee-1", "FEE", -1),
            transaction("lending-1", "LENDING_INTEREST", 3),
        ]
    )
    assert [(r.reference, r.amount_gbp) for r in rows] == [("deposit-1", 500), ("withdraw-1", -100)]
    assert rows[0].occurred_at == dt.datetime(2026, 9, 8, 10, tzinfo=dt.UTC)


@pytest.mark.parametrize(
    "field,value",
    [
        ("reference", ""),
        ("reference", " padded "),
        ("reference", 1),
        ("reference", []),
        ("amount", None),
        ("amount", True),
        ("amount", float("nan")),
        ("amount", float("inf")),
        ("amount", 0),
        ("amount", -1),
        ("currency", "USD"),
        ("dateTime", "invalid"),
        ("dateTime", "2026-09-08"),
        ("type", "UNKNOWN"),
    ],
)
def test_cash_mapping_fails_closed(field, value):
    item = transaction()
    item[field] = value
    with pytest.raises(trading212.Trading212DataError):
        trading212.transactions_to_rows([item])


@pytest.mark.parametrize(("kind", "amount", "expected"), [
    ("DEPOSIT", 10, [10]), ("WITHDRAW", 10, [-10]), ("WITHDRAW", -10, [-10]),
    ("FEE", -1, []), ("INTEREST_ON_FREE_CASH", 1, []), ("LENDING_INTEREST", 1, []),
    ("TRANSFER", -10, [-10]), ("TRANSFER", 10, [10]),
])
def test_all_classified_documented_cash_types(kind, amount, expected):
    rows = trading212.transactions_to_rows([transaction(kind=kind, amount=amount)])
    assert [row.amount_gbp for row in rows] == expected


def test_transfer_rejects_zero_nonfinite_and_malformed_amounts():
    for amount in (
        0, -0.0, None, True, [], {}, "PRIVATE_AMOUNT_SENTINEL",
        float("nan"), float("inf"), -float("inf"), 10**1000,
    ):
        with pytest.raises(trading212.Trading212DataError) as rejected:
            trading212.transactions_to_rows([transaction(kind="TRANSFER", amount=amount)])
        assert rejected.value.code == "invalid_cash_transfer_amount"


def test_transfer_reference_and_currency_safeguards():
    for field, value, code in (
        ("reference", " padded ", "invalid_cash_transaction_reference"),
        ("reference", "", "invalid_cash_transaction_reference"),
        ("currency", "USD", "invalid_cash_transaction_currency"),
        ("currency", None, "invalid_cash_transaction_currency"),
    ):
        item = transaction(kind="TRANSFER", amount=-10)
        item[field] = value
        with pytest.raises(trading212.Trading212DataError) as rejected:
            trading212.transactions_to_rows([item])
        assert rejected.value.code == code
    item = transaction(kind="TRANSFER", amount=-10)
    assert len(trading212.transactions_to_rows([item, item])) == 1
    with pytest.raises(trading212.Trading212DataError) as rejected:
        trading212.transactions_to_rows([item, transaction(kind="TRANSFER", amount=10)])
    assert rejected.value.code == "cash_reference_conflict"


def test_cash_numeric_boundaries_for_every_classified_type():
    for kind in ("DEPOSIT", "WITHDRAW", "FEE", "INTEREST_ON_FREE_CASH", "LENDING_INTEREST"):
        for amount in (None, True, float("nan"), float("inf"), -float("inf")):
            with pytest.raises(trading212.Trading212DataError) as rejected:
                trading212.transactions_to_rows([transaction(kind=kind, amount=amount)])
            assert rejected.value.code == "invalid_cash_transaction_amount", kind
        if kind in ("DEPOSIT", "WITHDRAW"):
            with pytest.raises(trading212.Trading212DataError) as rejected:
                trading212.transactions_to_rows([transaction(kind=kind, amount=0)])
            assert rejected.value.code == "invalid_cash_transaction_amount"
        else:
            # Internal events still validate even though they create no external flow.
            assert trading212.transactions_to_rows([transaction(kind=kind, amount=0)]) == []


@pytest.mark.parametrize("kind", ["UNKNOWN", "WITHDRAWAL", None, [], {}])
def test_unknown_cash_types_are_not_aliases(kind):
    with pytest.raises(trading212.Trading212DataError) as rejected:
        trading212.transactions_to_rows([transaction(kind=kind)])
    assert rejected.value.code == "unsupported_cash_transaction_type"


def test_all_cash_categories_validate_currency_and_reference_identity():
    for kind in ("DEPOSIT", "WITHDRAW", "TRANSFER", "FEE", "INTEREST_ON_FREE_CASH", "LENDING_INTEREST"):
        item = transaction(kind=kind, amount=10)
        expected = trading212.transactions_to_rows([item])
        assert trading212.transactions_to_rows([item, item]) == expected, kind
        with pytest.raises(trading212.Trading212DataError) as rejected:
            trading212.transactions_to_rows([item, transaction(kind=kind, amount=20)])
        assert rejected.value.code == "cash_reference_conflict", kind
        for currency in (None, "USD"):
            with pytest.raises(trading212.Trading212DataError) as rejected:
                trading212.transactions_to_rows([dict(item, currency=currency)])
            assert rejected.value.code == "invalid_cash_transaction_currency", kind


def test_cash_mapping_rejects_conflicting_references():
    with pytest.raises(trading212.Trading212DataError):
        trading212.transactions_to_rows([transaction(), transaction(amount=999)])


def test_cash_mapping_deduplicates_exact_references_but_not_identical_amounts():
    rows = trading212.transactions_to_rows([transaction(), transaction(), transaction("deposit-2")])
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_cash_client_paginates_read_only_with_endpoint_delay():
    calls = []
    delays = []

    async def sleep(delay):
        delays.append(delay)

    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.url.host == "live.trading212.com"
        return httpx.Response(
            200,
            json={
                "items": [transaction(str(len(calls)))],
                "nextPagePath": "/api/v0/equity/history/transactions?cursor=opaque-123&limit=50"
                if len(calls) == 1
                else None,
            },
        )

    client = trading212.Trading212Client(
        api_key="test-key",
        api_secret="test-secret",
        transport=httpx.MockTransport(handler),
        sleep=sleep,
    )
    assert len(await client.fetch_transactions()) == 2
    assert len(calls) == 2
    assert delays == [10.1]


@pytest.mark.parametrize(
    "path",
    [
        "https://attacker.invalid/api/v0/equity/history/transactions?cursor=1&limit=50",
        "/api/v0/equity/history/orders?cursor=1&limit=50",
        "/api/v0/equity/history/transactions?cursor=1&limit=51",
        "/api/v0/equity/history/transactions?cursor=1&limit=50&limit=50",
        "/api/v0/equity/history/transactions?cursor=1&limit=50&extra=1",
        "/api/v0/equity/history/transactions?cursor=1&limit=50#fragment",
    ],
)
@pytest.mark.asyncio
async def test_cash_client_rejects_bad_pagination_before_following(path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"items": [], "nextPagePath": path})

    client = trading212.Trading212Client(
        api_key="test-key",
        api_secret="test-secret",
        transport=httpx.MockTransport(handler),
        page_delay=0,
    )
    with pytest.raises(trading212.Trading212DataError):
        await client.fetch_transactions()
    assert len(calls) == 1

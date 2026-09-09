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
        ("type", "TRANSFER"),
        ("type", "UNKNOWN"),
    ],
)
def test_cash_mapping_fails_closed(field, value):
    item = transaction()
    item[field] = value
    with pytest.raises(trading212.Trading212DataError):
        trading212.transactions_to_rows([item])


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

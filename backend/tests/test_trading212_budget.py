"""Synthetic transport tests: no live broker I/O."""

import asyncio
import datetime as dt
from email.utils import format_datetime

import httpx
import pytest

from app.services.trading212 import Trading212Client, Trading212DataError


@pytest.mark.asyncio
async def test_retry_after_is_honoured_then_read_succeeds():
    requests, delays = [], []

    def handler(request):
        requests.append(request)
        return (
            httpx.Response(429, headers={"Retry-After": "2"})
            if len(requests) == 1
            else httpx.Response(200, json=[])
        )

    async def sleep(seconds):
        delays.append(seconds)

    client = Trading212Client(
        api_key="synthetic",
        api_secret="synthetic",
        transport=httpx.MockTransport(handler),
        sleep=sleep,
    )
    assert await client.fetch_positions() == []
    assert len(requests) == 2
    assert delays == [2]


@pytest.mark.asyncio
async def test_retry_after_exceeding_budget_fails_without_early_retry():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(429, headers={"Retry-After": "901"})

    client = Trading212Client(
        api_key="synthetic", api_secret="synthetic", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(Trading212DataError, match="budget"):
        await client.fetch_positions()
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_retries_are_bounded():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(503)

    async def sleep(seconds):
        pass

    client = Trading212Client(
        api_key="synthetic",
        api_secret="synthetic",
        transport=httpx.MockTransport(handler),
        sleep=sleep,
    )
    with pytest.raises(httpx.HTTPStatusError):
        await client.fetch_positions()
    assert len(requests) == 3


@pytest.mark.asyncio
async def test_request_wall_clock_is_bounded_even_for_hung_transport():
    async def handler(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json=[])

    client = Trading212Client(
        api_key="synthetic",
        api_secret="synthetic",
        transport=httpx.MockTransport(handler),
        runtime_budget=0.01,
    )
    with pytest.raises(Trading212DataError, match="budget"):
        await client.fetch_positions()


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["orders", "transactions"])
async def test_pagination_and_all_sections_share_one_deadline(endpoint):
    now, requests = [0.0], []

    async def sleep(seconds):
        now[0] += seconds

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("positions"):
            return httpx.Response(200, json=[])
        return httpx.Response(
            200,
            json={
                "items": [],
                "nextPagePath": f"/api/v0/equity/history/{endpoint}?cursor={len(requests)}&limit=50",
            },
        )

    client = Trading212Client(
        api_key="synthetic",
        api_secret="synthetic",
        transport=httpx.MockTransport(handler),
        runtime_budget=15,
        clock=lambda: now[0],
        sleep=sleep,
        page_delay=10,
    )
    await client.fetch_positions()
    with pytest.raises(Trading212DataError, match="budget"):
        await (
            client.fetch_historical_orders()
            if endpoint == "orders"
            else client.fetch_transactions()
        )
    assert len(requests) == 3
    assert now[0] == 10


@pytest.mark.asyncio
async def test_http_date_retry_after_is_honoured():
    requests, delays = [], []
    when = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=5)

    def handler(request):
        requests.append(request)
        return (
            httpx.Response(429, headers={"Retry-After": format_datetime(when, usegmt=True)})
            if len(requests) == 1
            else httpx.Response(200, json=[])
        )

    async def sleep(seconds):
        delays.append(seconds)

    client = Trading212Client(
        api_key="synthetic",
        api_secret="synthetic",
        transport=httpx.MockTransport(handler),
        sleep=sleep,
    )
    assert await client.fetch_positions() == []
    assert len(requests) == 2
    assert 3 < delays[0] <= 5


@pytest.mark.asyncio
@pytest.mark.parametrize("header", ["NaN", "inf", "-1", "²", "9" * 5000])
async def test_invalid_retry_after_fails_without_retry(header):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(429, headers=[(b"Retry-After", header.encode("latin1"))])

    client = Trading212Client(
        api_key="synthetic", api_secret="synthetic", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(Trading212DataError, match="Retry-After"):
        await client.fetch_positions()
    assert len(requests) == 1


@pytest.mark.parametrize("budget", [float("inf"), float("nan"), -1, 0, 901, True])
def test_invalid_runtime_budget_is_rejected(budget):
    with pytest.raises(ValueError):
        Trading212Client(api_key="synthetic", api_secret="synthetic", runtime_budget=budget)

"""Trading 212 documented HTTP timeouts remain read-only and bounded."""

import httpx
import pytest

from app.services.trading212 import Trading212Client, Trading212DataError


@pytest.mark.asyncio
async def test_documented_http_timeout_retries_one_get_then_succeeds():
    calls = []
    delays = []

    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        if len(calls) == 1:
            return httpx.Response(408)
        return httpx.Response(200, json=[])

    async def sleep(seconds):
        delays.append(seconds)

    client = Trading212Client(
        api_key="synthetic-key", api_secret="synthetic-secret",
        transport=httpx.MockTransport(handler), sleep=sleep,
    )
    assert await client.fetch_positions() == []
    assert len(calls) == 2
    assert delays == [10.1]


@pytest.mark.asyncio
async def test_repeated_408_stops_after_three_gets():
    calls, delays = [], []

    def handler(request):
        calls.append(request)
        return httpx.Response(408)

    async def sleep(seconds):
        delays.append(seconds)

    client = Trading212Client(
        api_key="synthetic-key", api_secret="synthetic-secret",
        transport=httpx.MockTransport(handler), sleep=sleep,
    )
    with pytest.raises(httpx.HTTPStatusError) as rejected:
        await client.fetch_positions()
    assert rejected.value.response.status_code == 408
    assert len(calls) == 3
    assert delays == [10.1, 20.2]


@pytest.mark.asyncio
async def test_408_does_not_retry_when_delay_exceeds_budget():
    calls, delays = [], []

    def handler(request):
        calls.append(request)
        return httpx.Response(408)

    async def sleep(seconds):
        delays.append(seconds)

    client = Trading212Client(
        api_key="synthetic-key", api_secret="synthetic-secret",
        transport=httpx.MockTransport(handler), sleep=sleep,
        runtime_budget=5, clock=lambda: 0,
    )
    with pytest.raises(Trading212DataError) as rejected:
        await client.fetch_positions()
    assert rejected.value.code == "retry_budget_exceeded"
    assert len(calls) == 1
    assert delays == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403])
async def test_permission_and_bad_request_responses_are_not_retried(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status)

    client = Trading212Client(
        api_key="synthetic-key", api_secret="synthetic-secret",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(httpx.HTTPStatusError) as rejected:
        await client.fetch_positions()
    assert rejected.value.response.status_code == status
    assert len(calls) == 1

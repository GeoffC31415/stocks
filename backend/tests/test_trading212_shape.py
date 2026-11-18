"""Response drift is observable without retaining private keys, values or URLs."""

import logging

import httpx
import pytest

from app.services.trading212 import Trading212Client


@pytest.mark.asyncio
async def test_paged_drift_is_source_labelled_bounded_and_does_not_modify_data(caplog):
    private = "PRIVATE_JOURNAL_SENTINEL"
    item = {
        "order": {"instrument": {"name": "Example", private: 1}},
        "fill": {"type": "TRADE", "price": {private: 1}, "walletImpact": {"taxes": [{private: 1}]}},
        private: {private: 1},
    }
    pages = iter(
        [
            {
                private: 1,
                "items": [item, item],
                "nextPagePath": "/api/v0/equity/history/orders?cursor=2&limit=50",
            },
            {private: 1, "items": [item], "nextPagePath": None},
        ]
    )
    client = Trading212Client(
        api_key=private,
        api_secret=private,
        page_delay=0,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=next(pages))),
    )
    assert await client.fetch_historical_orders() == [item] * 3
    logs = [r for r in caplog.records if r.getMessage().startswith("Trading 212 response drift ")]
    assert {r.getMessage().split("drift ")[1] for r in logs} == {
        "endpoint=orders location=orders_page field=extra code=additional_field",
        "endpoint=orders location=historical_order field=extra code=additional_field",
        "endpoint=orders location=instrument field=extra code=additional_field",
        "endpoint=orders location=tax field=extra code=additional_field",
        "endpoint=orders location=fill field=price code=unexpected_type",
    }
    assert len(logs) == 5
    assert all(r.exc_info is None and private not in r.getMessage() for r in logs)


@pytest.mark.asyncio
async def test_broken_warning_sink_does_not_hide_provider_data_or_break_fetch(monkeypatch):
    # A handler failure must not suppress the *import*, even after detecting an anomaly.
    logger = logging.getLogger("app.services.trading212_shape")
    attempts = []

    def broken(*args, **kwargs):
        attempts.append(1)
        raise OSError("SYNTHETIC_LOG_UNAVAILABLE")

    monkeypatch.setattr(logger, "warning", broken)
    payload = {"currency": "GBP", "arbitrary": "SYNTHETIC_PRIVATE"}
    client = Trading212Client(
        api_key="synthetic",
        api_secret="synthetic",
        page_delay=0,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
    )
    assert await client.fetch_account_summary() == payload
    assert attempts == [1]

"""The dedicated worker can retain valid executions when a cash page is unusable."""

import copy
import json

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlite_schema import create_file_schema
from test_gate_a_trading212 import Reader

from app import trading212_cli as worker
from app.models import (
    CashFlowCoverage,
    ExternalCashFlow,
    ImportBatch,
    Instrument,
    Order,
    OrderImportBatch,
)
from app.routers import trading212 as router
from app.services.trading212 import Trading212Client


@pytest.mark.asyncio
async def test_cash_pagination_failure_imports_only_verified_history_then_recovers(
    tmp_path, monkeypatch, caplog
):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'portfolio.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(worker, "SessionLocal", sessions)
    monkeypatch.setattr(worker.settings, "sync_inbox", tmp_path / "inbox")
    status_dir = tmp_path / "public" / "trading212"
    monkeypatch.setattr(worker.settings, "sync_status_dir", status_dir)
    for key in ("trading212_api_key", "trading212_api_secret"):
        monkeypatch.setattr(worker.settings, key, SecretStr("fixture"))
    r = Reader()
    positions = await r.fetch_positions()
    trades = await r.fetch_historical_orders()
    cash = {"items": await r.fetch_transactions(), "nextPagePath": None}
    paths = {
        "/api/v0/equity/positions": positions,
        "/api/v0/equity/account/summary": await r.fetch_account_summary(),
        "/api/v0/equity/history/orders": {"items": trades, "nextPagePath": None},
        "/api/v0/equity/history/transactions": cash,
    }
    requested = []

    def transport(request):
        requested.append(request.url.path)
        return httpx.Response(200, json=paths[request.url.path])

    monkeypatch.setattr(
        router,
        "get_trading212_client",
        lambda: Trading212Client(
            api_key="fixture",
            api_secret="fixture",
            page_delay=0,
            transport=httpx.MockTransport(transport),
        ),
    )

    async def run(char, exit_code, outcome):
        monkeypatch.setenv("INVOCATION_ID", char * 32)
        requested.clear()
        assert await worker.run() == exit_code
        assert sorted(requested) == sorted(paths)  # no refetch for salvage
        text = (status_dir / "last-sync.json").read_text()
        assert "PRIVATE_SENTINEL" not in text
        report = json.loads(text)
        assert report["outcome"] == outcome and report["invocation_id"] == char * 32
        return report["freshness"]["Trading 212"]

    async def durable():
        async with sessions() as s:
            return [
                await s.scalar(select(func.count()).select_from(m))
                for m in (ImportBatch, OrderImportBatch, Order, ExternalCashFlow, CashFlowCoverage)
            ]

    try:
        await create_file_schema(engine)
        first = await run("a", 0, "complete")
        assert await durable() == [1, 1, 1, 1, 1]
        positions.pop()  # A sale, but a partial refresh must not close the holding.
        trades.append(copy.deepcopy(trades[0]))
        trades[-1]["fill"]["id"] = 2
        paths["/api/v0/equity/history/orders"]["PRIVATE_SENTINEL_FIELD"] = "PRIVATE_SENTINEL_VALUE"
        cash["items"].append({**cash["items"][0], "reference": "second-deposit"})
        cash["nextPagePath"] = "/different-endpoint?PRIVATE_SENTINEL_CURSOR"
        # Alembic's fileConfig may have disabled an already-created journal sink.
        from app.services import sync_runner

        monkeypatch.setattr(sync_runner.logger, "disabled", True)
        partial = await run("b", 1, "partial")
        assert await durable() == [1, 2, 2, 1, 1]
        for key in ("holdings", "cash", "transactions"):
            assert partial[key]["verified_at"] == first[key]["verified_at"]
            assert partial[key]["status"] not in ("ok", "unchanged", "imported")
        assert partial["orders"]["verified_at"] > first["orders"]["verified_at"]
        async with sessions() as s:
            assert (
                await s.scalar(select(Instrument).where(Instrument.identifier == "TWO"))
            ).closed_at is None
        assert (
            "code=additional_field" in caplog.text and "code=invalid_cash_pagination" in caplog.text
        )
        assert "PRIVATE_SENTINEL" not in caplog.text
        cash["nextPagePath"] = None
        await run("c", 0, "complete")
        assert await durable() == [2, 2, 2, 2, 1]
        async with sessions() as s:
            assert (
                await s.scalar(select(Instrument).where(Instrument.identifier == "TWO"))
            ).closed_at is not None
        # A repeat with irrelevant data on both collections is not another valuation or trade batch.
        positions[0]["PRIVATE_SENTINEL_FIELD"] = True
        trades[-1]["PRIVATE_SENTINEL_FIELD"] = "irrelevant change"
        repeated = await run("d", 0, "complete")
        assert repeated["holdings"]["status"] == repeated["orders"]["status"] == "unchanged"
        assert await durable() == [2, 2, 2, 2, 1]
    finally:
        await engine.dispose()

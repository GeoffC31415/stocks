"""Atomic sync regressions: synthetic SQLite files and an in-process broker fake."""

import copy
import datetime as dt
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlite_schema import create_file_schema

from app.models import (
    CashFlowCoverage,
    ExternalCashFlow,
    HoldingSnapshot,
    ImportBatch,
    Instrument,
    Order,
    OrderImportBatch,
)
from app.routers import trading212


class SyntheticReader:
    async def fetch_positions(self):
        return [
            {
                "instrument": {"currency": "GBP", "isin": "GB00TEST", "name": "Test"},
                "quantity": 1,
                "walletImpact": {"currency": "GBP", "currentValue": 10, "totalCost": 9},
            }
        ]

    async def fetch_account_summary(self):
        return {
            "currency": "GBP",
            "cash": {
                "availableToTrade": 1,
                "inPies": 0,
                "reservedForOrders": 0,
            },
        }

    async def fetch_historical_orders(self):
        return []

    async def fetch_transactions(self):
        return []


@pytest.fixture
async def sync_database(tmp_path, monkeypatch):
    monkeypatch.setattr(
        trading212, "settings", SimpleNamespace(trading212_account_name="Synthetic account")
    )
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sync.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def configure(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=100")
        cursor.close()

    await create_file_schema(engine)
    try:
        yield engine, async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_failed_sync_cannot_delete_another_writers_reused_ids(sync_database, monkeypatch):
    _, sessions = sync_database

    class InvalidCashReader(SyntheticReader):
        async def fetch_transactions(self):
            return [{"type": "UNSUPPORTED"}]

    async with sessions() as session:
        rollback = session.rollback
        rolled_back_ids = []

        async def rollback_then_other_writer():
            rolled_back_ids.append(
                (
                    await session.scalar(select(ImportBatch.id)),
                    await session.scalar(select(OrderImportBatch.id)),
                )
            )
            await rollback()
            # Reproduce a writer winning the gap after rollback and reusing SQLite IDs.
            async with sessions() as other:
                batch = ImportBatch(as_of_date=dt.date(2026, 1, 1), file_sha256="s" * 64)
                order_batch = OrderImportBatch(file_sha256="o" * 64, row_count=0)
                other.add_all([batch, order_batch])
                await other.commit()
                assert (batch.id, order_batch.id) == rolled_back_ids[-1]

        monkeypatch.setattr(session, "rollback", rollback_then_other_writer)
        with pytest.raises(HTTPException) as error:
            await trading212.sync_trading212_all(
                force=False,
                _origin_guard=None,
                session=session,
                client=InvalidCashReader(),
            )
        assert error.value.status_code == 400
        assert len(rolled_back_ids) == 1

    async with sessions() as check:
        assert await check.scalar(select(ImportBatch.file_sha256)) == "s" * 64
        assert await check.scalar(select(OrderImportBatch.file_sha256)) == "o" * 64
        assert await check.scalar(select(func.count()).select_from(Instrument)) == 0
        assert await check.scalar(select(func.count()).select_from(HoldingSnapshot)) == 0


@pytest.mark.asyncio
async def test_network_fetches_finish_before_any_import_writes(sync_database):
    engine, sessions = sync_database
    async with engine.begin() as connection:
        await connection.exec_driver_sql("CREATE TABLE writer_probe (phase TEXT)")
    writes = []
    fetched = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def record_import_writes(_connection, _cursor, statement, _parameters, _context, _many):
        if (
            statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
            and "writer_probe" not in statement
        ):
            writes.append(statement)

    async def during_network(phase):
        fetched.append(phase)
        assert not writes, "A broker fetch happened after database writes"
        # A second real SQLite writer can still work while the broker is awaited.
        async with engine.begin() as connection:
            await connection.exec_driver_sql("INSERT INTO writer_probe VALUES (?)", (phase,))

    class LockCheckingReader(SyntheticReader):
        async def fetch_positions(self):
            await during_network("positions")
            return await super().fetch_positions()

        async def fetch_account_summary(self):
            await during_network("summary")
            return await super().fetch_account_summary()

        async def fetch_historical_orders(self):
            await during_network("orders")
            return await super().fetch_historical_orders()

        async def fetch_transactions(self):
            await during_network("cash")
            return await super().fetch_transactions()

    async with sessions() as session:
        result = await trading212.sync_trading212_all(
            force=False,
            _origin_guard=None,
            session=session,
            client=LockCheckingReader(),
        )
    assert result.snapshot == "imported"
    assert result.orders == "imported"
    assert fetched == ["positions", "summary", "orders", "cash"]
    assert writes


@pytest.mark.asyncio
async def test_successful_sync_commits_all_data_once_and_repeats_idempotently(sync_database):
    engine, sessions = sync_database
    commits = []

    @event.listens_for(engine.sync_engine, "commit")
    def record_commit(_connection):
        commits.append(True)

    class CompleteReader(SyntheticReader):
        async def fetch_historical_orders(self):
            return [
                {
                    "fill": {
                        "id": 1,
                        "filledAt": "2020-01-01T10:00:00Z",
                        "quantity": 1,
                        "type": "TRADE",
                        "walletImpact": {"currency": "GBP", "netValue": -9},
                    },
                    "order": {
                        "instrument": {"name": "Test", "ticker": "TEST_EQ"},
                        "side": "BUY",
                        "status": "FILLED",
                    },
                }
            ]

        async def fetch_transactions(self):
            return [
                {
                    "reference": "test-deposit",
                    "type": "DEPOSIT",
                    "amount": 10,
                    "currency": "GBP",
                    "dateTime": "2020-01-01T09:00:00Z",
                },
                {
                    "reference": "synthetic-transfer-out", "type": "TRANSFER", "amount": -2,
                    "currency": "GBP", "dateTime": "2020-01-01T09:30:00Z",
                },
                {
                    "reference": "synthetic-transfer-in", "type": "TRANSFER", "amount": 3,
                    "currency": "GBP", "dateTime": "2020-01-01T09:45:00Z",
                },
            ]

    from app.services.trading212 import Trading212Client

    reader = CompleteReader()
    payloads = {
        "/api/v0/equity/positions": await reader.fetch_positions(),
        "/api/v0/equity/account/summary": await reader.fetch_account_summary(),
        "/api/v0/equity/history/orders": {
            "items": await reader.fetch_historical_orders(), "nextPagePath": None,
        },
    }
    cash = await reader.fetch_transactions()
    next_path = (
        "/api/v0/equity/history/transactions?cursor=synthetic-next&limit=50"
        "&time=2020-01-01T09%3A45%3A00Z"
    )
    cash_requests = []

    def transport(request):
        assert request.method == "GET"
        if request.url.path == "/api/v0/equity/history/transactions":
            cash_requests.append(request.url.raw_path.decode())
            payload = (
                {"items": cash[2:], "nextPagePath": None}
                if "cursor" in request.url.params
                else {"items": cash[:2], "nextPagePath": next_path}
            )
        else:
            payload = payloads[request.url.path]
        return httpx.Response(200, json=payload)

    client = Trading212Client(
        api_key="synthetic-key", api_secret="synthetic-secret",
        transport=httpx.MockTransport(transport), page_delay=0,
    )
    for expected_snapshot, expected_cash in [("imported", 3), ("unchanged", 0)]:
        commits.clear()
        async with sessions() as session:
            result = await trading212.sync_trading212_all(
                force=False,
                _origin_guard=None,
                session=session,
                client=client,
            )
        assert commits == [True]
        assert result.snapshot == expected_snapshot
        assert result.orders == expected_snapshot
        assert result.cash_flows_imported == expected_cash
        async with sessions() as check:
            for model, expected_count in [
                (ImportBatch, 1),
                (OrderImportBatch, 1),
                (Instrument, 2),
                (HoldingSnapshot, 2),
                (Order, 1),
                (ExternalCashFlow, 3),
                (CashFlowCoverage, 1),
            ]:
                assert await check.scalar(select(func.count()).select_from(model)) == expected_count
            assert dict((await check.execute(select(
                ExternalCashFlow.reference, ExternalCashFlow.amount_gbp,
            ))).all()) == {
                "test-deposit": 10, "synthetic-transfer-out": -2, "synthetic-transfer-in": 3,
            }
    assert cash_requests == [
        "/api/v0/equity/history/transactions?limit=50", next_path,
    ] * 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    ["same-page-conflict", "across-pages-conflict", "invalid-duplicate-with-extras",
     "ticker-memory-cross-page", "isin-memory-cross-page", "parent-memory-cross-page",
     "same-item-ticker-conflict", "malformed-name", "malformed-ticker", "malformed-parent",
     "malformed-fill-container", "malformed-order-container", "malformed-wallet-container",
     "signed-parent-conflict", "parent-out-of-range"],
)
async def test_bad_fill_rolls_back_owner_after_full_fetch(sync_database, caplog, case):
    from app.services.trading212 import Trading212Client, Trading212DataError

    engine, sessions = sync_database
    reader = SyntheticReader()
    baseline_fill = {
        "order": {"instrument": {"name": "Test"}, "side": "BUY"},
        "fill": {
            "id": 101, "type": "TRADE", "filledAt": "2020-01-01T09:00:00Z",
            "quantity": 1, "walletImpact": {"currency": "GBP", "netValue": -9},
        },
    }
    candidate: dict[str, Any] = {
        "order": {"instrument": {"name": "PRIVATE_NAME_SENTINEL"}, "side": "BUY"},
        "fill": {
            "id": 202, "type": "TRADE", "filledAt": "2020-01-02T09:00:00Z",
            "quantity": 2, "walletImpact": {"currency": "GBP", "netValue": -20},
        },
    }
    conflicting: dict[str, Any] = {
        **candidate,
        "fill": {**candidate["fill"], "id": " 202 ", "walletImpact": {
            "currency": "GBP", "netValue": -21,
        }},
        "unknown_extra": {"private": "PRIVATE_EXTRA_SENTINEL"},
    }
    across_pages = case != "same-page-conflict"
    code = "order_fill_identity_conflict"
    if case == "invalid-duplicate-with-extras":
        conflicting["fill"]["quantity"] = {"extra": "PRIVATE_BAD_QUANTITY_SENTINEL"}
        code = "invalid_order_fill_quantity"
    elif case not in {"same-page-conflict", "across-pages-conflict"}:
        # Isolate the identity/name defect: economic fields remain identical.
        conflicting = copy.deepcopy(candidate)
        if case == "ticker-memory-cross-page":
            candidate["order"]["instrument"]["ticker"] = "PRIVATE_TICKER_A"
            conflicting["order"]["ticker"] = "PRIVATE_TICKER_B"
        elif case == "isin-memory-cross-page":
            candidate["order"]["instrument"]["isin"] = "PRIVATE_ISIN_A"
            conflicting["order"]["instrument"]["isin"] = "PRIVATE_ISIN_B"
        elif case == "parent-memory-cross-page":
            candidate["order"]["id"] = 100
            conflicting["order"]["id"] = 200
        elif case == "same-item-ticker-conflict":
            conflicting["order"]["instrument"]["ticker"] = "PRIVATE_TICKER_A"
            conflicting["order"]["ticker"] = "PRIVATE_TICKER_B"
        elif case == "malformed-name":
            candidate["order"]["instrument"]["name"] = "123"
            conflicting["order"]["instrument"]["name"] = 123
            code = "invalid_order_fill_name"
        elif case == "malformed-ticker":
            conflicting["order"]["instrument"]["ticker"] = ["PRIVATE_TICKER"]
            code = "invalid_order_fill_identity"
        elif case == "malformed-parent":
            conflicting["order"]["id"] = ["PRIVATE_PARENT"]
            code = "invalid_order_fill_identity"
        elif case == "malformed-fill-container":
            conflicting["fill"] = ["PRIVATE_FILL"]
            code = "invalid_order_fill_type"
        elif case == "malformed-order-container":
            conflicting["order"] = ["PRIVATE_ORDER"]
            code = "invalid_order_fill_identity"
        elif case == "malformed-wallet-container":
            conflicting["fill"]["walletImpact"] = ["PRIVATE_WALLET"]
            code = "invalid_order_fill_value"
        elif case == "signed-parent-conflict":
            candidate["order"]["id"] = -100
            conflicting["order"]["id"] = "-200"
        elif case == "parent-out-of-range":
            candidate["order"]["id"] = 2**63
            code = "invalid_order_fill_identity"
    positions = await reader.fetch_positions()
    account = await reader.fetch_account_summary()
    pages = [[baseline_fill]]
    order_requests = []

    def transport(request):
        if request.url.path == "/api/v0/equity/history/orders":
            second_page = "cursor" in request.url.params
            order_requests.append(second_page)
            return httpx.Response(200, json={
                "items": pages[1 if second_page else 0],
                "nextPagePath": (
                    "/api/v0/equity/history/orders?cursor=123&limit=50"
                    if len(pages) == 2 and not second_page else None
                ),
            })
        payloads = {
            "/api/v0/equity/positions": positions,
            "/api/v0/equity/account/summary": account,
            "/api/v0/equity/history/transactions": {"items": [], "nextPagePath": None},
        }
        return httpx.Response(200, json=payloads[request.url.path])

    client = Trading212Client(
        api_key="SYNTHETIC_KEY", api_secret="SYNTHETIC_SECRET",
        transport=httpx.MockTransport(transport), page_delay=0,
    )
    models = (ImportBatch, Instrument, HoldingSnapshot, OrderImportBatch, Order,
              ExternalCashFlow, CashFlowCoverage)

    async def persisted_state():
        async with sessions() as check:
            return [
                [dict(row) for row in (await check.execute(
                    select(model.__table__).order_by(*model.__table__.primary_key.columns)
                )).mappings().all()]
                for model in models
            ]

    async with sessions() as session:
        await trading212.run_trading212_sync(session, client)
    before = await persisted_state()
    assert len(before[4]) == 1
    staged_closures = []

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def observe_closure(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("UPDATE INSTRUMENTS SET CLOSED_AT"):
            staged_closures.append(True)

    positions = []  # Would close the retained instrument if rollback failed.
    if case.endswith("memory-cross-page"):
        missing = copy.deepcopy(candidate)
        missing["order"].pop("id", None)
        missing["order"]["instrument"].pop("ticker", None)
        missing["order"]["instrument"].pop("isin", None)
        pages = [[candidate, missing], [conflicting]]
    else:
        pages = [[candidate], [conflicting]] if across_pages else [[candidate, conflicting]]
    order_requests.clear()
    async with sessions() as session:
        with pytest.raises(Trading212DataError) as rejected:
            await trading212.run_trading212_sync(session, client)
        assert rejected.value.code == code
        assert rejected.value.t212_endpoint == "orders"
        assert rejected.value.t212_phase == "import"
        assert "PRIVATE_" not in str(rejected.value)
        if code == "order_fill_identity_conflict":
            assert str(rejected.value) == "Trading 212 returned conflicting order fills."
        caplog.set_level("ERROR", logger=trading212.__name__)
        public = trading212._provider_error(rejected.value)
        assert public.detail == f"Trading 212 validation failed ({code})."
        assert f"code={code} endpoint=orders phase=import" in caplog.text
        assert "PRIVATE_" not in caplog.text
        assert "SYNTHETIC_" not in caplog.text
        assert all(record.exc_info is None for record in caplog.records)
        await session.commit()  # Must not resurrect earlier joined-session writes.
    assert order_requests == ([False, True] if across_pages else [False])
    assert staged_closures  # The failure came after the real closure UPDATE.
    assert await persisted_state() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("parent_id", [123, -123])
async def test_matching_fill_overlap_and_distinct_ids_import_once(sync_database, parent_id):
    from app.services.trading212 import Trading212Client

    _, sessions = sync_database
    reader = SyntheticReader()
    original = {
        "order": {
            "id": parent_id, "instrument": {"name": "Test", "ticker": "TEST_EQ", "isin": "GB00TEST"},
            "side": "SELL",
        },
        "fill": {
            "id": 101, "type": "TRADE", "filledAt": "2020-01-01T09:00:00Z",
            "quantity": -1, "walletImpact": {"currency": "GBP", "netValue": 9},
        },
    }
    overlap = {
        "order": {
            "id": f" {parent_id} ", "ticker": " TEST_EQ ",
            "instrument": {"name": " Test ", "isin": "GB00TEST", "extra": "ignored"},
            "side": "sell",
        },
        "fill": {
            "id": " 101 ", "type": "TRADE", "filledAt": "2020-01-01T10:00:00+01:00",
            "quantity": 1, "walletImpact": {"currency": "GBP", "netValue": -9, "extra": 7},
        },
        "extra": {"anything": True},
    }
    missing_evidence = copy.deepcopy(overlap)
    missing_evidence["order"].pop("id")
    missing_evidence["order"].pop("ticker")
    missing_evidence["order"]["instrument"].pop("isin")
    distinct = {**original, "fill": {**original["fill"], "id": 102}}
    calls = []
    positions, account = await reader.fetch_positions(), await reader.fetch_account_summary()

    def transport(request):
        if request.url.path == "/api/v0/equity/history/orders":
            second = "cursor" in request.url.params
            calls.append(second)
            return httpx.Response(200, json={
                "items": [overlap, missing_evidence, distinct,
                          {"fill": {"type": "STOCK_SPLIT", "id": 101}}]
                if second else [original],
                "nextPagePath": None if second else
                "/api/v0/equity/history/orders?cursor=123&limit=50",
            })
        payloads = {
            "/api/v0/equity/positions": positions,
            "/api/v0/equity/account/summary": account,
            "/api/v0/equity/history/transactions": {"items": [], "nextPagePath": None},
        }
        return httpx.Response(200, json=payloads[request.url.path])

    client = Trading212Client(
        api_key="SYNTHETIC_KEY", api_secret="SYNTHETIC_SECRET",
        transport=httpx.MockTransport(transport), page_delay=0,
    )
    for expected in ("imported", "unchanged"):
        async with sessions() as session:
            result = await trading212.run_trading212_sync(session, client)
            assert result.orders == expected
            if expected == "imported":
                assert result.order_rows == 2
    assert calls == [False, True, False, True]
    async with sessions() as check:
        orders = (await check.scalars(select(Order))).all()
        assert len(orders) == 2
        assert {(o.side, o.quantity, o.cost_proceeds_gbp) for o in orders} == {("Sell", 1, 9)}
        assert len({o.order_fingerprint for o in orders}) == 2


@pytest.mark.asyncio
async def test_prefetched_account_forbidden_rejects_without_writes(sync_database):
    _, sessions = sync_database

    class NoAccountReader(SyntheticReader):
        async def fetch_account_summary(self):
            response = httpx.Response(403, request=httpx.Request("GET", "https://broker.invalid"))
            raise httpx.HTTPStatusError("forbidden", request=response.request, response=response)

    async with sessions() as session:
        with pytest.raises(HTTPException) as rejected:
            await trading212.sync_trading212_all(
                force=False, _origin_guard=None, session=session, client=NoAccountReader(),
            )
        assert rejected.value.status_code == 400
    async with sessions() as check:
        assert await check.scalar(select(func.count()).select_from(Instrument)) == 0
        assert await check.scalar(select(func.count()).select_from(ImportBatch)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_method",
    [
        "fetch_positions",
        "fetch_transactions",
    ],
)
async def test_broker_failure_performs_no_database_work(sync_database, monkeypatch, failure_method):
    engine, sessions = sync_database
    statements = []
    commits = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def record_statement(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    @event.listens_for(engine.sync_engine, "commit")
    def record_commit(_connection):
        commits.append(True)

    async def fail():
        raise httpx.ConnectError("synthetic network failure")

    reader = SyntheticReader()
    monkeypatch.setattr(reader, failure_method, fail)
    async with sessions() as session:
        with pytest.raises(HTTPException) as error:
            await trading212.sync_trading212_all(
                force=False,
                _origin_guard=None,
                session=session,
                client=reader,
            )
        assert error.value.status_code == 502
    assert statements == []
    assert commits == []

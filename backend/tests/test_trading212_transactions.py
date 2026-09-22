"""Atomic sync regressions: synthetic SQLite files and an in-process broker fake."""

import datetime as dt
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import (
    Base,
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

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
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
                }
            ]

    for expected_snapshot, expected_cash in [("imported", 1), ("unchanged", 0)]:
        commits.clear()
        async with sessions() as session:
            result = await trading212.sync_trading212_all(
                force=False,
                _origin_guard=None,
                session=session,
                client=CompleteReader(),
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
                (ExternalCashFlow, 1),
                (CashFlowCoverage, 1),
            ]:
                assert await check.scalar(select(func.count()).select_from(model)) == expected_count


@pytest.mark.asyncio
async def test_prefetched_account_forbidden_preserves_no_invented_cash_fallback(sync_database):
    _, sessions = sync_database

    class NoAccountReader(SyntheticReader):
        async def fetch_account_summary(self):
            response = httpx.Response(403, request=httpx.Request("GET", "https://broker.invalid"))
            raise httpx.HTTPStatusError("forbidden", request=response.request, response=response)

    async with sessions() as session:
        result = await trading212.sync_trading212_all(
            force=False,
            _origin_guard=None,
            session=session,
            client=NoAccountReader(),
        )
    assert result.snapshot_rows == 1
    async with sessions() as check:
        assert await check.scalar(select(func.count()).select_from(Instrument)) == 1
        assert await check.scalar(select(Instrument.is_cash)) is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_method",
    [
        "fetch_positions",
        "fetch_account_summary",
        "fetch_historical_orders",
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

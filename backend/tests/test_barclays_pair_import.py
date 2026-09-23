"""Atomic, fail-closed Barclays holdings+orders import (synthetic workbooks only)."""

from __future__ import annotations

import datetime as dt
import io

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, HoldingSnapshot, ImportBatch, Instrument, Order, OrderImportBatch
from app.services import barclays_pair_import as pair
from app.services.barclays_pair_import import BarclaysExportInvalid, import_barclays_pair

ACCOUNT = "ID0000000-001 (Investment ISA)"
HOLD_HEADER = [
    "Investment", "Identifier", "Quantity Held", "Last Price", "Last Price CCY",
    "Value", "Value CCY", "FX Rate", "Last Price (p)", "Value (£)",
    "Book Cost", "Book Cost CCY", "Average FX Rate", "Book Cost (£)", "% Change",
]  # fmt: skip
ORDER_HEADER = [
    "Investment", "Date", "Order Status", "Account", "Buy/Sell", "Quantity",
    "Cost/Proceeds", "Country",
]  # fmt: skip


def _book(sheet: str, title: list[object] | None, header: list[str], rows: list[list[object]]):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    if title:
        ws.append(title)
        ws.append([])
    ws.append(header)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def holding(name: str, ident: str, qty: object = 10, gbp: object = 100.0) -> list[object]:
    return [name, ident, qty, 1.0, "GBP", gbp, "GBP", 1, 100, gbp, 90, "GBP", 1, 90, 11.1]


def holdings_xls(*rows: list[object]) -> bytes:
    rows = rows or (holding("Alpha Fund", "AAA"), holding("Beta plc", "BBB"))
    return _book(ACCOUNT, [ACCOUNT], HOLD_HEADER, [*rows, ["Cash", "", None, None, None,
                 50.0, "GBP", None, None, 50.0, None, None, None, None, None]])  # fmt: skip


def order(name: str, day: int, side: str = "Buy", cost: object = 1500.0, status="Completed"):
    return [name, dt.datetime(2026, 9, day, 10, 0), status, "Investment ISA", side, 10, cost, "GB"]


def orders_xls(*rows: list[object]) -> bytes:
    rows = rows or (order("Alpha Fund", 1), order("Beta plc", 2, "Sell", 800.0))
    return _book("Orders", None, ORDER_HEADER, list(rows))


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


async def _count(session, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


TODAY = dt.date(2026, 9, 23)


@pytest.mark.asyncio
async def test_imports_pair_in_one_transaction_and_is_idempotent(session):
    result = await import_barclays_pair(session, holdings_xls(), orders_xls(), as_of=TODAY)
    assert result.holdings == "imported" and result.orders == "imported"
    assert result.account_name == ACCOUNT
    assert result.holding_rows == 3 and result.new_orders == 2
    assert await _count(session, ImportBatch) == 1
    assert await _count(session, Order) == 2
    batch = (await session.execute(select(ImportBatch))).scalar_one()
    assert batch.as_of_date == TODAY

    again = await import_barclays_pair(session, holdings_xls(), orders_xls(), as_of=TODAY)
    assert (again.holdings, again.orders) == ("unchanged", "unchanged")
    assert await _count(session, ImportBatch) == 1 and await _count(session, Order) == 2


@pytest.mark.asyncio
async def test_failure_in_orders_rolls_back_the_holdings_snapshot(session, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("orders failed")

    monkeypatch.setattr(pair, "ingest_parsed_orders", boom)
    with pytest.raises(RuntimeError):
        await import_barclays_pair(session, holdings_xls(), orders_xls(), as_of=TODAY)
    assert await _count(session, ImportBatch) == 0
    assert await _count(session, HoldingSnapshot) == 0
    assert await _count(session, Instrument) == 0
    assert await _count(session, OrderImportBatch) == 0


@pytest.mark.parametrize(
    "rows",
    [
        [holding("Alpha Fund", "")],  # security without identifier
        [holding("Alpha Fund", "AAA", qty="n/a")],  # unparseable quantity
        [holding("Alpha Fund", "AAA", gbp=None)],  # missing GBP value
        [holding("Alpha Fund", "AAA", gbp="nan")],  # non-finite value
        [["", "AAA", 10, 1, "GBP", 1, "GBP", 1, 1, 1, 1, "GBP", 1, 1, 1]],  # nameless row
    ],
)
@pytest.mark.asyncio
async def test_malformed_holdings_rows_fail_closed_without_writes(session, rows):
    with pytest.raises(BarclaysExportInvalid):
        await import_barclays_pair(session, holdings_xls(*rows), orders_xls(), as_of=TODAY)
    assert await _count(session, ImportBatch) == 0 and await _count(session, Order) == 0


@pytest.mark.parametrize(
    "row",
    [
        ["Alpha Fund", "not a date", "Completed", "Investment ISA", "Buy", 10, 1500, "GB"],
        ["Alpha Fund", dt.datetime(2026, 9, 1), "Completed", "Investment ISA", "Hold", 10, 1, "GB"],
        ["Alpha Fund", dt.datetime(2026, 9, 1), "Completed", "Investment ISA", "Buy", 10, None, "GB"],
        ["Alpha Fund", dt.datetime(2026, 9, 1), "Completed", "Other ISA", "Buy", 10, 1500, "GB"],
    ],
)  # fmt: skip
@pytest.mark.asyncio
async def test_malformed_completed_orders_fail_closed(session, row):
    with pytest.raises(BarclaysExportInvalid):
        await import_barclays_pair(
            session, holdings_xls(), orders_xls(order("Beta plc", 2), row), as_of=TODAY
        )
    assert await _count(session, ImportBatch) == 0


@pytest.mark.asyncio
async def test_non_completed_orders_are_ignored_not_rejected(session):
    result = await import_barclays_pair(
        session,
        holdings_xls(),
        orders_xls(order("Alpha Fund", 1), order("Beta plc", 3, status="Cancelled", cost=None)),
        as_of=TODAY,
    )
    assert result.new_orders == 1


@pytest.mark.asyncio
async def test_multiple_accounts_or_empty_snapshot_are_rejected(session):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.load_workbook(io.BytesIO(holdings_xls()))
    other = wb.copy_worksheet(wb.active)
    other.title = "ID0000000-002 (Investment ISA)"
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(BarclaysExportInvalid, match="one account"):
        await import_barclays_pair(session, buf.getvalue(), orders_xls(), as_of=TODAY)

    empty = _book(ACCOUNT, [ACCOUNT], HOLD_HEADER, [])
    with pytest.raises(BarclaysExportInvalid, match="no holdings"):
        await import_barclays_pair(session, empty, orders_xls(), as_of=TODAY)


@pytest.mark.asyncio
async def test_mass_closure_needs_attention_instead_of_closing_holdings(session):
    many = [holding(f"Fund {i}", f"F{i:02d}") for i in range(8)]
    await import_barclays_pair(session, holdings_xls(*many), orders_xls(), as_of=TODAY)
    # Next day only one security appears and no sells explain the rest.
    with pytest.raises(BarclaysExportInvalid, match="would close"):
        await import_barclays_pair(
            session,
            holdings_xls(many[0]),
            orders_xls(order("Fund 0", 5)),
            as_of=TODAY + dt.timedelta(days=1),
        )
    open_count = (
        await session.execute(
            select(func.count()).select_from(Instrument).where(Instrument.closed_at.is_(None))
        )
    ).scalar_one()
    assert open_count == 9  # 8 funds + cash, none closed


@pytest.mark.asyncio
async def test_closure_explained_by_sells_is_allowed(session):
    many = [holding(f"Fund {i}", f"F{i:02d}") for i in range(4)]
    await import_barclays_pair(session, holdings_xls(*many), orders_xls(), as_of=TODAY)
    sells = [order(f"Fund {i}", 5, "Sell", 900.0) for i in (1, 2, 3)]
    result = await import_barclays_pair(
        session, holdings_xls(many[0]), orders_xls(*sells), as_of=TODAY + dt.timedelta(days=1)
    )
    assert result.closed == 3

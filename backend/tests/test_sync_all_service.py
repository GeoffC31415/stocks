"""Inbox sync-all service contracts (synthetic files, in-memory database)."""

from __future__ import annotations

import datetime as dt
import io
import os
from pathlib import Path  # noqa: TC003 - pytest tmp_path annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, ImportBatch, Order, OrderImportBatch
from app.services.sync_all_service import sync_inbox


def _hl_holdings(created: str, units: str) -> bytes:
    return (
        "HL Fund & Share Account, , , ,\n"
        "Client Name:,Mr Test Person, , ,\n"
        "Client Number:, 1234567, , ,\n"
        f"Spreadsheet created at,{created}, , ,\n"
        "\n"
        "Code,Stock,Units held,Price (pence),Value (\u00a3),Cost (\u00a3),Gain/loss (\u00a3),Gain/loss (%)\n"
        f'ABC,Example Fund,"{units}","100.0","{float(units):.2f}","5.00","5.00","100"\n'
    ).encode()


HL_ACTIVITY = (
    "Portfolio Summary\n"
    "Client Name:,Mr Test Person\n"
    "Client Number:,1234567\n"
    "Valuation as at,20-09-2026 17:00\n"
    "\n"
    "Trade date,Settle date,Reference,Description,Unit cost (p),Quantity,Value (\u00a3)\n"
    '"18/09/2026","22/09/2026","B123","Example Fund 10 @ 100.0","100.0","10","-5000.00"\n'
).encode("utf-8")


def _barclays_holdings(value: float) -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ID0000000-001 (Investment ISA)"
    ws.append(["ID0000000-001 (Investment ISA)"])
    ws.append([])
    ws.append(
        [
            "Investment",
            "Identifier",
            "Quantity Held",
            "Last Price",
            "Last Price CCY",
            "Value",
            "Value CCY",
            "FX Rate",
            "Last Price (p)",
        ]
    )
    ws.append(["Cash", None, None, None, None, 10.0, "GBP", None, None])
    ws.append(["Example Plc", "EXM", 2, 1.5, "GBP", value, "GBP", 1, 150])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _write(inbox: Path, name: str, data: bytes, when: dt.datetime) -> Path:
    path = inbox / name
    path.write_bytes(data)
    ts = when.timestamp()
    os.utime(path, (ts, ts))
    return path


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        yield db
    await engine.dispose()


async def _count(session, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def test_routes_by_content_dates_and_moves_processed(session, tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    # Deliberately misleading filenames.
    _write(
        inbox,
        "portfolio-summary.csv",
        _hl_holdings("21-09-2026 19:11", "10"),
        dt.datetime(2026, 9, 21, 19, 11),
    )
    _write(inbox, "account-summary.csv", HL_ACTIVITY, dt.datetime(2026, 9, 20, 17, 0))
    _write(inbox, "LoadDocstore.xls", _barclays_holdings(3.0), dt.datetime(2026, 9, 19, 12, 0))
    _write(inbox, "notes.csv", b"<html>login</html>", dt.datetime(2026, 9, 19, 12, 0))

    report = await sync_inbox(session, inbox)

    by_kind = {item.kind: item for item in report.files if item.kind}
    assert by_kind["hl_holdings"].status == "imported"
    assert by_kind["hl_activity"].status == "imported"
    assert by_kind["barclays_holdings"].status == "imported"
    rejected = [item for item in report.files if item.status == "rejected"]
    assert [item.filename for item in rejected] == ["notes.csv"]

    batches = (await session.execute(select(ImportBatch).order_by(ImportBatch.id))).scalars().all()
    # Barclays has no internal date: file modification time is used.
    assert [b.as_of_date for b in batches] == [dt.date(2026, 9, 19), dt.date(2026, 9, 21)]
    assert await _count(session, OrderImportBatch) == 1
    assert await _count(session, Order) == 1

    processed = list((inbox / "processed").rglob("*"))
    assert len([p for p in processed if p.is_file()]) == 3
    assert (inbox / "rejected" / "notes.csv").exists()
    assert not (inbox / "portfolio-summary.csv").exists()


async def test_rerun_and_duplicate_files_are_unchanged(session, tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    data = _hl_holdings("21-09-2026 19:11", "10")
    _write(inbox, "a.csv", data, dt.datetime(2026, 9, 21, 19, 11))
    first = await sync_inbox(session, inbox)
    assert [f.status for f in first.files] == ["imported"]

    _write(inbox, "a (1).csv", data, dt.datetime(2026, 9, 21, 19, 12))
    _write(inbox, "b.csv", HL_ACTIVITY, dt.datetime(2026, 9, 20, 17, 0))
    _write(inbox, "b (1).csv", HL_ACTIVITY, dt.datetime(2026, 9, 20, 17, 1))
    second = await sync_inbox(session, inbox)
    statuses = sorted(f.status for f in second.files)
    assert statuses == ["imported", "unchanged", "unchanged"]
    assert await _count(session, ImportBatch) == 1
    assert await _count(session, OrderImportBatch) == 1


async def test_snapshots_import_in_chronological_order(session, tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    # Newer file sorts first by name; the older one must still import first.
    _write(inbox, "a.csv", _hl_holdings("21-09-2026 19:11", "12"), dt.datetime(2026, 9, 21))
    _write(inbox, "z.csv", _hl_holdings("20-09-2026 17:00", "10"), dt.datetime(2026, 9, 20))
    await sync_inbox(session, inbox)
    batches = (await session.execute(select(ImportBatch).order_by(ImportBatch.id))).scalars().all()
    assert [b.as_of_date for b in batches] == [dt.date(2026, 9, 20), dt.date(2026, 9, 21)]


async def test_dry_run_writes_nothing_and_moves_nothing(session, tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _write(inbox, "a.csv", _hl_holdings("21-09-2026 19:11", "10"), dt.datetime(2026, 9, 21))
    _write(inbox, "bad.csv", b"x,y\n1,2\n", dt.datetime(2026, 9, 21))
    report = await sync_inbox(session, inbox, dry_run=True)
    assert sorted(f.status for f in report.files) == ["new", "rejected"]
    assert await _count(session, ImportBatch) == 0
    assert (inbox / "a.csv").exists() and (inbox / "bad.csv").exists()


async def test_import_failure_is_isolated_and_file_left_in_place(
    session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _write(inbox, "h.csv", _hl_holdings("21-09-2026 19:11", "10"), dt.datetime(2026, 9, 21))
    _write(inbox, "o.csv", HL_ACTIVITY, dt.datetime(2026, 9, 20))

    from app.services import sync_all_service

    async def boom(*_args, **_kwargs):
        raise RuntimeError("parser exploded")

    monkeypatch.setitem(sync_all_service._IMPORTERS, "hl_activity", boom)
    report = await sync_inbox(session, inbox)
    status = {f.kind: f.status for f in report.files}
    assert status == {"hl_holdings": "imported", "hl_activity": "failed"}
    assert (inbox / "o.csv").exists()
    assert await _count(session, OrderImportBatch) == 0
    assert await _count(session, ImportBatch) == 1


async def test_extra_sources_are_scanned_without_moving(session, tmp_path: Path) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    _write(
        downloads,
        "account-summary (9).csv",
        _hl_holdings("20-09-2026 17:00", "10"),
        dt.datetime(2026, 9, 20),
    )
    _write(downloads, "holiday.csv", b"a,b\n", dt.datetime(2026, 9, 20))
    report = await sync_inbox(session, inbox, extra_sources=[downloads])
    assert [(f.filename, f.status) for f in report.files] == [
        ("account-summary (9).csv", "imported")
    ]
    # Files outside the inbox are never moved or deleted.
    assert (downloads / "account-summary (9).csv").exists()
    assert await _count(session, ImportBatch) == 1

"""Content-based broker export classification (synthetic fixtures only)."""

from __future__ import annotations

import datetime as dt
import io

import pytest

from app.services.export_classifier import ExportKind, UnrecognisedExport, classify_export

HL_HOLDINGS = (
    "HL Fund & Share Account, , , ,\n"
    "Client Name:,Mr Test Person, , ,\n"
    "Client Number:, 1234567, , ,\n"
    "Spreadsheet created at,21-09-2026 19:11, , ,\n"
    "\n"
    'Stock value:,"1,000.00", , ,\n'
    "Code,Stock,Units held,Price (pence),Value (\u00a3)\n"
    'ABC,Example Fund,"10","100.0","10.00"\n'
).encode("utf-8")

HL_ACTIVITY = (
    "Portfolio Summary\n"
    "Client Name:,Mr Test Person\n"
    "Client Number:,1234567\n"
    "Valuation as at,20-09-2026 17:00\n"
    "\n"
    "Trade date,Settle date,Reference,Description,Unit cost (p),Quantity,Value (\u00a3)\n"
    '"18/09/2026","22/09/2026","B123","Example Fund 10 @ 100.0","100.0","10","-10.00"\n'
).encode("cp1252")


def _xls(rows: list[list[object]]) -> bytes:
    """Build an in-memory spreadsheet readable by calamine (xlsx is fine for detection)."""
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ID0000000-001 (Investment ISA)"
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_hl_holdings_detected_with_metadata_date() -> None:
    result = classify_export("anything.csv", HL_HOLDINGS)
    assert result.kind is ExportKind.HL_HOLDINGS
    assert result.as_of == dt.date(2026, 9, 21)


def test_hl_activity_detected_even_when_named_like_holdings() -> None:
    result = classify_export("account-summary (3).csv", HL_ACTIVITY)
    assert result.kind is ExportKind.HL_ACTIVITY
    assert result.as_of == dt.date(2026, 9, 20)


def test_barclays_holdings_and_orders_share_a_filename() -> None:
    holdings = _xls(
        [
            ["ID0000000-001 (Investment ISA)"],
            [],
            ["Investment", "Identifier", "Quantity Held", "Last Price", "Value"],
            ["Cash", None, None, None, 1.0],
        ]
    )
    orders = _xls(
        [
            ["ID0000000-001 (Investment ISA)"],
            [],
            ["Investment", "Date", "Order Status", "Account", "Buy/Sell", "Quantity"],
            ["Example", "2026-09-18 10:00:00", "Completed", "Investment ISA", "Buy", 1],
        ]
    )
    assert classify_export("LoadDocstore.xls", holdings).kind is ExportKind.BARCLAYS_HOLDINGS
    assert classify_export("LoadDocstore.xls", orders).kind is ExportKind.BARCLAYS_ORDERS
    # Barclays holdings carry no date of their own.
    assert classify_export("LoadDocstore.xls", holdings).as_of is None


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"<!DOCTYPE html><html><body>Please log in</body></html>",
        b"  \n<html><head></head></html>",
        b"Some,Other,CSV\n1,2,3\n",
        b"\xd0\xcf\x11\xe0 not really a workbook",
    ],
)
def test_unrecognised_or_login_pages_are_rejected(data: bytes) -> None:
    with pytest.raises(UnrecognisedExport):
        classify_export("account-summary.csv", data)


def test_hl_holdings_without_created_date_is_rejected() -> None:
    broken = HL_HOLDINGS.replace(b"Spreadsheet created at,21-09-2026 19:11", b"")
    with pytest.raises(UnrecognisedExport):
        classify_export("x.csv", broken)

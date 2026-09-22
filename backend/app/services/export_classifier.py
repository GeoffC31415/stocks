"""Identify broker export files from their content, never their filename.

Broker downloads reuse names: Barclays ``LoadDocstore.xls`` is used for both
holdings and order history, and HL ``account-summary``/``portfolio-summary``
files have previously been routed to the wrong importer. Classification here
is deliberately strict: anything not positively identified is rejected so an
HTML login page or an unexpected layout can never reach an importer.
"""

from __future__ import annotations

import csv
import datetime as dt
import enum
import io
from dataclasses import dataclass

from python_calamine import CalamineWorkbook


class ExportKind(enum.StrEnum):
    HL_HOLDINGS = "hl_holdings"
    HL_ACTIVITY = "hl_activity"
    BARCLAYS_HOLDINGS = "barclays_holdings"
    BARCLAYS_ORDERS = "barclays_orders"


class UnrecognisedExport(ValueError):
    """The file is not a supported broker export."""


@dataclass(frozen=True)
class ClassifiedExport:
    kind: ExportKind
    # Date/time the broker generated the file, when the file records it.
    generated_at: dt.datetime | None

    @property
    def as_of(self) -> dt.date | None:
        return self.generated_at.date() if self.generated_at else None


_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_ZIP_MAGIC = b"PK\x03\x04"


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")


def _metadata_datetime(rows: list[list[str]], label: str) -> dt.datetime | None:
    for row in rows[:10]:
        if len(row) > 1 and row[0].strip().casefold() == label.casefold():
            try:
                return dt.datetime.strptime(row[1].strip(), "%d-%m-%Y %H:%M")
            except ValueError:
                return None
    return None


def _has_header(rows: list[list[str]], *cells: str) -> bool:
    wanted = [c.casefold() for c in cells]
    for row in rows[:40]:
        norm = [c.strip().casefold() for c in row]
        if norm[: len(wanted)] == wanted:
            return True
    return False


def _classify_csv(data: bytes) -> ClassifiedExport:
    text = _decode(data)
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or not rows[0]:
        raise UnrecognisedExport("Empty CSV.")
    first = rows[0][0].strip()
    if first.startswith("HL ") and _has_header(rows, "Code"):
        created = _metadata_datetime(rows, "Spreadsheet created at")
        if created is None:
            raise UnrecognisedExport("HL holdings file has no 'Spreadsheet created at' date.")
        return ClassifiedExport(ExportKind.HL_HOLDINGS, created)
    if first == "Portfolio Summary" and _has_header(rows, "Trade date", "Settle date", "Reference"):
        valued = _metadata_datetime(rows, "Valuation as at")
        if valued is None:
            raise UnrecognisedExport("HL activity file has no 'Valuation as at' date.")
        return ClassifiedExport(ExportKind.HL_ACTIVITY, valued)
    raise UnrecognisedExport("CSV is not a recognised HL export.")


def _classify_workbook(data: bytes) -> ClassifiedExport:
    try:
        wb = CalamineWorkbook.from_filelike(io.BytesIO(data))
        sheets = [wb.get_sheet_by_name(name).to_python() for name in wb.sheet_names]
    except Exception as exc:  # calamine raises several unrelated types
        raise UnrecognisedExport("Workbook could not be read.") from exc
    kinds: set[ExportKind] = set()
    for table in sheets:
        for row in table[:6]:
            cells = {str(c).strip().casefold() for c in row if c is not None}
            if {"investment", "identifier", "quantity held"} <= cells:
                kinds.add(ExportKind.BARCLAYS_HOLDINGS)
            elif {"investment", "date", "order status", "buy/sell"} <= cells:
                kinds.add(ExportKind.BARCLAYS_ORDERS)
    if len(kinds) != 1:
        raise UnrecognisedExport("Workbook is not a single recognised Barclays export.")
    return ClassifiedExport(kinds.pop(), None)


def classify_export(filename: str, data: bytes) -> ClassifiedExport:
    """Return the export kind; ``filename`` is used only in error messages."""
    head = data[:512].lstrip().lower()
    if not data.strip():
        raise UnrecognisedExport(f"{filename}: file is empty.")
    if head.startswith((b"<!doctype", b"<html", b"<?xml")) or b"<html" in head:
        raise UnrecognisedExport(f"{filename}: file is an HTML page, not an export.")
    try:
        if data.startswith((_OLE_MAGIC, _ZIP_MAGIC)):
            return _classify_workbook(data)
        return _classify_csv(data)
    except UnrecognisedExport as exc:
        raise UnrecognisedExport(f"{filename}: {exc}") from exc

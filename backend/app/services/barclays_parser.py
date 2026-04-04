from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from python_calamine import CalamineWorkbook

# Normalized header keys -> possible Barclays labels (lowercase match)
HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "investment": ("investment",),
    "identifier": ("identifier",),
    "quantity_held": ("quantity held",),
    "last_price": ("last price",),
    "last_price_ccy": ("last price ccy",),
    "value": ("value",),
    "value_ccy": ("value ccy",),
    "fx_rate": ("fx rate",),
    "last_price_p": ("last price (p)", "last price (p)", "last price(p)"),
    "value_gbp": ("value (£)", "value (gbp)"),
    "book_cost": ("book cost",),
    "book_cost_ccy": ("book cost ccy",),
    "average_fx_rate": ("average fx rate",),
    "book_cost_gbp": ("book cost (£)", "book cost (gbp)"),
    "pct_change": ("% change", "percent change"),
}


def _norm_header(cell: Any) -> str:
    if cell is None:
        return ""
    s = str(cell).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _build_header_map(header_row: list[Any]) -> dict[str, int]:
    by_col = {_norm_header(h): i for i, h in enumerate(header_row) if _norm_header(h)}
    result: dict[str, int] = {}
    for key, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias in by_col:
                result[key] = by_col[alias]
                break
    return result


def _cell(row: list[Any], idx: int | None) -> Any:
    if idx is None or idx >= len(row):
        return None
    return row[idx]


def _to_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).replace(",", "").strip())
    except ValueError:
        return None


def _to_str(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


@dataclass(frozen=True)
class ParsedHoldingRow:
    account_name: str
    investment: str
    identifier: str
    quantity: float | None
    last_price: float | None
    last_price_ccy: str | None
    value: float | None
    value_ccy: str | None
    fx_rate: float | None
    last_price_pence: float | None
    value_gbp: float | None
    book_cost: float | None
    book_cost_ccy: str | None
    average_fx_rate: float | None
    book_cost_gbp: float | None
    pct_change: float | None
    is_cash: bool


def parse_barclays_xls_bytes(
    data: bytes,
    *,
    default_as_of_date: date | None = None,
) -> tuple[list[ParsedHoldingRow], date]:
    """
    Parse Barclays Stockbrokers LoadDocstore-style .xls (all sheets).
    Returns rows and as_of date (defaults to default_as_of_date or today).
    """
    wb = CalamineWorkbook.from_filelike(io.BytesIO(data))
    as_of = default_as_of_date or date.today()
    rows_out: list[ParsedHoldingRow] = []

    for sheet_name in wb.sheet_names:
        account_name = (sheet_name or "Account").strip()
        sh = wb.get_sheet_by_name(sheet_name)
        table = sh.to_python()
        if not table or len(table) < 4:
            continue

        header_idx = None
        for i, row in enumerate(table[:6]):
            if not row:
                continue
            cells = [_norm_header(c) for c in row]
            if "investment" in cells and "identifier" in cells:
                header_idx = i
                break
        if header_idx is None:
            continue

        header_row = table[header_idx]
        col = _build_header_map(header_row)
        if "investment" not in col or "identifier" not in col:
            continue

        for row in table[header_idx + 1 :]:
            if not row or all(c == "" or c is None for c in row):
                continue
            inv = _to_str(_cell(row, col.get("investment")))
            if not inv:
                continue
            id_raw = _cell(row, col.get("identifier"))
            identifier = _to_str(id_raw) or ""
            is_cash = inv.strip().lower() == "cash"
            if is_cash:
                identifier = "CASH"

            rows_out.append(
                ParsedHoldingRow(
                    account_name=account_name,
                    investment=inv,
                    identifier=identifier,
                    quantity=_to_float(_cell(row, col.get("quantity_held"))),
                    last_price=_to_float(_cell(row, col.get("last_price"))),
                    last_price_ccy=_to_str(_cell(row, col.get("last_price_ccy"))),
                    value=_to_float(_cell(row, col.get("value"))),
                    value_ccy=_to_str(_cell(row, col.get("value_ccy"))),
                    fx_rate=_to_float(_cell(row, col.get("fx_rate"))),
                    last_price_pence=_to_float(_cell(row, col.get("last_price_p"))),
                    value_gbp=_to_float(_cell(row, col.get("value_gbp"))),
                    book_cost=_to_float(_cell(row, col.get("book_cost"))),
                    book_cost_ccy=_to_str(_cell(row, col.get("book_cost_ccy"))),
                    average_fx_rate=_to_float(_cell(row, col.get("average_fx_rate"))),
                    book_cost_gbp=_to_float(_cell(row, col.get("book_cost_gbp"))),
                    pct_change=_to_float(_cell(row, col.get("pct_change"))),
                    is_cash=is_cash,
                )
            )

    return rows_out, as_of

from __future__ import annotations

import csv
import datetime as dt
import io
import re
from collections.abc import Iterable
from typing import Any

from app.services.barclays_order_parser import DRIP_THRESHOLD_GBP, ParsedOrderRow
from app.services.barclays_parser import ParsedHoldingRow

HL_ACCOUNT_NAME = "HL Fund & Share Account"

_TRADE_REF_RE = re.compile(r"^[BS]\d+$", re.IGNORECASE)
_DESCRIPTION_TRADE_SUFFIX_RE = re.compile(r"\s+[\d,.]+\s+@\s+[\d,.]+\s*$")


def _decode_csv(data: bytes) -> list[list[str]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252")
    return [row for row in csv.reader(io.StringIO(text))]


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _header_index(rows: Iterable[list[str]], first_column: str) -> int | None:
    target = first_column.casefold()
    for index, row in enumerate(rows):
        if row and _clean(row[0]).casefold() == target:
            return index
    return None


def _to_float(value: str) -> float | None:
    cleaned = _clean(value)
    if not cleaned or cleaned.casefold() == "n/a":
        return None
    try:
        return float(cleaned.replace(",", ""))
    except ValueError:
        return None


def _to_date(value: str, *, fmt: str) -> dt.date | None:
    cleaned = _clean(value)
    if not cleaned:
        return None
    try:
        return dt.datetime.strptime(cleaned, fmt).date()
    except ValueError:
        return None


def _metadata_value(rows: list[list[str]], label: str) -> str | None:
    label_norm = label.casefold()
    for row in rows:
        if row and _clean(row[0]).casefold() == label_norm and len(row) > 1:
            value = _clean(row[1])
            return value or None
    return None


def _holding_as_of(rows: list[list[str]]) -> dt.date:
    created_at = _metadata_value(rows, "Spreadsheet created at")
    if created_at is None:
        return dt.date.today()
    parsed = _to_date(created_at, fmt="%d-%m-%Y %H:%M")
    return parsed or dt.date.today()


def parse_hl_holdings_csv_bytes(data: bytes) -> tuple[list[ParsedHoldingRow], dt.date]:
    rows = _decode_csv(data)
    header_idx = _header_index(rows, "Code")
    if header_idx is None:
        return [], _holding_as_of(rows)

    header = [_clean(cell).casefold() for cell in rows[header_idx]]
    col = {name: idx for idx, name in enumerate(header) if name}
    required = {"code", "stock", "units held", "price (pence)", "value (£)", "cost (£)"}
    if not required.issubset(col):
        return [], _holding_as_of(rows)

    client_name = _metadata_value(rows, "Client Name")
    account_label = HL_ACCOUNT_NAME
    if client_name:
        account_label = f"HL Fund & Share Account ({client_name})"

    parsed_rows: list[ParsedHoldingRow] = []
    for row in rows[header_idx + 1 :]:
        code = _clean(row[col["code"]]) if col["code"] < len(row) else ""
        stock = _clean(row[col["stock"]]) if col["stock"] < len(row) else ""
        if not code and stock.casefold() == "totals":
            break
        if not code or not stock:
            continue

        parsed_rows.append(
            ParsedHoldingRow(
                account_name=account_label,
                investment=stock,
                identifier=code,
                quantity=_to_float(row[col["units held"]]) if col["units held"] < len(row) else None,
                last_price=None,
                last_price_ccy="GBX",
                value=None,
                value_ccy="GBP",
                fx_rate=None,
                last_price_pence=(
                    _to_float(row[col["price (pence)"]])
                    if col["price (pence)"] < len(row)
                    else None
                ),
                value_gbp=_to_float(row[col["value (£)"]]) if col["value (£)"] < len(row) else None,
                book_cost=None,
                book_cost_ccy="GBP",
                average_fx_rate=None,
                book_cost_gbp=_to_float(row[col["cost (£)"]]) if col["cost (£)"] < len(row) else None,
                pct_change=(
                    _to_float(row[col["gain/loss (%)"]])
                    if "gain/loss (%)" in col and col["gain/loss (%)"] < len(row)
                    else None
                ),
                is_cash=False,
            )
        )

    return parsed_rows, _holding_as_of(rows)


def _parse_trade_date(value: str) -> dt.datetime | None:
    trade_date = _to_date(value, fmt="%d/%m/%Y")
    if trade_date is None:
        return None
    return dt.datetime.combine(trade_date, dt.time.min, tzinfo=dt.UTC)


def _security_name_from_description(description: str) -> str:
    return _DESCRIPTION_TRADE_SUFFIX_RE.sub("", _clean(description)).strip()


def parse_hl_activity_csv_bytes(
    data: bytes,
    *,
    drip_threshold_gbp: float = DRIP_THRESHOLD_GBP,
) -> list[ParsedOrderRow]:
    rows = _decode_csv(data)
    header_idx = _header_index(rows, "Trade date")
    if header_idx is None:
        return []

    header = [_clean(cell).casefold() for cell in rows[header_idx]]
    col = {name: idx for idx, name in enumerate(header) if name}
    required = {
        "trade date",
        "reference",
        "description",
        "unit cost (p)",
        "quantity",
        "value (£)",
    }
    if not required.issubset(col):
        return []

    client_name = _metadata_value(rows, "Client Name")
    account_label = HL_ACCOUNT_NAME
    if client_name:
        account_label = f"HL Fund & Share Account ({client_name})"

    parsed_rows: list[ParsedOrderRow] = []
    for row in rows[header_idx + 1 :]:
        reference = _clean(row[col["reference"]]) if col["reference"] < len(row) else ""
        if not _TRADE_REF_RE.match(reference):
            continue

        unit_cost = _to_float(row[col["unit cost (p)"]]) if col["unit cost (p)"] < len(row) else None
        quantity = _to_float(row[col["quantity"]]) if col["quantity"] < len(row) else None
        value = _to_float(row[col["value (£)"]]) if col["value (£)"] < len(row) else None
        if unit_cost is None or quantity is None or value is None:
            continue

        order_date = _parse_trade_date(row[col["trade date"]])
        if order_date is None:
            continue

        side = "Buy" if reference.upper().startswith("B") else "Sell"
        cost_proceeds_gbp = abs(value)
        security_name = _security_name_from_description(row[col["description"]])
        if not security_name:
            continue

        parsed_rows.append(
            ParsedOrderRow(
                security_name=security_name,
                order_date=order_date,
                order_status="Completed",
                account_name=account_label,
                side=side,
                quantity=quantity,
                cost_proceeds_gbp=cost_proceeds_gbp,
                country="GB",
                is_drip=side.lower() == "buy" and cost_proceeds_gbp < drip_threshold_gbp,
            )
        )

    return parsed_rows

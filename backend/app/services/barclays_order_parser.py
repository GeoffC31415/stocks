from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import UTC, datetime

from python_calamine import CalamineWorkbook

DRIP_THRESHOLD_GBP = 1000.0


def _to_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def _to_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


@dataclass
class ParsedOrderRow:
    security_name: str
    order_date: datetime
    order_status: str
    account_name: str
    side: str
    quantity: float | None
    cost_proceeds_gbp: float | None
    country: str | None
    is_drip: bool


def parse_barclays_order_xls_bytes(
    data: bytes,
    *,
    drip_threshold_gbp: float = DRIP_THRESHOLD_GBP,
) -> list[ParsedOrderRow]:
    """
    Parse a Barclays order history .xls file.
    Orders with Buy cost < drip_threshold_gbp are classified as dividend reinvestments (DRIP).
    """
    wb = CalamineWorkbook.from_filelike(io.BytesIO(data))
    rows_out: list[ParsedOrderRow] = []

    for sheet_name in wb.sheet_names:
        sh = wb.get_sheet_by_name(sheet_name)
        table = sh.to_python()

        header_idx = None
        for i, row in enumerate(table[:6]):
            cells = [str(c).strip().lower() if c is not None else "" for c in row]
            if "investment" in cells and "date" in cells:
                header_idx = i
                break
        if header_idx is None:
            continue

        header = [str(c).strip().lower() if c is not None else "" for c in table[header_idx]]
        col: dict[str, int] = {h: idx for idx, h in enumerate(header) if h}

        inv_col = col.get("investment")
        date_col = col.get("date")
        status_col = col.get("order status")
        acct_col = col.get("account")
        side_col = col.get("buy/sell")
        qty_col = col.get("quantity")
        cost_col = col.get("cost/proceeds")
        country_col = col.get("country")

        for row in table[header_idx + 1 :]:
            if not row or all(c is None or c == "" for c in row):
                continue

            inv = (
                str(row[inv_col]).strip()
                if inv_col is not None and row[inv_col] is not None
                else None
            )
            if not inv:
                continue

            date_val = row[date_col] if date_col is not None else None
            order_date = _to_datetime(date_val)
            if order_date is None:
                continue

            status = (
                str(row[status_col]).strip()
                if status_col is not None and row[status_col] is not None
                else ""
            )
            if status.lower() != "completed":
                continue

            acct = (
                str(row[acct_col]).strip()
                if acct_col is not None and row[acct_col] is not None
                else ""
            )
            side = (
                str(row[side_col]).strip()
                if side_col is not None and row[side_col] is not None
                else ""
            )
            qty_raw = row[qty_col] if qty_col is not None else None
            qty = _to_float(qty_raw)
            cost_raw = row[cost_col] if cost_col is not None else None
            cost = _to_float(cost_raw)
            country = (
                str(row[country_col]).strip()
                if country_col is not None and row[country_col] is not None
                else None
            )

            is_drip = side.lower() == "buy" and cost is not None and cost < drip_threshold_gbp

            rows_out.append(
                ParsedOrderRow(
                    security_name=inv,
                    order_date=order_date,
                    order_status=status,
                    account_name=acct,
                    side=side,
                    quantity=qty,
                    cost_proceeds_gbp=cost,
                    country=country,
                    is_drip=is_drip,
                )
            )

    return rows_out

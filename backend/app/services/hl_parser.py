from __future__ import annotations

import csv
import datetime as dt
import io
import math
import re
from typing import TYPE_CHECKING, Any

from app.services.barclays_order_parser import DRIP_THRESHOLD_GBP, ParsedOrderRow
from app.services.barclays_parser import ParsedHoldingRow

if TYPE_CHECKING:
    from collections.abc import Iterator

HL_ACCOUNT_NAME = "HL Fund & Share Account"
_TRADE_REF_RE = re.compile(r"^[BS]\d+$", re.IGNORECASE)
_DESCRIPTION_TRADE_SUFFIX_RE = re.compile(r"\s+[\d,.]+\s+@\s+[\d,.]+\s*$")


class HLParseError(ValueError):
    """Fixed, privacy-safe rejection of an incomplete or ambiguous HL export."""


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _decode_csv(data: bytes) -> list[list[str]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252")
    try:
        return list(csv.reader(io.StringIO(text), strict=True))
    except csv.Error:
        raise HLParseError("HL export contains invalid CSV.") from None


def _table(rows: list[list[str]], first: str, required: set[str]) -> tuple[int, dict[str, int]]:
    candidates = [i for i, row in enumerate(rows) if row and _clean(row[0]).casefold() == first]
    if len(candidates) != 1:
        raise HLParseError("HL export requires exactly one recognised header.")
    index = candidates[0]
    header = [_clean(cell).casefold() for cell in rows[index]]
    nonempty = [cell for cell in header if cell]
    if len(set(nonempty)) != len(nonempty) or not required <= set(header):
        raise HLParseError("HL export has missing or duplicate columns.")
    return index, {name: i for i, name in enumerate(header) if name}


def _number(value: str) -> float:
    try:
        result = float(_clean(value).replace(",", ""))
    except ValueError:
        raise HLParseError("HL export contains an invalid numeric value.") from None
    if not math.isfinite(result):
        raise HLParseError("HL export contains a non-finite numeric value.")
    return result


def _metadata_value(rows: list[list[str]], label: str) -> str | None:
    values = [
        row for row in rows if row and _clean(row[0]).rstrip(":").casefold() == label.casefold()
    ]
    if len(values) > 1:
        raise HLParseError("HL export has duplicate metadata.")
    if values:
        if len(values[0]) < 2 or not _clean(values[0][1]):
            raise HLParseError("HL export has incomplete metadata.")
        return _clean(values[0][1])
    return None


def _holding_as_of(rows: list[list[str]]) -> dt.date:
    created_at = _metadata_value(rows, "Valuation as at") or _metadata_value(rows, "Spreadsheet created at")
    if created_at is None:
        return dt.date.today()
    try:
        return dt.datetime.strptime(created_at, "%d-%m-%Y %H:%M").date()
    except ValueError:
        raise HLParseError("HL export has an invalid observation date.") from None


def _account(rows: list[list[str]]) -> str:
    # Preserve the historical account label byte-for-byte: colon-labelled client
    # metadata was never used for event fingerprints. Validate it separately.
    client_rows = [row for row in rows if row and _clean(row[0]).casefold() == "client name"]
    client = _metadata_value(client_rows, "Client Name")
    return f"{HL_ACCOUNT_NAME} ({client})" if client else HL_ACCOUNT_NAME


def _data_rows(rows: list[list[str]], index: int, col: dict[str, int]) -> Iterator[list[str]]:
    for row in rows[index + 1 :]:
        if not any(_clean(cell) for cell in row):
            continue
        if len(row) <= max(col.values()):
            raise HLParseError("HL export contains a truncated row.")
        if any(_clean(cell) for cell in row[max(col.values()) + 1 :]):
            raise HLParseError("HL export contains unexpected row fields.")
        yield row


def parse_hl_holdings_csv_bytes(data: bytes) -> tuple[list[ParsedHoldingRow], dt.date]:
    rows = _decode_csv(data)
    index, col = _table(
        rows, "code", {"code", "stock", "units held", "price (pence)", "value (£)", "cost (£)"}
    )
    account = _account(rows[:index])
    parsed_rows = []
    seen = set()
    totals = None
    value_total = cost_total = 0.0
    for row in _data_rows(rows, index, col):
        code, stock = _clean(row[col["code"]]), _clean(row[col["stock"]])
        if totals is not None:
            raise HLParseError("HL export contains rows after its totals.")
        if not code and stock.casefold() == "totals":
            for name in ("units held", "price (pence)", "gain/loss (£)", "gain/loss (%)"):
                if name in col and _clean(row[col[name]]).casefold() not in {"", "n/a"}:
                    _number(row[col[name]])
            totals = (_number(row[col["value (£)"]]), _number(row[col["cost (£)"]]))
            continue
        if not code or not stock or code in seen:
            raise HLParseError("HL export contains missing or duplicate position identity.")
        seen.add(code)
        quantity = _number(row[col["units held"]])
        price = _number(row[col["price (pence)"]])
        value = _number(row[col["value (£)"]])
        cost = _number(row[col["cost (£)"]])
        value_total += value
        cost_total += cost
        if min(quantity, price, value, cost) < 0:
            raise HLParseError("HL export contains a negative holding amount.")
        if "gain/loss (£)" in col and _clean(row[col["gain/loss (£)"]]):
            _number(row[col["gain/loss (£)"]])
        change = row[col["gain/loss (%)"]] if "gain/loss (%)" in col else ""
        pct_change = _number(change) if _clean(change).casefold() not in {"", "n/a"} else None
        parsed_rows.append(
            ParsedHoldingRow(
                account_name=account,
                investment=stock,
                identifier=code,
                quantity=quantity,
                last_price=None,
                last_price_ccy="GBX",
                value=None,
                value_ccy="GBP",
                fx_rate=None,
                last_price_pence=price,
                value_gbp=value,
                book_cost=None,
                book_cost_ccy="GBP",
                average_fx_rate=None,
                book_cost_gbp=cost,
                pct_change=pct_change,
                is_cash=False,
            )
        )
    if totals is None:
        raise HLParseError("HL export is missing its totals footer.")
    for actual, expected in zip(
        (value_total, cost_total),
        totals,
        strict=True,
    ):
        if not math.isclose(actual, expected, rel_tol=0, abs_tol=0.011):
            raise HLParseError("HL export totals do not reconcile.")
    stock_value = _metadata_value(rows[:index], "Stock value")
    if stock_value is not None and not math.isclose(
        _number(stock_value), totals[0], rel_tol=0, abs_tol=0.011
    ):
        raise HLParseError("HL export stock value does not reconcile.")
    count = _metadata_value(rows[:index], "Number of holdings")
    if count is not None and (not count.isdigit() or int(count) != len(parsed_rows)):
        raise HLParseError("HL export position count does not reconcile.")
    return parsed_rows, _holding_as_of(rows[:index])


def validate_hl_pair_metadata(holdings: bytes, activity: bytes, *, as_of: dt.date) -> None:
    """Check raw client identity independently of legacy fingerprint labels."""
    holding_rows, activity_rows = _decode_csv(holdings), _decode_csv(activity)
    holding_index, _ = _table(holding_rows, "code", {"code"})
    activity_index, _ = _table(activity_rows, "trade date", {"trade date"})
    holding_meta, activity_meta = holding_rows[:holding_index], activity_rows[:activity_index]
    for label in ("Client Name", "Client Number"):
        identity = _metadata_value(holding_meta, label)
        if identity is None or identity != _metadata_value(activity_meta, label):
            raise HLParseError("HL pair client identity is missing or does not match.")
    if not (_metadata_value(holding_meta, 'Valuation as at')
            or _metadata_value(holding_meta, 'Spreadsheet created at')):
        raise HLParseError('HL pair requires explicit valuation date evidence.')
    holding_date = _holding_as_of(holding_meta)
    if holding_date > as_of:
        raise HLParseError('HL pair valuation date is in the future.')
    valued = _metadata_value(activity_meta, "Valuation as at")
    if valued is not None:
        try:
            date = dt.datetime.strptime(valued, "%d-%m-%Y %H:%M").date()
        except ValueError:
            raise HLParseError("HL activity observation date is invalid.") from None
        if date != holding_date:
            raise HLParseError("HL pair valuation dates do not match.")


def _security_name_from_description(description: str) -> str:
    return _DESCRIPTION_TRADE_SUFFIX_RE.sub("", _clean(description)).strip()


def parse_hl_activity_csv_bytes(
    data: bytes, *, drip_threshold_gbp: float = DRIP_THRESHOLD_GBP
) -> list[ParsedOrderRow]:
    rows = _decode_csv(data)
    index, col = _table(
        rows,
        "trade date",
        {"trade date", "reference", "description", "unit cost (p)", "quantity", "value (£)"},
    )
    account = _account(rows[:index])
    parsed_rows = []
    for row in _data_rows(rows, index, col):
        reference = _clean(row[col["reference"]])
        description = _clean(row[col["description"]])
        try:
            order_date = dt.datetime.strptime(_clean(row[col["trade date"]]), "%d/%m/%Y").replace(
                tzinfo=dt.UTC
            )
        except ValueError:
            raise HLParseError("HL activity contains an invalid date.") from None
        value = _number(row[col["value (£)"]])
        if not description:
            raise HLParseError("HL activity contains a missing description.")
        if not _TRADE_REF_RE.fullmatch(reference):
            # Cash-only events are excluded deliberately, not by silently dropping
            # every unknown reference. New provider event types require review.
            if (
                description.casefold().startswith(
                    (
                        "cash deposit",
                        "cash withdrawal",
                        "interest",
                        "dividend",
                        "loyalty bonus",
                        "fee",
                    )
                )
                and not _clean(row[col["quantity"]])
                and not _clean(row[col["unit cost (p)"]])
            ):
                continue
            raise HLParseError("HL activity contains an unrecognised event requiring review.")
        price = _number(row[col["unit cost (p)"]])
        quantity = _number(row[col["quantity"]])
        security = _security_name_from_description(description)
        if quantity <= 0 or price < 0 or not security:
            raise HLParseError("HL activity contains invalid trade values.")
        side = "Buy" if reference.upper().startswith("B") else "Sell"
        parsed_rows.append(
            ParsedOrderRow(
                security_name=security,
                order_date=order_date,
                order_status="Completed",
                account_name=account,
                side=side,
                quantity=quantity,
                cost_proceeds_gbp=abs(value),
                country="GB",
                is_drip=side == "Buy" and abs(value) < drip_threshold_gbp,
            )
        )
    count = _metadata_value(rows[:index], "Number of transactions")
    if count is not None and (
        not count.isdigit() or int(count) != sum(1 for _ in _data_rows(rows, index, col))
    ):
        raise HLParseError("HL activity count does not reconcile.")
    return parsed_rows

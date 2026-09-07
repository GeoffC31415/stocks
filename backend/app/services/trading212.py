from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import math
from collections.abc import Awaitable, Callable, Iterable, Mapping
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import parse_qs, urlsplit

import httpx

from app.services.barclays_order_parser import ParsedOrderRow
from app.services.barclays_parser import ParsedHoldingRow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models import ImportBatch, OrderImportBatch


class Trading212DataError(ValueError):
    """Raised when a read-only provider response cannot be imported safely."""


class Trading212CurrencyError(Trading212DataError):
    """Raised when Trading 212 wallet values are not denominated in GBP."""


class Trading212Client:
    """Minimal read-only client for the Trading 212 live equity API."""

    _BASE_URL = "https://live.trading212.com"
    _ORDERS_PATH = "/api/v0/equity/history/orders"
    _MAX_ORDER_PAGES = 1000

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
        page_delay: float = 10.1,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not api_key or not api_secret:
            raise ValueError("Trading 212 API credentials are not configured.")
        self._api_key = api_key
        self._api_secret = api_secret
        self._transport = transport
        self._timeout = timeout
        self._page_delay = page_delay
        self._sleep = sleep

    def _validate_orders_path(self, path: str, *, continuation: bool) -> None:
        parsed = urlsplit(path)
        if parsed.scheme or parsed.netloc or parsed.path != self._ORDERS_PATH or parsed.fragment:
            raise Trading212DataError("Trading 212 returned an invalid pagination path.")
        query = parse_qs(parsed.query, keep_blank_values=True)
        expected_keys = {"cursor", "limit"} if continuation else {"limit"}
        if set(query) != expected_keys or any(len(values) != 1 for values in query.values()):
            raise Trading212DataError("Trading 212 returned an invalid pagination path.")
        limit = query.get("limit", ["50"])[0]
        cursor = query.get("cursor", [None])[0]
        if not limit.isdigit() or limit != str(int(limit)):
            raise Trading212DataError("Trading 212 returned an invalid pagination path.")
        if not 1 <= int(limit) <= 50:
            raise Trading212DataError("Trading 212 returned an invalid pagination path.")
        if cursor is not None and (
            not cursor.isdigit()
            or cursor != str(int(cursor))
            or not 0 <= int(cursor) <= 1_000_000_000_000_000_000
        ):
            raise Trading212DataError("Trading 212 returned an invalid pagination path.")
        expected_query = f"cursor={cursor}&limit={limit}" if continuation else f"limit={limit}"
        if parsed.query != expected_query:
            raise Trading212DataError("Trading 212 returned an invalid pagination path.")

    async def _get(self, path: str) -> Any:
        async with httpx.AsyncClient(
            base_url=self._BASE_URL,
            auth=httpx.BasicAuth(self._api_key, self._api_secret),
            transport=self._transport,
            timeout=self._timeout,
            headers={"Accept": "application/json"},
        ) as client:
            response = await client.get(path)
            response.raise_for_status()
            return response.json()

    async def fetch_account_summary(self) -> Mapping[str, Any]:
        result = await self._get("/api/v0/equity/account/summary")
        if not isinstance(result, Mapping):
            raise Trading212DataError("Trading 212 returned an invalid account summary.")
        return result

    async def fetch_positions(self) -> list[Mapping[str, Any]]:
        result = await self._get("/api/v0/equity/positions")
        if not isinstance(result, list) or any(not isinstance(item, Mapping) for item in result):
            raise Trading212DataError("Trading 212 returned an invalid positions response.")
        return result

    async def fetch_historical_orders(self) -> list[Mapping[str, Any]]:
        path = f"{self._ORDERS_PATH}?limit=50"
        seen_paths: set[str] = set()
        items: list[Mapping[str, Any]] = []
        while path:
            if len(seen_paths) >= self._MAX_ORDER_PAGES:
                raise Trading212DataError("Trading 212 order pagination exceeded the safety limit.")
            self._validate_orders_path(path, continuation=bool(seen_paths))
            if path in seen_paths:
                raise Trading212DataError("Trading 212 returned an invalid pagination path.")
            seen_paths.add(path)
            result = await self._get(path)
            if not isinstance(result, Mapping) or not isinstance(result.get("items"), list):
                raise Trading212DataError("Trading 212 returned an invalid order-history response.")
            page_items = result["items"]
            if any(not isinstance(item, Mapping) for item in page_items):
                raise Trading212DataError("Trading 212 returned an invalid order-history response.")
            items.extend(page_items)
            next_path = result.get("nextPagePath")
            if next_path in (None, ""):
                break
            if not isinstance(next_path, str):
                raise Trading212DataError("Trading 212 returned an invalid pagination path.")
            self._validate_orders_path(next_path, continuation=True)
            if next_path in seen_paths:
                raise Trading212DataError("Trading 212 returned an invalid pagination path.")
            await self._sleep(self._page_delay)
            path = next_path
        return items


class Trading212Reader(Protocol):
    async def fetch_account_summary(self) -> Mapping[str, Any]: ...

    async def fetch_positions(self) -> list[Mapping[str, Any]]: ...

    async def fetch_historical_orders(self) -> list[Mapping[str, Any]]: ...


async def sync_portfolio_snapshot(
    session: AsyncSession,
    client: Trading212Reader,
    *,
    account_name: str,
    force: bool = False,
) -> tuple[ImportBatch, dict[str, Any]]:
    from app.services.import_service import import_holding_snapshot

    positions = await client.fetch_positions()
    account_summary_available = True
    try:
        account = await client.fetch_account_summary()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 403:
            raise
        wallet_currencies = {
            str((position.get("walletImpact") or {}).get("currency") or "").upper()
            for position in positions
        }
        wallet_currencies.discard("")
        if len(wallet_currencies) != 1:
            raise Trading212CurrencyError(
                "Cannot verify the Trading 212 account currency without account access."
            ) from exc
        account = {"currency": wallet_currencies.pop()}
        account_summary_available = False
    rows = positions_to_rows(
        positions,
        account,
        account_name=account_name,
        require_cash=account_summary_available,
    )

    positions = sorted(positions, key=lambda item: json.dumps(item, sort_keys=True))
    source_payload = json.dumps(
        {"account_name": account_name, "account": account, "positions": positions},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    return await import_holding_snapshot(
        session,
        parsed_rows=rows,
        as_of_date=dt.datetime.now(dt.UTC).date(),
        filename="trading212-api-portfolio.json",
        file_sha256=hashlib.sha256(source_payload).hexdigest(),
        force=force,
        preserve_missing_identifiers={"CASH"} if not account_summary_available else None,
    )


async def sync_order_history(
    session: AsyncSession,
    client: Trading212Reader,
    *,
    account_name: str,
    force: bool = False,
) -> tuple[OrderImportBatch, int]:
    from app.services.order_service import ingest_parsed_orders

    items = await client.fetch_historical_orders()
    rows = historical_orders_to_rows(items, account_name=account_name)
    items = sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
    source_payload = json.dumps(
        {"account_name": account_name, "items": items},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return await ingest_parsed_orders(
        session,
        parsed=rows,
        file_bytes=source_payload,
        filename="trading212-api-orders.json",
        force=force,
    )


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _require_gbp(currency: Any) -> None:
    if str(currency or "").upper() != "GBP":
        raise Trading212CurrencyError(
            "Trading 212 imports require a GBP primary account and GBP wallet values."
        )


def positions_to_rows(
    positions: Iterable[Mapping[str, Any]],
    account: Mapping[str, Any],
    *,
    account_name: str,
    require_cash: bool = False,
) -> list[ParsedHoldingRow]:
    _require_gbp(account.get("currency"))
    rows: list[ParsedHoldingRow] = []

    for position in positions:
        instrument = position.get("instrument") or {}
        wallet = position.get("walletImpact") or {}
        _require_gbp(wallet.get("currency"))
        value_gbp = _number(wallet.get("currentValue"))
        book_cost_gbp = _number(wallet.get("totalCost"))
        unrealized = _number(wallet.get("unrealizedProfitLoss"))
        pct_change = None
        if book_cost_gbp is not None and book_cost_gbp != 0 and unrealized is not None:
            pct_change = unrealized / book_cost_gbp * 100.0

        identifier = str(instrument.get("isin") or instrument.get("ticker") or "").strip()
        investment = str(instrument.get("name") or instrument.get("ticker") or "").strip()
        if not identifier or not investment:
            raise Trading212DataError(
                "Trading 212 returned an invalid position without an identifier or name."
            )
        if value_gbp is None or book_cost_gbp is None or _number(position.get("quantity")) is None:
            raise Trading212DataError(
                "Trading 212 returned an invalid position with missing numeric values."
            )
        instrument_currency = str(instrument.get("currency") or "").upper() or None
        rows.append(
            ParsedHoldingRow(
                account_name=account_name,
                investment=investment,
                identifier=identifier,
                quantity=_number(position.get("quantity")),
                last_price=_number(position.get("currentPrice")),
                last_price_ccy=instrument_currency,
                value=value_gbp,
                value_ccy="GBP",
                fx_rate=None,
                last_price_pence=None,
                value_gbp=value_gbp,
                book_cost=book_cost_gbp,
                book_cost_ccy="GBP",
                average_fx_rate=None,
                book_cost_gbp=book_cost_gbp,
                pct_change=pct_change,
                is_cash=False,
            )
        )

    cash = account.get("cash")
    if require_cash and not isinstance(cash, Mapping):
        raise Trading212DataError("Trading 212 returned invalid cash values.")
    if isinstance(cash, Mapping):
        cash_parts = [
            _number(cash.get(field))
            for field in ("availableToTrade", "inPies", "reservedForOrders")
        ]
        if any(value is None for value in cash_parts):
            raise Trading212DataError("Trading 212 returned invalid cash values.")
        cash_value = sum(value for value in cash_parts if value is not None)
        rows.append(
            ParsedHoldingRow(
                account_name=account_name,
                investment="Cash",
                identifier="CASH",
                quantity=None,
                last_price=None,
                last_price_ccy="GBP",
                value=cash_value,
                value_ccy="GBP",
                fx_rate=1.0,
                last_price_pence=None,
                value_gbp=cash_value,
                book_cost=cash_value,
                book_cost_ccy="GBP",
                average_fx_rate=1.0,
                book_cost_gbp=cash_value,
                pct_change=0.0,
                is_cash=True,
            )
        )
    return rows


def _parse_datetime(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def historical_orders_to_rows(
    items: Iterable[Mapping[str, Any]],
    *,
    account_name: str,
) -> list[ParsedOrderRow]:
    rows: list[ParsedOrderRow] = []
    for item in items:
        fill = item.get("fill") or {}
        order = item.get("order") or {}
        if fill.get("type") != "TRADE":
            continue
        wallet = fill.get("walletImpact") or {}
        _require_gbp(wallet.get("currency"))
        order_date = _parse_datetime(fill.get("filledAt"))
        instrument = order.get("instrument") or {}
        security_name = str(instrument.get("name") or order.get("ticker") or "").strip()
        side_raw = str(order.get("side") or "").upper()
        quantity = _number(fill.get("quantity"))
        net_value = _number(wallet.get("netValue"))
        fill_id = fill.get("id")
        fill_id_valid = (
            isinstance(fill_id, int) and not isinstance(fill_id, bool) and fill_id >= 0
        ) or (isinstance(fill_id, str) and bool(fill_id.strip()))
        if (
            order_date is None
            or not security_name
            or side_raw not in {"BUY", "SELL"}
            or quantity is None
            or quantity <= 0
            or net_value is None
            or not fill_id_valid
        ):
            raise Trading212DataError("Trading 212 returned an invalid order fill.")
        rows.append(
            ParsedOrderRow(
                security_name=security_name,
                order_date=order_date,
                order_status="Completed",
                account_name=account_name,
                side=side_raw.title(),
                quantity=abs(quantity),
                cost_proceeds_gbp=abs(net_value),
                country=None,
                is_drip=False,
                source_event_id=str(fill_id).strip(),
            )
        )
    return rows

"""Durable market-data foundation.

Provider contract
-----------------
A provider yields :class:`MarketPricePointOut` rows: symbol, date, close,
optional adjusted close, currency, source, and fetched timestamp. The cache
table ``market_price_points`` stores these rows keyed by
(source, symbol, date). FX pairs (``GBPUSD=X`` style, stored as ``GBPUSD``)
go into ``market_fx_points`` through the same refresh path but a separate
table, and are used to convert non-GBP series to GBP at read time.

Provider selection (probe 2026-09-02, recorded in docs/market-data.md)
----------------------------------------------------------------------
- Stooq: bot-walled for this symbol set (403/empty bodies) — rejected.
- Yahoo Finance chart API: machine-readable OHLC for LSE (``BA.L``),
  London USD listings (``EQQQ.L``), US equities (``GOOGL``), the SPX
  benchmark (``^GSPC``), the VWRL benchmark (``VWRL.L``), and GBP/USD FX
  (``GBPUSD=X``) with 2y daily history. Requires a cookie jar (prime with
  ``fc.yahoo.com``) plus a browser User-Agent; hard rate limits apply, so
  every refresh is cache-first, single-flight per symbol, with bounded
  concurrency, per-symbol timeout, and retry/backoff. A failed refresh
  keeps the cached rows.

Analytics code never maps provider symbols: it asks the service for a
symbol it already knows, and the provider owns any symbol normalisation.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import select

from app.models import Instrument, InstrumentQuote, MarketFxPoint, MarketPricePoint

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any

    from sqlalchemy.ext.asyncio import AsyncSession

#: Source label stored with every cached point.
SOURCE = "yahoo"

#: Pairs the coverage gate needs (base currency quoted in the second).
DEFAULT_FX_PAIRS: tuple[str, ...] = ("GBPUSD",)

_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
_BASE_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"


# ---------------------------------------------------------------------------
# Provider contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MarketPricePointOut:
    """One daily observation in the provider's source currency."""

    symbol: str
    date: dt.date
    close: float
    adjusted_close: float | None
    currency: str
    source: str = SOURCE
    fetched_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))


class MarketDataProvider(Protocol):
    """Minimal provider contract: fetch a symbol's daily history.

    Implementations must be safe to call from a worker thread and must
    raise (not return empty lists) on failure so callers can distinguish
    "no data" from "transient failure".
    """

    async def fetch_daily(
        self,
        symbol: str,
        *,
        start: dt.date | None = None,
        timeout: float = 20.0,
    ) -> list[MarketPricePointOut]: ...


def _http_get(url: str, *, timeout: float = 20.0, opener: Any = None) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    open_request = opener.open if opener is not None else urllib.request.urlopen
    with open_request(request, timeout=timeout) as response:
        return response.read()


class YahooMarketDataProvider:
    """Yahoo Finance chart API with cookie-jar priming and backoff.

    The cookie jar is module-level state (one session per process) because
    Yahoo's rate limiter keys on the IP and the primed session cookies
    together; rebuilding it per call would reset the limiter's window.
    """

    name = "yahoo"
    _opener: Any = None
    _last_request_at = 0.0
    _min_spacing_s = 4.0
    _backoff_s = 60.0

    @classmethod
    def _get_opener(cls) -> Any:
        if cls._opener is None:
            import http.cookiejar

            jar = http.cookiejar.CookieJar()
            cls._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
            with contextlib.suppress(Exception):  # priming is best-effort
                cls._get("https://fc.yahoo.com", opener=cls._opener, timeout=15.0)
        return cls._opener

    @classmethod
    def _throttle(cls) -> None:
        wait = cls._min_spacing_s - (time.monotonic() - cls._last_request_at)
        if wait > 0:
            time.sleep(wait)
        cls._last_request_at = time.monotonic()

    @classmethod
    def _get(cls, url: str, *, timeout: float, opener: Any) -> bytes:
        cls._throttle()
        return _http_get(url, timeout=timeout, opener=opener)

    @staticmethod
    def _parse_chart(symbol: str, payload: dict[str, Any]) -> list[MarketPricePointOut]:
        chart = payload.get("chart") or {}
        if chart.get("error"):
            error = chart["error"]
            raise LookupError(f"{symbol}: provider error {error.get('description', error)}")
        results = chart.get("result") or []
        if not results:
            raise LookupError(f"{symbol}: provider returned no result")
        result = results[0]
        meta = result.get("meta") or {}
        currency = str(meta.get("currency") or "UNKNOWN")
        timestamps: list[int] = result.get("timestamp") or []
        indicators = result.get("indicators") or {}
        quote = (indicators.get("quote") or [{}])[0]
        closes: list[float | None] = quote.get("close") or []
        adj = (indicators.get("adjclose") or [{}])[0].get("adjclose")
        points: list[MarketPricePointOut] = []
        for index, timestamp in enumerate(timestamps):
            close = closes[index] if index < len(closes) else None
            if close is None:
                continue
            adjusted = adj[index] if adj is not None and index < len(adj) else None
            date = dt.datetime.fromtimestamp(timestamp, dt.UTC).date()
            points.append(
                MarketPricePointOut(
                    symbol=symbol,
                    date=date,
                    close=float(close),
                    adjusted_close=None if adjusted is None else float(adjusted),
                    currency=currency,
                )
            )
        if not points:
            raise LookupError(f"{symbol}: provider returned no usable rows")
        return points

    def fetch_daily_blocking(
        self,
        symbol: str,
        *,
        start: dt.date | None = None,
        timeout: float = 20.0,
        attempts: int = 3,
    ) -> list[MarketPricePointOut]:
        """Thread-safe blocking fetch with retry/backoff (run via to_thread)."""
        url = _BASE_URL.format(symbol=urllib.parse.quote(symbol))
        url = f"{url}?range=max&interval=1d&events=div%7Csplit"
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                opener = self._get_opener()
                raw = self._get(url, timeout=timeout, opener=opener)
                points = self._parse_chart(symbol, json.loads(raw))
                if start is not None:
                    points = [point for point in points if point.date >= start]
                return points
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code != 429:
                    break
                # Rate-limited: back off longer, refresh cookies for the next attempt.
                time.sleep(self._backoff_s if attempt == attempts - 1 else 15.0)
                type(self)._opener = None
            except Exception as exc:  # noqa: BLE001 - surface any failure to the caller
                last_error = exc
                break
        raise RuntimeError(f"{symbol}: fetch failed after {attempts} attempts: {last_error}")

    async def fetch_daily(
        self,
        symbol: str,
        *,
        start: dt.date | None = None,
        timeout: float = 20.0,
    ) -> list[MarketPricePointOut]:
        return await asyncio.to_thread(self.fetch_daily_blocking, symbol, start=start, timeout=timeout)


def make_provider() -> MarketDataProvider:
    """Default provider factory; keep provider-specific choices out of analytics."""
    return YahooMarketDataProvider()


# ---------------------------------------------------------------------------
# Cache persistence
# ---------------------------------------------------------------------------


async def store_points(
    session: AsyncSession,
    points: Sequence[MarketPricePointOut],
) -> int:
    """Upsert price points into the cache; returns rows written.

    Existing rows are never deleted, only overwritten when the fetched
    series covers the same date, so a failed or partial refresh keeps the
    cached rows usable (partial-failure safety).
    """
    if not points:
        return 0
    by_key: dict[tuple[str, str, dt.date], MarketPricePointOut] = {
        (point.source, point.symbol, point.date): point for point in points
    }
    written = 0
    for (source, symbol, date), point in by_key.items():
        result = await session.execute(
            select(MarketPricePoint)
            .where(
                MarketPricePoint.source == source,
                MarketPricePoint.symbol == symbol,
                MarketPricePoint.date == date,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            existing = MarketPricePoint(
                source=source,
                symbol=symbol,
                date=date,
                close=point.close,
                adjusted_close=point.adjusted_close,
                currency=point.currency,
                fetched_at=point.fetched_at,
            )
            session.add(existing)
        else:
            existing.close = point.close
            existing.adjusted_close = point.adjusted_close
            existing.currency = point.currency
            existing.fetched_at = point.fetched_at
        written += 1
    await session.flush()
    return written


async def load_points(
    session: AsyncSession,
    symbol: str,
    *,
    start: dt.date | None = None,
    source: str | None = SOURCE,
) -> list[MarketPricePoint]:
    query = select(MarketPricePoint).where(MarketPricePoint.symbol == symbol)
    if source is not None:
        query = query.where(MarketPricePoint.source == source)
    if start is not None:
        query = query.where(MarketPricePoint.date >= start)
    query = query.order_by(MarketPricePoint.date)
    return list((await session.execute(query)).scalars().all())


# ---------------------------------------------------------------------------
# FX cache
# ---------------------------------------------------------------------------

_CURRENCY_TO_PAIR: dict[str, str] = {"USD": "GBPUSD", "EUR": "GBPEUR"}


def fx_pair_for_currency(currency: str) -> str | None:
    """Pair needed to convert ``currency`` into GBP, or None when unknown."""
    if currency.upper() == "GBP":
        return None
    return _CURRENCY_TO_PAIR.get(currency.upper())


async def store_fx_points(
    session: AsyncSession,
    points: Sequence[MarketPricePointOut],
) -> int:
    """Upsert FX quote series into the FX cache (pair = symbol minus ``=X``)."""
    written = 0
    for point in points:
        pair = point.symbol.split("=", 1)[0].upper()
        result = await session.execute(
            select(MarketFxPoint)
            .where(
                MarketFxPoint.source == point.source,
                MarketFxPoint.pair == pair,
                MarketFxPoint.date == point.date,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            existing = MarketFxPoint(
                source=point.source,
                pair=pair,
                date=point.date,
                rate=point.close,
                fetched_at=point.fetched_at,
            )
            session.add(existing)
        else:
            existing.rate = point.close
            existing.fetched_at = point.fetched_at
        written += 1
    await session.flush()
    return written


async def latest_fx_rate(
    session: AsyncSession,
    pair: str,
    *,
    as_of: dt.date | None = None,
    source: str | None = SOURCE,
) -> float | None:
    """Most recent cached rate on or before ``as_of`` (latest if omitted)."""
    query = select(MarketFxPoint).where(MarketFxPoint.pair == pair.upper())
    if source is not None:
        query = query.where(MarketFxPoint.source == source)
    if as_of is not None:
        query = query.where(MarketFxPoint.date <= as_of)
    query = query.order_by(MarketFxPoint.date.desc()).limit(1)
    row = (await session.execute(query)).scalar_one_or_none()
    return None if row is None else row.rate


# ---------------------------------------------------------------------------
# Refresh orchestration (bounded concurrency, per-symbol timeout, backoff)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class RefreshResult:
    ok: list[str]
    failed: dict[str, str]
    points_stored: int = 0

    @property
    def partial(self) -> bool:
        return bool(self.failed)


async def refresh_market_data(
    session: AsyncSession,
    symbols: Sequence[str],
    *,
    provider: MarketDataProvider | None = None,
    fx_pairs: Sequence[str] = DEFAULT_FX_PAIRS,
    start: dt.date | None = None,
    concurrency: int = 2,
    timeout: float = 20.0,
    per_symbol_delay_s: float = 5.0,
) -> RefreshResult:
    """Refresh price + FX caches.

    Bounded concurrency via a semaphore; symbols are refreshed strictly
    sequentially per provider session with a polite delay (rate limits are
    IP-wide). A symbol that fails is reported in ``failed`` and its cached
    rows are kept — a refresh never deletes usable data.
    """
    active_provider = provider or make_provider()
    semaphore = asyncio.Semaphore(max(1, concurrency))
    failed: dict[str, str] = {}
    points_stored_total = [0]
    all_symbols = list(dict.fromkeys(symbols))
    fx_symbols = [f"{pair}=X" for pair in dict.fromkeys(fx_pairs)]

    async def _refresh(symbol: str, is_fx: bool) -> None:
        async with semaphore:
            if isinstance(active_provider, YahooMarketDataProvider):
                # Yahoo rate limits are IP-wide: a single polite sequential
                # stream beats a parallel fan-out, so the semaphore mostly
                # bounds the FX/price overlap rather than raw parallelism.
                fetcher = lambda sym: asyncio.to_thread(  # noqa: E731
                    active_provider.fetch_daily_blocking,
                    sym,
                    start=start,
                    timeout=timeout,
                )
            else:
                fetcher = lambda sym: active_provider.fetch_daily(sym, start=start, timeout=timeout)  # noqa: E731
            try:
                points = await fetcher(symbol)
            except Exception as exc:  # noqa: BLE001 - report and keep cached rows
                failed[symbol] = str(exc)[:200]
                return
            stored = await store_fx_points(session, points) if is_fx else await store_points(session, points)
            points_stored_total[0] += stored
            await session.commit()
            await asyncio.sleep(per_symbol_delay_s)

    for symbol in all_symbols:
        await _refresh(symbol, is_fx=False)
    for fx_symbol in fx_symbols:
        await _refresh(fx_symbol, is_fx=True)

    return RefreshResult(
        ok=[s for s in all_symbols if s not in failed],
        failed=failed,
        points_stored=points_stored_total[0],
    )


# ---------------------------------------------------------------------------
# Read-side helpers (cache-first; GBP conversion only with valid FX)
# ---------------------------------------------------------------------------


async def cached_history(
    session: AsyncSession,
    symbol: str,
    *,
    start: dt.date | None = None,
    base_value: float = 100.0,
) -> list[dict[str, Any]]:
    """Rebased value series from the cache. Empty list when nothing is cached."""
    points = await load_points(session, symbol, start=start)
    if len(points) < 2:
        return []
    first = points[0]
    base = first.adjusted_close if first.adjusted_close is not None else first.close
    if base <= 0:
        return []
    rows: list[dict[str, Any]] = []
    for point in points:
        close = point.adjusted_close if point.adjusted_close is not None else point.close
        rows.append(
            {
                "date": point.date,
                "symbol": symbol,
                "close": close,
                "rebased_value": (close / base) * base_value,
                "currency": point.currency,
            }
        )
    return rows


async def fetch_history(
    session: AsyncSession | None,
    symbol: str,
    *,
    start: dt.date | None = None,
    base_value: float = 100.0,
    provider: MarketDataProvider | None = None,
) -> list[dict[str, Any]]:
    """Cache-only analytics read. Refresh is an explicit POST operation.

    ``provider`` is retained for caller compatibility but never used here.
    Missing cache/session returns no history, never a provider call or write.
    """
    if session is None:
        return []
    return await cached_history(session, symbol, start=start, base_value=base_value)


async def fetch_latest_quote(symbol: str) -> dict[str, Any] | None:
    """Latest close in the provider's source currency (NOT assumed to be GBP)."""
    provider = make_provider()
    try:
        points = await provider.fetch_daily(symbol)
    except Exception:  # noqa: BLE001 - quote failures are non-fatal
        return None
    if not points:
        return None
    last = points[-1]
    return {
        "ticker": symbol.strip(),
        "price": last.close,
        "price_ccy": last.currency,
        "as_of_date": last.date,
        "fetched_at": last.fetched_at,
    }


async def refresh_instrument_quote(
    session: AsyncSession,
    instrument: Instrument,
) -> InstrumentQuote | None:
    """Refresh an instrument's quote, keeping source currency explicit."""
    if not instrument.ticker:
        return None
    payload = await fetch_latest_quote(instrument.ticker)
    if payload is None:
        return None

    existing = (
        await session.execute(
            select(InstrumentQuote).where(InstrumentQuote.instrument_id == instrument.id)
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = InstrumentQuote(instrument_id=instrument.id, ticker=instrument.ticker)
        session.add(existing)

    existing.ticker = payload["ticker"]
    existing.price_ccy = payload["price_ccy"]
    existing.price_gbp = payload["price"] if payload["price_ccy"] == "GBP" else None
    existing.as_of_date = payload["as_of_date"]
    existing.fetched_at = payload["fetched_at"]
    await session.commit()
    await session.refresh(existing)
    return existing


def infer_asset_class(instrument: Instrument) -> str | None:
    text = f"{instrument.security_name} {instrument.identifier}".lower()
    if instrument.is_cash:
        return "Cash"
    if "etf" in text or "ucits" in text or "index" in text:
        return "ETF"
    if "bond" in text or "gilt" in text:
        return "Bond"
    return "Equity"

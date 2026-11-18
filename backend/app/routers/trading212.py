from __future__ import annotations

import datetime as dt  # noqa: TC003 - Pydantic runtime annotation.
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002 - FastAPI runtime annotation.

from app.config import settings
from app.database import get_session
from app.schemas import ImportBatchOut, ImportResult, OrderImportBatchOut
from app.services.import_service import DuplicateImportError
from app.services.order_service import DuplicateOrderImportError
from app.services.trading212 import (
    Trading212CashReader,
    Trading212Client,
    Trading212DataError,
    Trading212Reader,
    sync_cash_history,
    sync_order_history,
    sync_portfolio_snapshot,
)
from app.services.trading212_valuation import ValuationObservation, ledger_scope

if TYPE_CHECKING:
    from collections.abc import Mapping


router = APIRouter(prefix="/api/trading212", tags=["trading212"])
logger = logging.getLogger(__name__)
_TRUSTED_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
}


class CashFlowSyncResult(BaseModel):
    account_name: str
    imported_count: int
    total_count: int
    fetched_at: dt.datetime


class Trading212SyncResult(BaseModel):
    account_name: str
    snapshot: str
    snapshot_rows: int | None = None
    orders: str
    order_rows: int | None = None
    cash_flows_imported: int
    cash_flows_total: int
    valuation_at: dt.date | None = None
    fetched_at: dt.datetime


class Trading212Status(BaseModel):
    configured: bool
    account_name: str


@dataclass
class _FetchedTrading212Data:
    """Replay fetched responses to import services without any network access."""

    # Only fully fetched sections are present. Looking up an unavailable
    # section fails closed; it must never be replayed as an empty response.
    responses: dict[str, Any] = field(default_factory=dict)
    observed_at: dict[str, dt.datetime] = field(default_factory=dict)
    valuation: ValuationObservation | None = None

    async def fetch_positions(self) -> list[Mapping[str, Any]]:
        return self.responses["positions"]

    async def fetch_account_summary(self) -> Mapping[str, Any]:
        account = self.responses["account_summary"]
        if isinstance(account, httpx.HTTPStatusError):
            raise account  # Preserve the direct route's denied-summary diagnostic.
        return account

    async def fetch_historical_orders(self) -> list[Mapping[str, Any]]:
        return self.responses["orders"]

    async def fetch_transactions(self) -> list[Mapping[str, Any]]:
        return self.responses["transactions"]


def require_local_origin(request: Request) -> None:
    """Preserve local development protection; public mode uses its exact origin."""
    application = request.scope.get("app")
    config = getattr(getattr(application, "state", None), "web_config", settings)
    origins = request.headers.getlist("origin")
    if config.deployment_mode == "public":
        if origins != [config.public_origin]:
            raise HTTPException(status_code=403, detail="Untrusted request origin.")
        return
    if not origins:
        return
    if len(origins) != 1 or origins[0] not in _TRUSTED_ORIGINS:
        raise HTTPException(status_code=403, detail="Untrusted request origin.")


def require_local_broker(request: Request) -> None:
    """Reject public broker execution before resolving database or credentials."""
    config = getattr(getattr(request.scope.get("app"), "state", None), "web_config", settings)
    if config.deployment_mode == "public":
        raise HTTPException(status_code=403, detail="Broker sync runs in the isolated service.")


def get_trading212_client() -> Trading212Client:
    key = settings.trading212_api_key
    secret = settings.trading212_api_secret
    if key is None or secret is None:
        raise HTTPException(status_code=503, detail="Trading 212 credentials are not configured.")
    api_key = key.get_secret_value().strip()
    api_secret = secret.get_secret_value().strip()
    if not api_key or not api_secret:
        raise HTTPException(status_code=503, detail="Trading 212 credentials are not configured.")
    return Trading212Client(api_key=api_key, api_secret=api_secret)


def _provider_error(exc: Exception, *, operation: str | None = None) -> HTTPException:
    # Fixed, revalidated tokens only. Never format exception text, causes,
    # request URLs, provider bodies or tracebacks into agent-readable logs.
    from app.services.trading212 import trading212_diagnostic, trading212_failure_description

    code, endpoint, phase, http_status = trading212_diagnostic(exc)
    if operation in {"positions", "orders", "transactions"} and endpoint == "sync":
        endpoint = operation
        phase = "fetch" if isinstance(exc, httpx.HTTPError) else "import"
    # Migration fileConfig may disable pre-existing application loggers.
    # Restore only this safe diagnostic sink, never HTTP/provider loggers.
    logger.disabled = False
    reason, stage, resource = trading212_failure_description(code, endpoint, phase, http_status)
    logger.error(
        "Trading 212 sync failed code=%s endpoint=%s phase=%s http_status=%s "
        'reason="%s" stage="%s" resource="%s"',
        code,
        endpoint,
        phase,
        http_status if http_status is not None else "unavailable",
        reason,
        stage,
        resource,
    )
    if code == "account_summary_forbidden":
        return HTTPException(
            status_code=400,
            detail="Trading 212 requires the read-only account permission to verify cash. "
            "No portfolio changes were imported.",
        )
    if isinstance(exc, httpx.HTTPStatusError):
        return HTTPException(
            status_code=502,
            detail=f"Trading 212 returned HTTP {http_status or 'error'}.",
        )
    if isinstance(exc, httpx.HTTPError):
        return HTTPException(status_code=502, detail="Trading 212 could not be reached.")
    if isinstance(exc, Trading212DataError):
        return HTTPException(status_code=400, detail=f"Trading 212 validation failed ({code}).")
    return HTTPException(status_code=500, detail="Trading 212 sync failed.")


@router.post("/sync/cash-flows", response_model=CashFlowSyncResult)
async def sync_trading212_cash_flows(
    _broker_guard: None = Depends(require_local_broker),
    _origin_guard: None = Depends(require_local_origin),
    session: AsyncSession = Depends(get_session),
    client: Trading212CashReader = Depends(get_trading212_client),
) -> CashFlowSyncResult:
    try:
        result = await sync_cash_history(
            session, client, account_name=settings.trading212_account_name
        )
    except Exception as exc:
        await session.rollback()
        error = _provider_error(exc, operation="transactions")
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 403:
            raise HTTPException(
                status_code=502,
                detail="Trading 212 cash history requires the read-only history:transactions permission.",
            ) from exc
        raise error from exc
    return CashFlowSyncResult.model_validate(result)


@router.post("/sync", response_model=Trading212SyncResult)
async def sync_trading212_all(
    force: bool = Query(default=False),
    _broker_guard: None = Depends(require_local_broker),
    _origin_guard: None = Depends(require_local_origin),
    session: AsyncSession = Depends(get_session),
    client: Trading212Client = Depends(get_trading212_client),
) -> Trading212SyncResult:
    """Refresh the complete read-only Trading 212 dataset in one action."""
    try:
        return await run_trading212_sync(session, client, force=force)
    except Exception as exc:
        raise _provider_error(exc) from exc


def _annotate(exc: BaseException, endpoint: str, phase: str) -> None:
    if isinstance(exc, Exception):
        # Never let diagnostic enrichment replace the error. Bypass arbitrary setters.
        with suppress(Exception):
            vars(exc).update(t212_endpoint=endpoint, t212_phase=phase)


@dataclass(frozen=True)
class Trading212Incomplete:
    """Worker-only evidence. Map errors at the diagnostic sink; never serialize them."""

    sections: dict[str, dict[str, Any]]
    errors: list[Exception] = field(repr=False)


async def _stage_snapshot(
    session: AsyncSession,
    fetched: _FetchedTrading212Data,
    *,
    force: bool,
) -> tuple[str, int | None, dt.date | None]:
    try:
        batch, summary = await sync_portfolio_snapshot(
            session,
            fetched,
            account_name=settings.trading212_account_name,
            force=force,
            commit=False,
            observation_date=fetched.valuation.account_summary_received_at.date()
            if fetched.valuation
            else None,
        )
        if fetched.valuation is not None:
            # Only a new batch gets evidence. Never restamp a retained duplicate.
            batch.diff_summary = {**summary, ValuationObservation.key: fetched.valuation.metadata()}
        rows = summary.get("row_count") if isinstance(summary, dict) else None
        return "imported", rows, batch.as_of_date
    except DuplicateImportError as exc:
        from app.models import ImportBatch

        retained = await session.get(ImportBatch, exc.batch_id)
        return "unchanged", None, retained.as_of_date if retained else None


async def _stage_orders(
    session: AsyncSession,
    fetched: _FetchedTrading212Data,
    *,
    force: bool,
    require_retained: bool,
    manual_matching_only: bool,
) -> tuple[str, int | None]:
    try:
        batch, _ = await sync_order_history(
            session,
            fetched,
            account_name=settings.trading212_account_name,
            force=force,
            commit=False,
            require_retained=require_retained,
            manual_matching_only=manual_matching_only,
        )
        return "imported", batch.row_count
    except DuplicateOrderImportError:
        return "unchanged", None


async def run_trading212_sync(
    session: AsyncSession, client: Trading212Client, *, force: bool = False
) -> Trading212SyncResult:
    """Direct API: require one atomic account refresh; never accept partial history."""
    result = await _run_sync(session, client, force=force, allow_history_only=False)
    assert isinstance(result, Trading212SyncResult)
    return result


async def run_trading212_worker_sync(
    session: AsyncSession, client: Trading212Client
) -> Trading212SyncResult | Trading212Incomplete:
    """Retain the last complete valuation if a required section fails validation."""
    return await _run_sync(session, client, force=False, allow_history_only=True)


# Only classified source rejections may discard a section and replay its peers.
# DB errors, unclassified failures and anything at setup/flush/commit are fatal.
_SECTION_REJECTIONS = {
    "positions": {
        "invalid_position_identity",
        "invalid_position_numbers",
        "invalid_cash_values",
        "non_gbp_currency",
        "account_summary_forbidden",
    },
    "orders": {
        "invalid_order_fill_date",
        "invalid_order_fill_type",
        "invalid_order_fill_name",
        "invalid_order_fill_side",
        "invalid_order_fill_quantity",
        "invalid_order_fill_value",
        "invalid_order_fill_id",
        "invalid_order_fill_identity",
        "order_fill_identity_conflict",
        "order_history_conflict",
        "non_gbp_currency",
    },
    "transactions": {
        "future_cash_transaction",
        "cash_history_conflict",
        "cash_history_source_conflict",
        "invalid_cash_transaction",
        "unsupported_cash_transaction_type",
        "invalid_cash_transaction_date",
        "invalid_cash_transaction_reference",
        "invalid_cash_transfer_amount",
        "invalid_cash_transaction_amount",
        "invalid_cash_transaction_currency",
        "cash_reference_conflict",
    },
}


def _incomplete(
    errors: dict[str, Exception],
    statuses: dict[str, str],
    observed_at: dict[str, dt.datetime],
) -> Trading212Incomplete:
    from app.services.sync_freshness import REQUIRED_SECTIONS, verified_sections

    sections = {}
    for section in REQUIRED_SECTIONS["Trading 212"]:
        sections.update(
            verified_sections(
                {section: statuses.get(section, "needs_attention")},
                observed_at[section].isoformat() if section in statuses else "",
                None,
                coverage={section: "complete"},
            )
        )
    return Trading212Incomplete(sections=sections, errors=list(errors.values()))


_FETCH_REJECTIONS = {
    "invalid_json_response",
    "request_failed",
    "invalid_positions_response",
    "invalid_account_summary",
    "invalid_order_history_response",
    "invalid_order_pagination",
    "order_pagination_limit",
    "invalid_cash_history_response",
    "invalid_cash_pagination",
    "cash_pagination_limit",
    "cash_pagination_repeated",
}


def _section_fetch_failure(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        # Scoped denial or endpoint failure after the client's bounded attempts.
        # Authentication and rate-limit/budget policy are not section failures.
        return exc.response.status_code in {403, 404, 408, 500, 502, 503, 504}
    if isinstance(exc, httpx.RequestError):
        return True
    return (
        isinstance(exc, Trading212DataError)
        and type(exc.code) is str
        and exc.code in _FETCH_REJECTIONS
    )


async def _fetch_once(
    session: AsyncSession,
    client: Trading212Client,
    *,
    allow_history_only: bool,
) -> tuple[_FetchedTrading212Data, dict[str, Exception]]:
    errors: dict[str, Exception] = {}
    fetched = _FetchedTrading212Data()
    # Complete broker I/O once, outside every write transaction. Capture the
    # phase here, not from an exception-supplied URL or untrusted metadata.
    endpoint = "sync"
    try:
        for endpoint, fetch in (
            ("positions", client.fetch_positions),
            ("account_summary", client.fetch_account_summary),
            ("orders", client.fetch_historical_orders),
            ("transactions", client.fetch_transactions),
        ):
            try:
                fetched.observed_at[endpoint] = dt.datetime.now(dt.UTC)
                fetched.responses[endpoint] = await fetch()
                if allow_history_only and endpoint == "account_summary":
                    fetched.valuation = ValuationObservation(
                        fetched.observed_at["positions"],
                        dt.datetime.now(dt.UTC),
                        ledger_scope(settings.trading212_account_name),
                    )
            except Exception as exc:
                denied_summary = (
                    endpoint == "account_summary"
                    and isinstance(exc, httpx.HTTPStatusError)
                    and exc.response.status_code == 403
                )
                if not allow_history_only and denied_summary:
                    fetched.responses[endpoint] = exc
                    continue
                if not allow_history_only or not _section_fetch_failure(exc):
                    raise
                failure = (
                    Trading212DataError(
                        "Required cash is unavailable.", code="account_summary_forbidden"
                    )
                    if denied_summary
                    else exc
                )
                _annotate(failure, endpoint, "fetch")
                errors[endpoint] = failure
    except BaseException as exc:
        await session.rollback()
        _annotate(exc, endpoint, "fetch")
        raise

    return fetched, errors


async def _run_sync(
    session: AsyncSession,
    client: Trading212Client,
    *,
    force: bool,
    allow_history_only: bool,
) -> Trading212SyncResult | Trading212Incomplete:
    fetched, errors = await _fetch_once(session, client, allow_history_only=allow_history_only)
    # Each rejection removes its entire section (and the valuation). A fresh
    # joined transaction revalidates eligible history against retained DB state;
    # never release a SQLite savepoint or commit one section ahead of another.
    while not {"orders", "transactions"}.issubset(errors):
        endpoint, phase = "sync", "setup"
        snapshot = orders = cash = None
        try:
            connection = await session.connection()
            if allow_history_only and connection.dialect.name == "sqlite":
                # SQLite legacy SELECTs alone do not reserve the writer. Pin
                # retained evidence through commit, including duplicate checks.
                await connection.exec_driver_sql("UPDATE import_batches SET id = id WHERE 0")
            async with AsyncSession(
                bind=connection,
                join_transaction_mode="rollback_only",
                expire_on_commit=False,
            ) as joined:
                if not errors:
                    endpoint, phase = "positions", "import"
                    snapshot = await _stage_snapshot(joined, fetched, force=force)
                if "orders" not in errors:
                    endpoint, phase = "orders", "import"
                    orders = await _stage_orders(
                        joined, fetched, force=force, require_retained=allow_history_only,
                        manual_matching_only=snapshot is None,
                    )
                if "transactions" not in errors:
                    endpoint, phase = "transactions", "import"
                    cash = await sync_cash_history(
                        joined,
                        fetched,
                        account_name=settings.trading212_account_name,
                        commit=False,
                        observed_at=fetched.observed_at["transactions"]
                        if allow_history_only
                        else None,
                    )
                endpoint, phase = "sync", "commit"
                if errors:
                    statuses: dict[str, str] = {}
                    if orders is not None:
                        statuses["orders"] = orders[0]
                    if cash is not None:
                        statuses["transactions"] = (
                            "imported" if cash["imported_count"] else "unchanged"
                        )
                    result = _incomplete(errors, statuses, fetched.observed_at)
                else:
                    assert snapshot is not None and orders is not None and cash is not None
                    result = Trading212SyncResult(
                        account_name=settings.trading212_account_name,
                        snapshot=snapshot[0],
                        snapshot_rows=snapshot[1],
                        valuation_at=snapshot[2],
                        orders=orders[0],
                        order_rows=orders[1],
                        cash_flows_imported=cash["imported_count"],
                        cash_flows_total=cash["total_count"],
                        fetched_at=cash["fetched_at"],
                    )
                await joined.flush()
            if allow_history_only and isinstance(client, Trading212Client):
                phase = "deadline"
                client.check_budget()
                phase = "commit"
            await session.commit()
            return result
        except BaseException as exc:
            await session.rollback()
            _annotate(exc, endpoint, phase)
            if not (
                allow_history_only
                and phase == "import"
                and isinstance(exc, Trading212DataError)
                and type(exc.code) is str
                and exc.code in _SECTION_REJECTIONS[endpoint]
            ):
                raise
            errors[endpoint] = exc
    return _incomplete(errors, {}, fetched.observed_at)


@router.get("/status", response_model=Trading212Status)
async def trading212_status() -> Trading212Status:
    key = settings.trading212_api_key
    secret = settings.trading212_api_secret
    configured = bool(
        key and secret and key.get_secret_value().strip() and secret.get_secret_value().strip()
    )
    return Trading212Status(
        configured=configured,
        account_name=settings.trading212_account_name,
    )


@router.post(
    "/sync/portfolio",
    response_model=ImportResult,
    status_code=status.HTTP_201_CREATED,
)
async def sync_trading212_portfolio(
    force: bool = Query(default=False),
    _broker_guard: None = Depends(require_local_broker),
    _origin_guard: None = Depends(require_local_origin),
    session: AsyncSession = Depends(get_session),
    client: Trading212Reader = Depends(get_trading212_client),
) -> ImportResult:
    try:
        batch, summary = await sync_portfolio_snapshot(
            session,
            client,
            account_name=settings.trading212_account_name,
            force=force,
        )
    except DuplicateImportError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "This Trading 212 snapshot is unchanged.",
                "existing_batch_id": exc.batch_id,
            },
        ) from exc
    except Exception as exc:
        raise _provider_error(exc, operation="positions") from exc
    return ImportResult(batch=ImportBatchOut.model_validate(batch), summary=summary)


@router.post(
    "/sync/orders",
    response_model=OrderImportBatchOut,
    status_code=status.HTTP_201_CREATED,
)
async def sync_trading212_orders(
    force: bool = Query(default=False),
    _broker_guard: None = Depends(require_local_broker),
    _origin_guard: None = Depends(require_local_origin),
    session: AsyncSession = Depends(get_session),
    client: Trading212Reader = Depends(get_trading212_client),
) -> OrderImportBatchOut:
    try:
        batch, _inserted = await sync_order_history(
            session,
            client,
            account_name=settings.trading212_account_name,
            force=force,
        )
    except DuplicateOrderImportError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"This Trading 212 order history is unchanged (batch {exc.batch_id}).",
        ) from exc
    except Exception as exc:
        raise _provider_error(exc, operation="orders") from exc
    return OrderImportBatchOut(
        id=batch.id,
        created_at=batch.created_at,
        filename=batch.filename,
        row_count=batch.row_count,
    )

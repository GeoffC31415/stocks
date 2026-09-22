from __future__ import annotations

import datetime as dt  # noqa: TC003 - Pydantic runtime annotation.
import logging
from dataclasses import dataclass
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
    fetched_at: dt.datetime


class Trading212Status(BaseModel):
    configured: bool
    account_name: str


@dataclass(frozen=True)
class _FetchedTrading212Data:
    """Replay fetched responses to import services without any network access."""

    positions: list[Mapping[str, Any]]
    account_summary: Mapping[str, Any] | httpx.HTTPStatusError
    historical_orders: list[Mapping[str, Any]]
    transactions: list[Mapping[str, Any]]

    async def fetch_positions(self) -> list[Mapping[str, Any]]:
        return self.positions

    async def fetch_account_summary(self) -> Mapping[str, Any]:
        if isinstance(self.account_summary, httpx.HTTPStatusError):
            # Preserve the service's verified-currency/no-invented-cash fallback.
            raise self.account_summary
        return self.account_summary

    async def fetch_historical_orders(self) -> list[Mapping[str, Any]]:
        return self.historical_orders

    async def fetch_transactions(self) -> list[Mapping[str, Any]]:
        return self.transactions


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


def _provider_error(exc: Exception) -> HTTPException:
    if isinstance(exc, httpx.HTTPStatusError):
        return HTTPException(
            status_code=502,
            detail=f"Trading 212 returned HTTP {exc.response.status_code}.",
        )
    if isinstance(exc, httpx.HTTPError):
        return HTTPException(status_code=502, detail="Trading 212 could not be reached.")
    if isinstance(exc, Trading212DataError):
        return HTTPException(status_code=400, detail=str(exc))
    logger.exception("Unexpected Trading 212 sync failure", exc_info=exc)
    return HTTPException(status_code=500, detail="Trading 212 sync failed.")


@router.post("/sync/cash-flows", response_model=CashFlowSyncResult)
async def sync_trading212_cash_flows(
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
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 403:
            raise HTTPException(
                status_code=502,
                detail="Trading 212 cash history requires the read-only history:transactions permission.",
            ) from exc
        raise _provider_error(exc) from exc
    return CashFlowSyncResult.model_validate(result)


@router.post("/sync", response_model=Trading212SyncResult)
async def sync_trading212_all(
    force: bool = Query(default=False),
    _origin_guard: None = Depends(require_local_origin),
    session: AsyncSession = Depends(get_session),
    client: Trading212Client = Depends(get_trading212_client),
) -> Trading212SyncResult:
    """Refresh the complete read-only Trading 212 dataset in one action."""
    try:
        # Complete all broker I/O before opening a transaction or taking a writer lock.
        positions = await client.fetch_positions()
        account_summary: Mapping[str, Any] | httpx.HTTPStatusError
        try:
            account_summary = await client.fetch_account_summary()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 403:
                raise
            account_summary = exc
        fetched = _FetchedTrading212Data(
            positions=positions,
            account_summary=account_summary,
            historical_orders=await client.fetch_historical_orders(),
            transactions=await client.fetch_transactions(),
        )
        # Legacy matching helpers commit internally. Join the caller's transaction
        # without allowing those commits to reach the database connection.
        async with AsyncSession(
            bind=await session.connection(),
            join_transaction_mode="rollback_only",
            expire_on_commit=False,
        ) as import_session:
            try:
                _batch, summary = await sync_portfolio_snapshot(
                    import_session,
                    fetched,
                    account_name=settings.trading212_account_name,
                    force=force,
                    commit=False,
                )
                snapshot = "imported"
                snapshot_rows = summary.get("row_count") if isinstance(summary, dict) else None
            except DuplicateImportError:
                snapshot, snapshot_rows = "unchanged", None
            try:
                order_batch, _inserted = await sync_order_history(
                    import_session,
                    fetched,
                    account_name=settings.trading212_account_name,
                    force=force,
                    commit=False,
                )
                orders, order_rows = "imported", order_batch.row_count
            except DuplicateOrderImportError:
                orders, order_rows = "unchanged", None
            cash = await sync_cash_history(
                import_session, fetched, account_name=settings.trading212_account_name, commit=False
            )
            await import_session.flush()
        await session.commit()
    except Exception as exc:
        await session.rollback()
        raise _provider_error(exc) from exc
    return Trading212SyncResult(
        account_name=settings.trading212_account_name,
        snapshot=snapshot,
        snapshot_rows=snapshot_rows,
        orders=orders,
        order_rows=order_rows,
        cash_flows_imported=cash["imported_count"],
        cash_flows_total=cash["total_count"],
        fetched_at=cash["fetched_at"],
    )


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
        raise _provider_error(exc) from exc
    return ImportResult(batch=ImportBatchOut.model_validate(batch), summary=summary)


@router.post(
    "/sync/orders",
    response_model=OrderImportBatchOut,
    status_code=status.HTTP_201_CREATED,
)
async def sync_trading212_orders(
    force: bool = Query(default=False),
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
        raise _provider_error(exc) from exc
    return OrderImportBatchOut(
        id=batch.id,
        created_at=batch.created_at,
        filename=batch.filename,
        row_count=batch.row_count,
    )

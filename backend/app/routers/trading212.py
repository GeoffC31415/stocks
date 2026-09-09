from __future__ import annotations

import datetime as dt  # noqa: TC003 - Pydantic runtime annotation.
import logging

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


def require_local_origin(request: Request) -> None:
    """Block browser-triggered credential use from non-local web origins."""
    origin = request.headers.get("origin")
    if origin is None:
        return
    if origin not in _TRUSTED_ORIGINS:
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
    batch = None
    order_batch = None
    batch_id = None
    order_batch_id = None
    try:
        try:
            batch, summary = await sync_portfolio_snapshot(
                session,
                client,
                account_name=settings.trading212_account_name,
                force=force,
                commit=False,
            )
            snapshot = "imported"
            batch_id = batch.id
            snapshot_rows = summary.get("row_count") if isinstance(summary, dict) else None
        except DuplicateImportError:
            snapshot, snapshot_rows = "unchanged", None
        try:
            order_batch, _inserted = await sync_order_history(
                session,
                client,
                account_name=settings.trading212_account_name,
                force=force,
                commit=False,
            )
            orders, order_rows = "imported", order_batch.row_count
            order_batch_id = order_batch.id
        except DuplicateOrderImportError:
            orders, order_rows = "unchanged", None
        cash = await sync_cash_history(
            session, client, account_name=settings.trading212_account_name, commit=False
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        # Defensive cleanup protects all-or-nothing semantics even if a future
        # collaborator accidentally reintroduces an inner commit.
        from sqlalchemy import delete

        from app.models import ImportBatch, OrderImportBatch

        if batch_id is not None:
            await session.execute(delete(ImportBatch).where(ImportBatch.id == batch_id))
        if order_batch_id is not None:
            await session.execute(
                delete(OrderImportBatch).where(OrderImportBatch.id == order_batch_id)
            )
        await session.commit()
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

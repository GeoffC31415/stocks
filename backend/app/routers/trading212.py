from __future__ import annotations

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
    Trading212Client,
    Trading212DataError,
    Trading212Reader,
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


@router.get("/status", response_model=Trading212Status)
async def trading212_status() -> Trading212Status:
    key = settings.trading212_api_key
    secret = settings.trading212_api_secret
    configured = bool(
        key
        and secret
        and key.get_secret_value().strip()
        and secret.get_secret_value().strip()
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

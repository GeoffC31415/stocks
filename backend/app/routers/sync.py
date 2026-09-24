"""Sync-all API: one button for every account, plus per-account freshness."""

from __future__ import annotations

import asyncio
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002 - FastAPI runtime annotation.

from app.config import settings
from app.database import get_session
from app.models import HoldingSnapshot, ImportBatch, Instrument
from app.routers.trading212 import require_local_origin
from app.services.sync_control import (
    SyncBusy,
    public_report,
    request_service_sync,
    service_sync_status,
)
from app.services.sync_runner import read_last_sync, run_sync_all

router = APIRouter(prefix="/api/sync", tags=["sync"])
_lock = asyncio.Lock()


class AccountFreshness(BaseModel):
    account_name: str
    last_snapshot_date: dt.date | None
    age_days: int | None
    stale: bool


class SyncStatus(BaseModel):
    manual_sync_enabled: bool
    service_trigger_enabled: bool = False
    accounts: list[AccountFreshness]
    stale_after_days: int
    last_run: dict | None
    running: bool


def _fetchers(include_fetch: bool) -> list:
    if not include_fetch:
        return []
    from app.fetchers import barclays, hl

    return [("Hargreaves Lansdown", hl.fetch), ("Barclays", barclays.fetch)]


def require_manual_sync(request: Request) -> None:
    """Public hosting never lets a web request trigger broker logins.

    Declared before the database dependency so a refused request opens no session;
    the scheduled job (stocks-sync.timer / make sync) is the only fetch path.
    """
    config = getattr(getattr(request.scope.get("app"), "state", None), "web_config", settings)
    if config.deployment_mode == "public":
        raise HTTPException(status_code=403, detail="Sync runs on the daily schedule.")


@router.post("/request", status_code=202)
async def request_sync(request: Request) -> dict:
    config = getattr(getattr(request.scope.get("app"), "state", None), "web_config", settings)
    if config.deployment_mode != "public" or not config.sync_service_trigger_enabled:
        raise HTTPException(status_code=403, detail="Service sync is disabled.")
    if request.headers.getlist("origin") != [config.public_origin]:
        raise HTTPException(status_code=403, detail="Cross-origin request forbidden")
    if request.query_params or await request.body():
        raise HTTPException(status_code=400, detail="This endpoint accepts no parameters.")
    return await asyncio.to_thread(request_service_sync, config.resolved_sync_inbox())


@router.get("/request")
async def requested_sync_status(request: Request) -> dict:
    config = getattr(getattr(request.scope.get("app"), "state", None), "web_config", settings)
    if config.deployment_mode != "public" or not config.sync_service_trigger_enabled:
        return {"state": "disabled", "request_id": None, "last_run": None}
    return await asyncio.to_thread(service_sync_status, config.resolved_sync_inbox())


@router.post("/all")
async def sync_all(
    fetch: bool = Query(default=True, description="Log in to brokers and download exports"),
    _manual_guard: None = Depends(require_manual_sync),
    _origin_guard: None = Depends(require_local_origin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if _lock.locked():
        raise HTTPException(status_code=409, detail="A sync is already running.")
    async with _lock:
        try:
            report = await run_sync_all(session, fetchers=_fetchers(fetch))
        except SyncBusy:
            raise HTTPException(status_code=409, detail="A sync is already running.") from None
    return report.to_json()


@router.get("/status", response_model=SyncStatus)
async def sync_status(request: Request, session: AsyncSession = Depends(get_session)) -> SyncStatus:
    config = getattr(getattr(request.scope.get("app"), "state", None), "web_config", settings)
    rows = await session.execute(
        select(Instrument.account_name, func.max(ImportBatch.as_of_date))
        .join(HoldingSnapshot, HoldingSnapshot.instrument_id == Instrument.id)
        .join(ImportBatch, ImportBatch.id == HoldingSnapshot.import_batch_id)
        .group_by(Instrument.account_name)
        .order_by(Instrument.account_name)
    )
    today = dt.date.today()
    limit = settings.sync_stale_days
    accounts = []
    for name, last in rows.all():
        age = (today - last).days if last else None
        accounts.append(
            AccountFreshness(
                account_name=name,
                last_snapshot_date=last,
                age_days=age,
                stale=age is None or age > limit,
            )
        )
    return SyncStatus(
        manual_sync_enabled=config.deployment_mode != "public",
        service_trigger_enabled=config.deployment_mode == "public"
        and config.sync_service_trigger_enabled,
        accounts=accounts,
        stale_after_days=limit,
        last_run=public_report(read_last_sync(config.resolved_sync_inbox()))
        if config.deployment_mode == "public"
        else read_last_sync(config.resolved_sync_inbox()),
        running=_lock.locked(),
    )

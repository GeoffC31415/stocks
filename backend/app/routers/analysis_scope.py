"""Validation shared by period-scoped, cache-only portfolio endpoints."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Instrument
from app.services.performance_service import PERIOD_OPTIONS


async def validate_analysis_scope(
    request: Request, session: AsyncSession = Depends(get_session),
) -> None:
    params = request.query_params
    for key in ("account_name", "period", "start", "end", "from_date", "to_date"):
        if len(params.getlist(key)) > 1:
            raise HTTPException(422, f"Repeated scope parameter: {key}")
    if "start" in params or "end" in params:
        raise HTTPException(422, "Custom analysis dates are not supported; choose a period.")
    if "period" in params and params["period"] not in PERIOD_OPTIONS:
        raise HTTPException(422, "Choose one of 1M/3M/6M/1Y/YTD/ALL.")
    if "period" in params and ("from_date" in params or "to_date" in params):
        raise HTTPException(422, "Choose either a period or explicit return dates, not both.")
    if "account_name" in params:
        account = params["account_name"]
        exists = await session.scalar(select(Instrument.id).where(Instrument.account_name == account).limit(1))
        if not account or exists is None:
            raise HTTPException(422, "Unknown account; select an existing account.")

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas import CGTSummaryResponse
from app.services.cgt_service import get_cgt_summary

router = APIRouter(prefix="/api/cgt", tags=["cgt"])


@router.get("/summary", response_model=CGTSummaryResponse)
async def cgt_summary(
    account_name: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> CGTSummaryResponse:
    """UK Capital Gains Tax summary grouped by tax year.

    Implements the three CGT matching rules for shares:
    1. Same-day rule -- buys & sells on the same day match first
    2. Bed & breakfasting (30-day rule) -- buys within 30 days after a sale
    3. Section 104 pool -- remaining shares form a pooled holding
    """
    data = await get_cgt_summary(session, account_name=account_name)
    return CGTSummaryResponse(**data)

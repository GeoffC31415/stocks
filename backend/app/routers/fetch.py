"""
API endpoints for triggering external data fetches (e.g., Barclays Smart Investor).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.barclays_worker import worker, FetchStatus

router = APIRouter(prefix="/api/fetch", tags=["fetch"])


class FetchRequest(BaseModel):
    provider: str = "barclays"
    report_type: str = "holdings"


class FetchResponse(BaseModel):
    status: str
    message: str
    report_path: str | None = None
    error: str | None = None


@router.post("/barclays", response_model=FetchResponse)
async def fetch_barclays(req: FetchRequest):
    """Trigger a background fetch for Barclays Smart Investor data."""
    if worker.status.status == "running":
        raise HTTPException(status_code=409, detail="Fetch already in progress.")
    
    job_id = worker.start_fetch(req.report_type)
    return FetchResponse(
        status="started",
        message=f"Fetch started for {req.report_type} report.",
    )


@router.get("/status", response_model=FetchResponse)
async def get_fetch_status():
    """Get the current status of the fetch job."""
    return FetchResponse(
        status=worker.status.status,
        message=worker.status.message,
        report_path=worker.status.report_path,
        error=worker.status.error,
    )

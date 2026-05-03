from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import ImportBatch
from app.schemas import ImportBatchOut, ImportDiffSummary, ImportResult, SnapshotDiffResponse
from app.services.import_service import (
    DuplicateImportError,
    compare_import_batches,
    get_import_batch,
    get_import_diff_summary,
    import_barclays_xls,
)

router = APIRouter(prefix="/api/imports", tags=["imports"])


@router.post("", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
async def create_import(
    file: UploadFile = File(...),
    as_of_date: dt.date | None = Form(default=None),
    file_metadata_date: dt.date | None = Form(default=None),
    force: bool = Form(default=False),
    session: AsyncSession = Depends(get_session),
) -> ImportResult:
    if not file.filename or not file.filename.lower().endswith(".xls"):
        raise HTTPException(status_code=400, detail="Please upload a .xls file.")
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        batch, summary = await import_barclays_xls(
            session,
            file_bytes=payload,
            filename=file.filename,
            as_of_date=as_of_date,
            file_metadata_as_of=file_metadata_date,
            force=force,
        )
    except DuplicateImportError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "This exact file was already imported.",
                "existing_batch_id": exc.batch_id,
            },
        ) from exc
    except Exception as exc:  # pragma: no cover - safety for malformed broker files
        raise HTTPException(status_code=400, detail=f"Import failed: {exc}") from exc

    return ImportResult(
        batch=ImportBatchOut.model_validate(batch),
        summary=summary,
    )


@router.get("", response_model=list[ImportBatchOut])
async def list_imports(session: AsyncSession = Depends(get_session)) -> list[ImportBatchOut]:
    result = await session.execute(select(ImportBatch).order_by(ImportBatch.id.desc()))
    return [ImportBatchOut.model_validate(row) for row in result.scalars().all()]


@router.get("/diff", response_model=SnapshotDiffResponse)
async def compare_imports(
    from_id: int = Query(alias="from"),
    to_id: int = Query(alias="to"),
    session: AsyncSession = Depends(get_session),
) -> SnapshotDiffResponse:
    data = await compare_import_batches(
        session,
        from_batch_id=from_id,
        to_batch_id=to_id,
    )
    if data is None:
        raise HTTPException(status_code=404, detail="Import batch not found.")
    return SnapshotDiffResponse.model_validate(data)


@router.get("/{batch_id}", response_model=ImportBatchOut)
async def get_import(
    batch_id: int,
    session: AsyncSession = Depends(get_session),
) -> ImportBatchOut:
    batch = await get_import_batch(session, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Import batch not found.")
    return ImportBatchOut.model_validate(batch)


@router.get("/{batch_id}/diff", response_model=ImportDiffSummary)
async def get_import_diff(
    batch_id: int,
    session: AsyncSession = Depends(get_session),
) -> ImportDiffSummary:
    summary = await get_import_diff_summary(session, batch_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Import batch not found.")
    return ImportDiffSummary.model_validate(summary)

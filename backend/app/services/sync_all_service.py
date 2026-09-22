"""Import every broker export found in the sync inbox, routed by content.

The inbox is owned by the automation: processed files are moved to
``processed/YYYY-MM-DD/`` and unrecognised files to ``rejected/``. Extra
sources (e.g. ``~/Downloads``) are only read, never moved or deleted.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import shutil
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,  # noqa: TC002 - used at runtime by callers' annotations
)

from app.models import ImportBatch, OrderImportBatch
from app.services.export_classifier import ExportKind, UnrecognisedExport, classify_export
from app.services.import_service import (
    DuplicateImportError,
    import_barclays_xls,
    import_hl_holdings_csv,
)
from app.services.order_service import (
    DuplicateOrderImportError,
    import_hl_orders_csv,
    import_order_history,
)

logger = logging.getLogger(__name__)

# Matches the app-wide default (frontend DRIP_DEFAULT) and existing imported data.
DRIP_THRESHOLD_GBP = 1000.0
_SUFFIXES = {".csv", ".xls", ".xlsx"}

Importer = Callable[..., Awaitable[Any]]


async def _hl_holdings(session: AsyncSession, data: bytes, name: str, as_of: dt.date) -> None:
    await import_hl_holdings_csv(session, file_bytes=data, filename=name, as_of_date=as_of)


async def _barclays_holdings(session: AsyncSession, data: bytes, name: str, as_of: dt.date) -> None:
    await import_barclays_xls(session, file_bytes=data, filename=name, as_of_date=as_of)


async def _hl_activity(session: AsyncSession, data: bytes, name: str, as_of: dt.date) -> None:
    await import_hl_orders_csv(
        session, file_bytes=data, filename=name, drip_threshold_gbp=DRIP_THRESHOLD_GBP
    )


async def _barclays_orders(session: AsyncSession, data: bytes, name: str, as_of: dt.date) -> None:
    await import_order_history(
        session, file_bytes=data, filename=name, drip_threshold_gbp=DRIP_THRESHOLD_GBP
    )


_IMPORTERS: dict[str, Importer] = {
    ExportKind.HL_HOLDINGS.value: _hl_holdings,
    ExportKind.HL_ACTIVITY.value: _hl_activity,
    ExportKind.BARCLAYS_HOLDINGS.value: _barclays_holdings,
    ExportKind.BARCLAYS_ORDERS.value: _barclays_orders,
}
_SNAPSHOT_KINDS = {ExportKind.HL_HOLDINGS.value, ExportKind.BARCLAYS_HOLDINGS.value}


@dataclass
class FileResult:
    filename: str
    source: str
    kind: str | None
    as_of: dt.date | None
    status: str  # imported | unchanged | new (dry run) | rejected | failed
    detail: str | None = None


@dataclass
class SyncReport:
    files: list[FileResult] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for item in self.files:
            out[item.status] = out.get(item.status, 0) + 1
        return out


@dataclass
class _Candidate:
    path: Path
    in_inbox: bool
    data: bytes
    sha: str
    kind: str
    generated_at: dt.datetime


def _list_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in _SUFFIXES)


async def _already_imported(session: AsyncSession, kind: str, sha: str) -> bool:
    model = ImportBatch if kind in _SNAPSHOT_KINDS else OrderImportBatch
    found = await session.execute(select(model.id).where(model.file_sha256 == sha).limit(1))
    return found.scalar_one_or_none() is not None


def _move(path: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / path.name
    n = 1
    while target.exists():
        target = dest_dir / f"{path.stem} ({n}){path.suffix}"
        n += 1
    shutil.move(str(path), target)


async def sync_inbox(
    session: AsyncSession,
    inbox: Path,
    *,
    extra_sources: Iterable[Path] = (),
    dry_run: bool = False,
    today: dt.date | None = None,
) -> SyncReport:
    """Classify, import and file away every export. One file's failure never blocks others."""
    today = today or dt.date.today()
    report = SyncReport()
    candidates: list[_Candidate] = []
    sources = [(inbox, True)] + [(Path(s), False) for s in extra_sources]

    for folder, in_inbox in sources:
        for path in _list_files(folder):
            data = path.read_bytes()
            try:
                classified = classify_export(path.name, data)
            except UnrecognisedExport as exc:
                if in_inbox:  # foreign files in e.g. Downloads are silently ignored
                    report.files.append(
                        FileResult(path.name, str(folder), None, None, "rejected", str(exc))
                    )
                    if not dry_run:
                        _move(path, inbox / "rejected")
                continue
            generated = classified.generated_at or dt.datetime.fromtimestamp(path.stat().st_mtime)
            candidates.append(
                _Candidate(
                    path,
                    in_inbox,
                    data,
                    hashlib.sha256(data).hexdigest(),
                    classified.kind.value,
                    generated,
                )
            )

    # Chronological per the broker's own timestamp: snapshot "closed" semantics depend on order.
    candidates.sort(key=lambda c: (c.generated_at, c.path.name))
    seen: set[tuple[str, str]] = set()
    for cand in candidates:
        result = FileResult(
            cand.path.name, str(cand.path.parent), cand.kind, cand.generated_at.date(), "imported"
        )
        key = (cand.kind in _SNAPSHOT_KINDS and "snap" or "orders", cand.sha)
        if key in seen or await _already_imported(session, cand.kind, cand.sha):
            result.status = "unchanged"
        elif dry_run:
            result.status = "new"
        else:
            try:
                await _IMPORTERS[cand.kind](session, cand.data, cand.path.name, result.as_of)
            except (DuplicateImportError, DuplicateOrderImportError):
                await session.rollback()
                result.status = "unchanged"
            except Exception as exc:
                await session.rollback()
                logger.exception("Import failed for %s", cand.path.name)
                result.status = "failed"
                result.detail = f"{type(exc).__name__}: {exc}"[:300]
        seen.add(key)
        if cand.in_inbox and not dry_run and result.status in {"imported", "unchanged"}:
            _move(cand.path, inbox / "processed" / today.isoformat())
        if cand.in_inbox or result.status != "unchanged":
            report.files.append(result)
    return report

"""One entry point that refreshes every account.

Order: browser fetchers (HL, Barclays) download into the inbox → the inbox is
imported by content → Trading 212 API sync. Each step's failure is recorded
and never blocks the others. The last run report is written to
``<inbox>/last-sync.json`` for status display and notifications (no values).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import (
    AsyncSession,  # noqa: TC002 - used at runtime by callers' annotations
)

from app.config import settings
from app.services.barclays_sync_service import FetchedPair, import_pair
from app.services.sync_all_service import SyncReport, sync_inbox
from app.services.sync_control import atomic_json, file_lock, validated_invocation_id

logger = logging.getLogger(__name__)

# A hung browser must never stop the inbox import or Trading 212 from running.
FETCH_TIMEOUT_SECONDS = 300

# A fetcher downloads exports into the inbox and returns a short status line.
Fetcher = Callable[[Path], Awaitable["StepResult | FetchedPair"]]


@dataclass
class StepResult:
    name: str
    status: str  # ok | unchanged | skipped | failed | needs_attention
    detail: str | None = None


@dataclass
class RunReport:
    started_at: str
    finished_at: str | None = None
    steps: list[StepResult] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    invocation_id: str | None = None

    @property
    def ok(self) -> bool:
        return not any(s.status in {"failed", "needs_attention"} for s in self.steps) and not any(
            f["status"] == "failed" for f in self.files
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "invocation_id": self.invocation_id,
            "finished_at": self.finished_at,
            "ok": self.ok,
            "steps": [asdict(s) for s in self.steps],
            "files": self.files,
        }

    def summary_lines(self) -> list[str]:
        lines = [
            f"{s.name}: {s.status}" + (f" ({s.detail})" if s.detail else "") for s in self.steps
        ]
        for f in self.files:
            if f["status"] in {"imported", "failed", "rejected", "new"}:
                label = f["kind"] or f["filename"]
                lines.append(f"  {label} {f['as_of'] or ''}: {f['status']}".rstrip())
        return lines


def _trading212_configured() -> bool:
    key, secret = settings.trading212_api_key, settings.trading212_api_secret
    return bool(
        key and secret and key.get_secret_value().strip() and secret.get_secret_value().strip()
    )


async def _trading212_step(session: AsyncSession) -> StepResult:
    # Imported lazily to keep this module importable without FastAPI routing.
    from app.routers.trading212 import get_trading212_client, run_trading212_sync
    from app.services.trading212 import Trading212DataError

    if not _trading212_configured():
        return StepResult("Trading 212", "skipped", "no API credentials")
    try:
        result = await run_trading212_sync(session, get_trading212_client())
    except httpx.HTTPStatusError as exc:
        return StepResult("Trading 212", "failed", f"HTTP {exc.response.status_code}")
    except httpx.HTTPError:
        return StepResult("Trading 212", "failed", "could not be reached")
    except Trading212DataError as exc:
        return StepResult("Trading 212", "failed", str(exc)[:200])
    except Exception:
        logger.exception("Trading 212 sync failed")
        return StepResult("Trading 212", "failed", "unexpected error (see log)")
    changed = (
        result.snapshot == "imported" or result.orders == "imported" or result.cash_flows_imported
    )
    return StepResult(
        "Trading 212",
        "ok" if changed else "unchanged",
        f"snapshot {result.snapshot}, orders {result.orders}, cash +{result.cash_flows_imported}",
    )


async def run_sync_all(
    session: AsyncSession,
    *,
    fetchers: Iterable[tuple[str, Fetcher]] = (),
    include_trading212: bool = True,
    extra_sources: Iterable[Path] = (),
    dry_run: bool = False,
    inbox: Path | None = None,
    write_status: bool = True,
) -> RunReport:
    inbox = inbox or settings.resolved_sync_inbox()
    with file_lock(inbox / "sync-run.lock"):
        return await _run_sync_all_locked(
            session,
            fetchers=fetchers,
            include_trading212=include_trading212,
            extra_sources=extra_sources,
            dry_run=dry_run,
            inbox=inbox,
            write_status=write_status,
        )


async def _run_sync_all_locked(
    session: AsyncSession,
    *,
    fetchers: Iterable[tuple[str, Fetcher]] = (),
    include_trading212: bool = True,
    extra_sources: Iterable[Path] = (),
    dry_run: bool = False,
    inbox: Path | None = None,
    write_status: bool = True,
) -> RunReport:
    inbox = inbox or settings.resolved_sync_inbox()
    inbox.mkdir(parents=True, exist_ok=True)
    report = RunReport(
        started_at=dt.datetime.now(dt.UTC).isoformat(),
        invocation_id=validated_invocation_id(os.environ.get("INVOCATION_ID")),
    )
    if write_status and not dry_run:
        atomic_json(inbox / "last-sync.json", report.to_json())

    for name, fetch in fetchers:
        if dry_run:
            report.steps.append(StepResult(name, "skipped", "dry run"))
            continue
        try:
            fetched = await asyncio.wait_for(fetch(inbox), FETCH_TIMEOUT_SECONDS)
            if isinstance(fetched, FetchedPair):
                imported_pair = await import_pair(
                    session, fetched.holdings, fetched.orders, as_of=fetched.as_of
                )
                # No further login is permitted until the whole pair commits.
                fetched.acknowledge()
                changed = (
                    imported_pair["snapshot"] == "imported" or imported_pair["orders"] == "imported"
                )
                report.steps.append(
                    StepResult(
                        name,
                        "ok" if changed else "unchanged",
                        f"snapshot {imported_pair['snapshot']}, orders {imported_pair['orders']}; "
                        f"{imported_pair['cancelled_orders']} cancelled orders excluded",
                    )
                )
            else:
                report.steps.append(fetched)
        except TimeoutError:
            logger.error("%s fetcher timed out", name)
            report.steps.append(
                StepResult(name, "failed", f"timed out after {FETCH_TIMEOUT_SECONDS}s")
            )
        except Exception as exc:
            logger.error("%s sync failed (%s)", name, type(exc).__name__)
            report.steps.append(StepResult(name, "failed", f"{type(exc).__name__}"))

    files: SyncReport = await sync_inbox(
        session, inbox, extra_sources=extra_sources, dry_run=dry_run
    )
    report.files = [
        {**asdict(f), "as_of": f.as_of.isoformat() if f.as_of else None} for f in files.files
    ]
    failed = sum(1 for f in files.files if f.status == "failed")
    imported = sum(1 for f in files.files if f.status in {"imported", "new"})
    report.steps.append(
        StepResult(
            "Import files",
            "failed" if failed else ("ok" if imported else "unchanged"),
            f"{imported} {'new' if dry_run else 'imported'}, {failed} failed"
            if files.files
            else None,
        )
    )

    if include_trading212 and not dry_run:
        report.steps.append(await _trading212_step(session))

    report.finished_at = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    if write_status and not dry_run:
        atomic_json(inbox / "last-sync.json", report.to_json())
    return report


def read_last_sync(inbox: Path | None = None) -> dict[str, Any] | None:
    path = (inbox or settings.resolved_sync_inbox()) / "last-sync.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None

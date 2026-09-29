"""One entry point that refreshes every account.

Order: browser fetchers (HL, Barclays) download into the inbox → the inbox is
imported by content → Trading 212 API sync. Each step's failure is recorded
and never blocks the others. The last run report is written to
``<inbox>/last-sync.json`` for status display and notifications (no values).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import importlib
import json
import logging
import os
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx
from sqlalchemy.ext.asyncio import (
    AsyncSession,  # noqa: TC002 - used at runtime by callers' annotations
)

from app.config import settings
from app.services.barclays_sync_service import FetchedPair, import_pair
from app.services.sync_all_service import SyncReport, sync_inbox
from app.services.sync_control import atomic_json, file_lock, public_report, validated_invocation_id
from app.services.sync_freshness import REQUIRED_SECTIONS, update_freshness, verified_sections

logger = logging.getLogger(__name__)

# A hung browser must never stop the inbox import or Trading 212 from running.
FETCH_TIMEOUT_SECONDS = 300

# A fetcher downloads exports into the inbox and returns a short status line.
class StagedPair(Protocol):
    @property
    def holdings(self) -> bytes: ...

    @property
    def orders(self) -> bytes: ...

    @property
    def observed_at(self) -> dt.datetime: ...

    @property
    def as_of(self) -> dt.date: ...


Fetcher = Callable[[Path], Awaitable["StepResult | FetchedPair | StagedPair"]]


@dataclass
class StepResult:
    name: str
    status: str  # ok | unchanged | skipped | failed | needs_attention
    detail: str | None = None
    sections: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class RunReport:
    started_at: str
    finished_at: str | None = None
    steps: list[StepResult] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    invocation_id: str | None = None
    freshness: dict[str, Any] = field(default_factory=dict)

    @property
    def outcome(self) -> str:
        failures = {"failed", "needs_attention", "rejected", "committed_with_attention"}
        bad = any(s.status in failures for s in self.steps) or any(
            f["status"] in failures for f in self.files
        ) or any(section.get("status") in failures for step in self.steps for section in step.sections.values())
        # Provider success must attest every required section, not merely commit.
        bad = bad or any(
            step.status in {'ok', 'unchanged', 'committed_with_attention'}
            and any(
                step.sections.get(name, {}).get('status') not in {'ok', 'imported', 'unchanged'}
                or step.sections.get(name, {}).get('coverage') != 'complete'
                or not step.sections.get(name, {}).get('verified_at')
                for name in REQUIRED_SECTIONS.get(step.name, set())
            )
            for step in self.steps
        )
        # A rejected/duplicate local file is not a successful provider observation.
        useful = any(s.status in {"ok", "committed_with_attention"} for s in self.steps) or any(
            f["status"] in {"imported", "new", "committed_with_attention"} for f in self.files
        ) or any(s.status == "unchanged" and s.name != "Import files" for s in self.steps)
        if bad:
            return "partial" if useful else "failed"
        if useful:
            return "complete"
        return "no_op" if self.files or any(s.status in {"no_op", "unchanged"} for s in self.steps) else "disabled"

    @property
    def ok(self) -> bool:
        return self.outcome not in {"partial", "failed"}

    def to_json(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "invocation_id": self.invocation_id,
            "finished_at": self.finished_at,
            "ok": self.ok,
            "schema_version": 2,
            "outcome": self.outcome,
            "freshness": self.freshness,
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
        return StepResult("Trading 212", "failed", type(exc).__name__)
    except Exception:
        logger.error("Trading 212 sync failed")
        return StepResult("Trading 212", "failed", "unexpected error (see log)")
    changed = (
        result.snapshot == "imported" or result.orders == "imported" or result.cash_flows_imported
    )
    return StepResult(
        "Trading 212",
        "ok" if changed else "unchanged",
        f"snapshot {result.snapshot}, orders {result.orders}, cash +{result.cash_flows_imported}",
        sections=verified_sections(
            {"holdings": result.snapshot, "orders": result.orders, "cash": result.snapshot, "transactions": "ok"},
            result.fetched_at.isoformat(), result.valuation_at.isoformat() if result.valuation_at else None,
            coverage=dict.fromkeys(REQUIRED_SECTIONS["Trading 212"], "complete"),
        ),
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
    previous = read_last_sync(inbox) or {}
    if previous.get("schema_version") == 2 and isinstance(previous.get("freshness"), dict):
        safe_previous = public_report(previous)
        report.freshness = safe_previous["freshness"] if safe_previous else {}
    if write_status and not dry_run:
        publish_report(inbox, report)

    try:
        await _execute_steps(session, report, fetchers=fetchers, include_trading212=include_trading212,
                             extra_sources=extra_sources, dry_run=dry_run, inbox=inbox, write_status=write_status)
    except BaseException:
        report.steps.append(StepResult("Run", "failed", "interrupted"))
        for provider, sections in report.freshness.items():
            if any(section.get("status") == "running" for section in sections.values()):
                report.steps.append(StepResult(provider, "failed", "interrupted"))
        raise
    finally:
        report.finished_at = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        for step in report.steps:
            report.freshness = update_freshness(report.freshness, asdict(step), report.started_at)
        if write_status and not dry_run:
            publish_report(inbox, report)
    return report


async def _execute_steps(session: AsyncSession, report: RunReport, *, fetchers: Iterable[tuple[str, Fetcher]], include_trading212: bool,
                         extra_sources: Iterable[Path], dry_run: bool, inbox: Path, write_status: bool) -> None:
    for name, fetch in fetchers:
        if dry_run:
            report.steps.append(StepResult(name, "skipped", "dry run"))
            continue
        report.freshness = update_freshness(report.freshness, asdict(StepResult(name, "running")), report.started_at)
        if write_status:
            publish_report(inbox, report)
        try:
            # Bound the entire broker operation, not just the browser fetch.
            # Cancellation reaches import_pair, which rolls back before exit.
            async with asyncio.timeout(FETCH_TIMEOUT_SECONDS):
                fetched = await fetch(inbox)
                if isinstance(fetched, FetchedPair):
                    imported_pair = await import_pair(
                        session, fetched.holdings, fetched.orders, as_of=fetched.as_of
                    )
                    # No further login is permitted until the whole pair commits.
                    attention = False
                    try:
                        fetched.acknowledge()
                    except Exception:
                        # The pair has committed already: acknowledgment only
                        # updates operational login/cooldown state, not holdings.
                        attention = True
                    changed = (
                        imported_pair["snapshot"] == "imported"
                        or imported_pair["orders"] == "imported"
                    )
                    report.steps.append(
                        StepResult(
                            name,
                            "committed_with_attention" if attention else ("ok" if changed else "unchanged"),
                            f"snapshot {imported_pair['snapshot']}, orders {imported_pair['orders']}; "
                            f"{imported_pair['cancelled_orders']} cancelled orders excluded",
                            sections=verified_sections(
                                {"holdings": imported_pair["snapshot"], "orders": imported_pair["orders"]},
                                fetched.observed_at.isoformat(), fetched.as_of.isoformat(),
                                coverage={"holdings": "complete", "orders": "unknown"},
                            ),
                        )
                    )
                elif isinstance(fetched, StepResult):
                    report.steps.append(fetched)
                elif name == "Hargreaves Lansdown":
                    # Integrity worker owns the staged transport and atomic
                    # import. Lazy import permits independent service rollout.
                    hl_pair = importlib.import_module("app.services.hl_sync_service")
                    if not isinstance(fetched, hl_pair.FetchedHLPair):
                        raise TypeError("Unsupported HL fetch result")
                    activity_start = getattr(fetched, "activity_start", None)
                    activity_end = getattr(fetched, "activity_end", None)
                    imported_pair = await hl_pair.import_pair(
                        session, fetched.holdings, fetched.orders, as_of=fetched.as_of,
                        activity_start=activity_start, activity_end=activity_end,
                    )
                    changed = any(imported_pair[key] == "imported" for key in ("snapshot", "orders"))
                    report.steps.append(StepResult(
                        name, "ok" if changed else "unchanged",
                        sections=verified_sections(
                            {"holdings": imported_pair["snapshot"], "orders": imported_pair["orders"]},
                            fetched.observed_at.isoformat(), str(imported_pair.get("valuation_at") or "") or None,
                            coverage={"holdings": "complete", "orders": "partial" if activity_start else "unknown"},
                            ranges={"orders": (activity_start.isoformat(), activity_end.isoformat())}
                            if activity_start and activity_end else None,
                        ),
                    ))
                else:
                    raise TypeError("Unsupported fetch result")
        except TimeoutError:
            logger.error("%s fetcher timed out", name)
            report.steps.append(
                StepResult(name, "failed", f"timed out after {FETCH_TIMEOUT_SECONDS}s")
            )
        except Exception as exc:
            logger.error("%s sync failed (%s)", name, type(exc).__name__)
            report.steps.append(StepResult(name, "failed", f"{type(exc).__name__}"))

    inbox_failed = False
    try:
        files: SyncReport = await sync_inbox(
            session, inbox, extra_sources=extra_sources, dry_run=dry_run
        )
    except Exception:
        await session.rollback()
        inbox_failed = True
        files = SyncReport()
    report.files = [
        {**asdict(f), "as_of": f.as_of.isoformat() if f.as_of else None} for f in files.files
    ]
    failed = int(inbox_failed) + sum(1 for f in files.files if f.status in {"failed", "rejected", "needs_attention", "committed_with_attention"})
    imported = sum(1 for f in files.files if f.status in {"imported", "new"})
    report.steps.append(
        StepResult(
            "Import files",
            "failed" if failed else ("ok" if imported else ("unchanged" if files.files else "no_op")),
            f"{imported} {'new' if dry_run else 'imported'}, {failed} failed"
            if files.files
            else None,
        )
    )

    if include_trading212 and not dry_run:
        report.freshness = update_freshness(report.freshness, asdict(StepResult("Trading 212", "running")), report.started_at)
        if write_status:
            publish_report(inbox, report)
        try:
            async with asyncio.timeout(FETCH_TIMEOUT_SECONDS):
                report.steps.append(await _trading212_step(session))
        except Exception:
            await session.rollback()
            report.steps.append(StepResult("Trading 212", "failed", "provider_failed"))



def publish_report(inbox: Path, report: RunReport) -> None:
    targets = [(inbox / "last-sync.json", False, 0o600)]
    if settings.sync_status_dir is not None:
        targets.append((settings.resolved_sync_status_dir() / "last-sync.json", True, 0o640))
    successful = []
    failed = False
    for path, public, mode in targets:
        try:
            payload = public_report(report.to_json()) if public else report.to_json()
            if payload is not None:
                payload["invocation_id"] = validated_invocation_id(report.invocation_id)
                atomic_json(path, payload, mode=mode)
                successful.append((path, public, mode))
        except OSError:
            failed = True
            # No error body, path or private exception enters the report. Other
            # destinations/providers still run; CLI exposes publication failure.
            if not any(s.name == "Status publication" for s in report.steps):
                report.steps.append(StepResult("Status publication", "failed", "status_write_failed"))
    if failed:
        # Reconcile surviving destinations with a failure discovered after an
        # earlier successful write. Never leave those destinations claiming ok.
        for path, public, mode in successful:
            try:
                payload = public_report(report.to_json()) if public else report.to_json()
                if payload is not None:
                    payload["invocation_id"] = validated_invocation_id(report.invocation_id)
                    atomic_json(path, payload, mode=mode)
            except OSError:
                pass


def read_last_sync(inbox: Path | None = None) -> dict[str, Any] | None:
    path = (inbox or settings.resolved_sync_status_dir()) / "last-sync.json"
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None

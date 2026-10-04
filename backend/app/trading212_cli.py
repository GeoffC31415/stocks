"""Fixed Trading 212-only worker; no browser fetches, inbox imports or migrations."""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import os
from dataclasses import asdict

from app.config import settings
from app.database import SessionLocal
from app.services.sync_control import SyncBusy, file_lock, validated_invocation_id
from app.services.sync_freshness import update_freshness
from app.services.sync_runner import RunReport, StepResult, _trading212_step, publish_report


async def run() -> int:
    inbox = settings.resolved_sync_inbox()
    report = RunReport(started_at=dt.datetime.now(dt.UTC).isoformat(), invocation_id=validated_invocation_id(os.environ.get("INVOCATION_ID")))
    try:
        # Same stable inode as the daily worker: no concurrent provider requests.
        with file_lock(inbox / "sync-run.lock"):
            status_inbox = inbox / "trading212"
            publish_report(status_inbox, report)
            try:
                async with SessionLocal() as session:
                    async with asyncio.timeout(240):
                        step = await _trading212_step(session, invocation_id=report.invocation_id)
                        if step.status == "skipped":
                            step = StepResult("Trading 212", "failed", "credentials_unavailable")
                        report.steps.append(step)
            except BaseException as exc:
                report.steps.append(StepResult("Trading 212", "failed", "interrupted"))
                code = "sync_timeout" if isinstance(exc, TimeoutError) else "interrupted"
                logging.getLogger("app.services.sync_runner").error("Trading 212 sync failed code=%s endpoint=sync phase=unknown", code)
                raise
            finally:
                report.finished_at = dt.datetime.now(dt.UTC).isoformat()
                for step in report.steps:
                    report.freshness = update_freshness(report.freshness, asdict(step), report.started_at)
                publish_report(status_inbox, report)
            return 0 if report.outcome == "complete" else 1
    except SyncBusy:
        logging.getLogger("app.services.sync_runner").error("Trading 212 sync unavailable code=sync_busy")
        return 1


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        result = asyncio.run(run())
    except Exception:
        # No traceback or arbitrary exception string reaches the journal.
        logging.getLogger("app.services.sync_runner").error("Trading 212 worker failed code=unexpected_error")
        result = 1
    raise SystemExit(result)


if __name__ == "__main__":
    main()

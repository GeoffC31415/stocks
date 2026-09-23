"""Command-line sync of every account.

make sync                      # fetch HL + Barclays, import inbox, Trading 212
make sync ARGS="--no-fetch"    # import inbox + Trading 212 only
python -m app.sync_cli --include-downloads --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from app.database import SessionLocal, init_db
from app.services.sync_runner import run_sync_all


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sync every portfolio account")
    p.add_argument("--no-fetch", action="store_true", help="skip browser downloads")
    p.add_argument("--only", choices=("hl", "barclays"), action="append", help="limit fetchers")
    p.add_argument("--no-trading212", action="store_true")
    p.add_argument(
        "--include-downloads",
        action="store_true",
        help="also import broker exports found in ~/Downloads (read-only there)",
    )
    p.add_argument("--dry-run", action="store_true", help="classify only; no downloads or writes")
    p.add_argument("--headed", action="store_true", help="show the browser")
    p.add_argument("--json", action="store_true", help="print the report as JSON")
    return p.parse_args()


def _fetchers(args: argparse.Namespace) -> list:
    if args.no_fetch:
        return []
    from app.fetchers import hl

    wanted = set(args.only or ("hl", "barclays"))
    out = []
    if "hl" in wanted:
        out.append(("Hargreaves Lansdown", lambda inbox: hl.fetch(inbox, headless=not args.headed)))
    return out


def _session_steps(args: argparse.Namespace) -> list:
    if args.no_fetch or "barclays" not in set(args.only or ("hl", "barclays")):
        return []
    from app.fetchers import barclays

    return [("Barclays", lambda session: barclays.sync(session, headless=not args.headed))]


async def _run(args: argparse.Namespace) -> int:
    await init_db()
    extra = [Path.home() / "Downloads"] if args.include_downloads else []
    async with SessionLocal() as session:
        report = await run_sync_all(
            session,
            fetchers=_fetchers(args),
            session_steps=_session_steps(args),
            include_trading212=not args.no_trading212,
            extra_sources=extra,
            dry_run=args.dry_run,
        )
    if args.json:
        print(json.dumps(report.to_json(), indent=2))
    else:
        print("\n".join(report.summary_lines()))
    # Non-zero only when nothing at all refreshed, so a timer can alert.
    refreshed = any(s.status in {"ok", "unchanged"} for s in report.steps)
    return 0 if report.ok or refreshed else 1


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(asyncio.run(_run(_parse())))


if __name__ == "__main__":
    main()

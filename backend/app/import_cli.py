from __future__ import annotations

import argparse
import asyncio
import datetime as dt
from pathlib import Path

from app.database import SessionLocal, init_db
from app.services.import_service import DuplicateImportError, import_barclays_xls, import_hl_holdings_csv


def _file_metadata_as_of_date(path: Path) -> dt.date:
    st = path.stat()
    ts = getattr(st, "st_birthtime", None)
    if ts is None:
        ts = st.st_mtime
    return dt.date.fromtimestamp(ts)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a portfolio snapshot")
    parser.add_argument("file_path", type=Path, help="Path to snapshot file")
    parser.add_argument(
        "--source",
        choices=("barclays", "hl"),
        default="barclays",
        help="Broker/export source",
    )
    parser.add_argument("--as-of-date", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--force", action="store_true", help="Allow duplicate file hash import")
    return parser.parse_args()


async def _run() -> None:
    args = _parse_args()
    if not args.file_path.exists():
        raise SystemExit(f"File not found: {args.file_path}")
    expected_suffix = ".csv" if args.source == "hl" else ".xls"
    if args.file_path.suffix.lower() != expected_suffix:
        raise SystemExit(f"Only {expected_suffix} files are supported for {args.source} import.")

    as_of_date = None
    if args.as_of_date:
        as_of_date = dt.date.fromisoformat(args.as_of_date)

    file_metadata_as_of = None if as_of_date else _file_metadata_as_of_date(args.file_path)

    await init_db()
    file_bytes = args.file_path.read_bytes()
    async with SessionLocal() as session:
        try:
            if args.source == "hl":
                batch, summary = await import_hl_holdings_csv(
                    session,
                    file_bytes=file_bytes,
                    filename=args.file_path.name,
                    as_of_date=as_of_date,
                    file_metadata_as_of=file_metadata_as_of,
                    force=args.force,
                )
            else:
                batch, summary = await import_barclays_xls(
                    session,
                    file_bytes=file_bytes,
                    filename=args.file_path.name,
                    as_of_date=as_of_date,
                    file_metadata_as_of=file_metadata_as_of,
                    force=args.force,
                )
        except DuplicateImportError as exc:
            raise SystemExit(f"Duplicate file hash. Existing batch: {exc.batch_id}") from exc

    print(f"Imported batch #{batch.id} for {batch.as_of_date.isoformat()}")
    print(
        f"Rows={summary.get('row_count', 0)} "
        f"new={len(summary.get('new_instrument_ids', []))} "
        f"changed={len(summary.get('changed', []))} "
        f"closed={len(summary.get('closed', []))}"
    )


if __name__ == "__main__":
    asyncio.run(_run())

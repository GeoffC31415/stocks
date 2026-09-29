"""Explicit offline operator closure review. Never reads broker credentials."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
from pathlib import Path

from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services.closure_review import review_closure_observation
from app.services.sync_control import file_lock


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Review one staged Trading 212 closure observation offline"
    )
    parser.add_argument(
        "--database", type=Path, required=True, help="explicit existing SQLite copy (no default)"
    )
    parser.add_argument(
        "--review", type=Path, required=True, help="private reviewed JSON observation"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="commit exactly this reviewed observation; default rolls back",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> dict:
    database = args.database.resolve(strict=True)
    if not database.is_file():
        raise ValueError("Explicit existing SQLite database required.")
    review = json.loads(args.review.read_text())
    required = {
        "account_name",
        "expected_batch_id",
        "expected_batch_sha256",
        "observation_sha256",
        "identifiers",
        "positions",
        "account_summary",
        "observed_at",
    }
    if not isinstance(review, dict) or set(review) != required:
        raise ValueError("Invalid closure review manifest fields.")
    observed = dt.datetime.fromisoformat(review["observed_at"])
    if observed.tzinfo is None or observed > dt.datetime.now(dt.UTC):
        raise ValueError("Closure observation requires a nonfuture timezone-aware timestamp.")
    if (
        not isinstance(review["identifiers"], list)
        or any(not isinstance(value, str) for value in review["identifiers"])
        or len(set(review["identifiers"])) != len(review["identifiers"])
        or not isinstance(review["positions"], list)
        or any(not isinstance(row, dict) for row in review["positions"])
        or not isinstance(review["account_summary"], dict)
    ):
        raise ValueError("Invalid staged closure observation.")
    engine = create_async_engine(URL.create("sqlite+aiosqlite", database=str(database)))
    try:
        # SQLite BEGIN IMMEDIATE serializes scope validation and snapshot mutation
        # with other writers; no stale review can pass between those operations.
        with file_lock(database.with_suffix(database.suffix + ".closure-review.lock")):
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                from sqlalchemy import text

                await session.execute(text("BEGIN IMMEDIATE"))
                return await review_closure_observation(
                    session,
                    account_name=review["account_name"],
                    expected_batch_id=review["expected_batch_id"],
                    expected_batch_sha256=review["expected_batch_sha256"],
                    observation_sha256=review["observation_sha256"],
                    identifiers=frozenset(review["identifiers"]),
                    positions=review["positions"],
                    account_summary=review["account_summary"],
                    apply=args.apply,
                    observation_date=observed.astimezone(dt.UTC).date(),
                )
    finally:
        await engine.dispose()


def main() -> None:
    try:
        result = asyncio.run(run(parse_args()))
    except (ValueError, OSError):
        raise SystemExit(
            "Closure review rejected; verify private manifest and latest account observation."
        ) from None
    print(json.dumps(result))


if __name__ == "__main__":
    main()

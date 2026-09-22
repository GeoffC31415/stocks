"""Private setup and consistent SQLite backups; never installs or starts services."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import Settings
from app.security import hash_password, validate_public_settings


def configure(
    output: Path, origin: str, username: str, password: str, database: Path, dist: Path
) -> None:
    """Create once, never echo credentials or put the password on a command line."""
    if len(password) < 16 or len(password.encode("utf-8")) > 1024:
        raise ValueError(
            "Use a unique password of at least 16 characters (at most 1024 UTF-8 bytes)"
        )
    config = Settings(
        _env_file=None,
        deployment_mode="public",
        public_origin=origin,
        auth_username=username,
        auth_password_hash=hash_password(password),
    )
    validate_public_settings(config)
    values = {
        "PORTFOLIO_DEPLOYMENT_MODE": "public",
        "PORTFOLIO_PUBLIC_ORIGIN": origin,
        "PORTFOLIO_AUTH_USERNAME": username,
        "PORTFOLIO_AUTH_PASSWORD_HASH": config.auth_password_hash.get_secret_value(),
        "PORTFOLIO_DATABASE_URL": f"sqlite+aiosqlite:///{database.resolve()}",
        "PORTFOLIO_FRONTEND_DIST": str(dist.resolve()),
    }
    # dotenv and systemd EnvironmentFile both accept these quoted values.
    # Avoid dotenv ${...} interpolation or multiline control characters in paths.
    if any(
        "$" in value or any(ord(c) < 32 for c in value)
        for key, value in values.items()
        if key != "PORTFOLIO_AUTH_PASSWORD_HASH"
    ):
        raise ValueError("Configuration values contain unsupported characters")
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        for key, value in values.items():
            stream.write(f"{key}={json.dumps(value, ensure_ascii=False)}\n")


def backup(source: Path, destination: Path) -> None:
    """Online SQLite snapshot, validated before success; refuse missing/overwrite."""
    import sqlite3
    from contextlib import closing

    if not source.is_file():
        raise FileNotFoundError("Source database does not exist")
    # Reserve the destination before connecting; do not clobber or follow symlinks.
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    try:
        with (
            closing(
                sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
            ) as original,
            closing(sqlite3.connect(destination)) as copied,
        ):
            original.backup(copied)
            if copied.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise RuntimeError("Backup failed SQLite integrity validation")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    setup = sub.add_parser(
        "configure", help="Create a private public-mode environment file"
    )
    setup.add_argument("--output", type=Path, required=True)
    setup.add_argument(
        "--origin", required=True, help="Exact HTTPS origin, no trailing slash"
    )
    setup.add_argument("--username", required=True)
    setup.add_argument("--database", type=Path, required=True)
    setup.add_argument("--dist", type=Path, required=True)
    snapshot = sub.add_parser(
        "backup", help="Create and validate a private SQLite snapshot"
    )
    snapshot.add_argument("--source", type=Path, required=True)
    snapshot.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "backup":
        backup(args.source, args.output)
        print("Private SQLite snapshot created; integrity_check passed.")
        return
    if not sys.stdin.isatty():
        parser.error("Run configure in an interactive terminal; never pipe a password")
    password = getpass.getpass("Unique website password (16+ characters): ")
    if password != getpass.getpass("Confirm password: "):
        parser.error("Passwords do not match")
    configure(
        args.output, args.origin, args.username, password, args.database, args.dist
    )
    print("Private configuration created. No services started.")


if __name__ == "__main__":
    main()

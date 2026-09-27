"""Local operator recovery only. Does not import settings, dotenv or portfolio DB.

Run as the web service identity with an explicit existing auth database. Tokens
are written exclusively to a private file, never stdout or command arguments.
"""

import argparse
import sys
from pathlib import Path

from app.passkeys import PasskeyStore


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local passkey session revocation and recovery")
    parser.add_argument(
        "--database", required=True, type=Path, help="Absolute existing auth database"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("revoke-all", help="Invalidate sessions and outstanding ceremonies")
    recover = commands.add_parser(
        "recover", help="Disable old keys and issue one-use enrollment token"
    )
    recover.add_argument(
        "--output", required=True, type=Path, help="New absolute private token file"
    )
    recover.add_argument("--ttl", type=int, default=600, help="Token lifetime, 60–900 seconds")
    args = parser.parse_args(argv)
    try:
        if not args.database.is_absolute() or not args.database.is_file():
            raise ValueError("Explicit existing database required")
        # These operations never generate or verify a WebAuthn response and do
        # not need a relying-party configuration. No application config imports.
        store = PasskeyStore(args.database, rp_id="", origin="")
        if args.command == "revoke-all":
            store.admin_revoke_all()
            print("All sessions and pending ceremonies revoked.")
        else:
            store.issue_recovery(args.output, ttl=args.ttl)
            print("Recovery token written privately. Existing sessions revoked; old keys disabled.")
    except (OSError, ValueError):
        print(
            "Auth operation refused: check database, private paths and unused output file.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

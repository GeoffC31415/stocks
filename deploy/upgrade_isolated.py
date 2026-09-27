"""Safely activate a new immutable release in the isolated layout."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import stat
import tempfile
from pathlib import Path

from broker_isolation import (
    CONFIG_FILES,
    MigrationError,
    System,
    controlled,
    digest,
    evidence,
    exclusive_write,
    host_preflight,
    publish_transition,
    replace_bytes,
    safe_path,
    switch_release,
    transition_lock,
)

ROOT = Path("/")
MARKER = ROOT / "etc/stocks/isolation.json"


def validate_release(release: Path, previous: Path) -> None:
    host_preflight(release, previous)
    safe_path(release)
    if not (release / "frontend/dist/index.html").is_file():
        raise MigrationError("Release frontend is missing.")
    caddy = release / "bin/caddy"
    controlled(caddy, ROOT)
    if not caddy.is_file() or not os.access(caddy, os.X_OK):
        raise MigrationError("Release proxy executable missing or not executable.")
    for name in ("stocks.service", "stocks-sync.service", "stocks-sync.timer"):
        path = release / "deploy" / name
        controlled(path, ROOT)
        if not path.is_file():
            raise MigrationError("Release unit template is missing.")


def current_candidate(previous: Path) -> tuple[dict, dict]:
    marker = json.loads(MARKER.read_text())
    bundle = Path(marker["bundle"])
    manifest = evidence(ROOT, bundle)
    candidate = json.loads((bundle / "transition.json").read_text())
    if (manifest["release"] != str(previous) or candidate.get("state") != "verified_candidate"
            or candidate.get("phase") != "activation"):
        raise MigrationError("Current isolation candidate is not verified.")
    return manifest, candidate


def prepare_bundle(release: Path, previous: Path, manifest: dict) -> Path:
    bundle = Path(tempfile.mkdtemp(prefix="isolation-", dir="/var/backups/stocks"))
    os.chmod(bundle, 0o700)
    config_dir = bundle / "config"
    config_dir.mkdir(mode=0o700)
    hashes = {}
    for relative in CONFIG_FILES:
        source = ROOT / relative
        target = config_dir / Path(relative).name
        exclusive_write(target, source.read_bytes())
        hashes[relative] = digest(source.read_bytes())
    exclusive_write(bundle / "state-complete", b"1\n")
    new_manifest = {
        "version": 2,
        "transition_id": os.urandom(16).hex(),
        "bundle": str(bundle),
        "previous": str(previous),
        "release": str(release),
        "services": manifest["services"],
        "config_sha256": hashes,
    }
    exclusive_write(bundle / "manifest.json", json.dumps(new_manifest).encode())
    exclusive_write(bundle / "previous-marker.json", MARKER.read_bytes())
    replace_bytes(MARKER, json.dumps({
        "version": 2, "transition_id": new_manifest["transition_id"], "bundle": str(bundle)
    }).encode())
    return bundle


def activate(release: Path, previous: Path, system: System) -> Path:
    with transition_lock(ROOT):
        validate_release(release, previous)
        old_manifest, old_candidate = current_candidate(previous)
        bundle = prepare_bundle(release, previous, old_manifest)
        manifest = json.loads((bundle / "manifest.json").read_text())
        old_marker = bundle / "previous-marker.json"
        publish_transition(ROOT, bundle, manifest, "activation", "preparing")
        try:
            system.stop()
            switch_release(ROOT, release)
            system.reload()
            system.start_web()
            system.health()
            identity = system.readiness(manifest["services"])
            publish_transition(ROOT, bundle, manifest, "activation", "verified_candidate", identity)
            exclusive_write(bundle / "supersedes.json", json.dumps({
                "bundle": old_manifest["bundle"], "transition_id": old_manifest["transition_id"]
            }).encode())
            return bundle
        except BaseException:
            try:
                system.stop()
                switch_release(ROOT, previous)
                exclusive_write(MARKER, old_marker.read_bytes())
                system.reload()
                system.start_web()
                system.health()
            except BaseException as error:
                raise MigrationError("Upgrade failed and rollback could not be confirmed; inspect preserved evidence.") from error
            raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "activate"))
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--expect-current", type=Path, required=True)
    parser.add_argument("--confirm", choices=("UPGRADE",))
    args = parser.parse_args(argv)
    try:
        host_preflight(args.release, args.expect_current)
        validate_release(args.release, args.expect_current)
        current_candidate(args.expect_current)
        if args.action == "preflight":
            print("Preflight passed; no services or markers changed.")
            return 0
        if os.geteuid() != 0 or socket.gethostname() != "geoff-Surface-Pro-4" or args.confirm != "UPGRADE":
            raise MigrationError("Upgrade requires root on the approved host and --confirm UPGRADE.")
        bundle = activate(args.release, args.expect_current, System())
        print(f"Upgrade activated; private recovery bundle: {bundle}")
        return 0
    except (MigrationError, OSError, ValueError, KeyError):
        print("STOP: Upgrade refused or incomplete; inspect private evidence and do not retry blindly.", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

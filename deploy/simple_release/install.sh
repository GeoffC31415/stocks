#!/bin/bash
# One-time, separately reviewed/pinned administrator installation. No sudoers.
set -euo pipefail
if [[ $EUID -ne 0 ]]; then printf '%s\n' 'administrator-only' >&2; exit 1; fi
if [[ $# -ne 3 ]]; then printf '%s\n' 'usage: install.sh SOURCE_DIRECTORY CONTROLLER_SHA256 PROBE_SHA256' >&2; exit 1; fi
exec /usr/bin/python3 -I -B - "$@" <<'PY'
import hashlib
import os
from pathlib import Path
import re
import stat
import sys

source, controller_hash, probe_hash = sys.argv[1:]
# Read once into memory, bind trusted argv digests, then install those exact bytes.
files = {}
rootfd = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
try:
    for name, expected in [('stocks_release.py', controller_hash), ('runtime_probe.py', probe_hash)]:
        if not re.fullmatch('[0-9a-f]{64}', expected):
            raise SystemExit('invalid-pin')
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=rootfd)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size < 128000:
                raise SystemExit('source-type-or-size')
            data = stream.read(128000)
        if hashlib.sha256(data).hexdigest() != expected:
            raise SystemExit('source-pin-mismatch')
        files[name] = data
finally:
    os.close(rootfd)

paths = [Path('/usr/local/lib/stocks-release'), Path('/var/lib/stocks-release'),
         Path('/opt/stocks/simple-releases')]
link = Path('/usr/local/sbin/stocks-release')
if any(p.exists() or p.is_symlink() for p in [*paths, link]):
    raise SystemExit('already-installed-or-partial: inspect, do not overwrite')
for path in [*paths, link]:
    for parent in path.parents:
        info = parent.lstat()
        if info.st_uid != 0 or info.st_mode & 0o022 or not stat.S_ISDIR(info.st_mode):
            raise SystemExit('unsafe-install-parent')
os.umask(0o077)
for path, mode in zip(paths, [0o755, 0o711, 0o755]):
    path.mkdir(mode=mode)
    path.chmod(mode)
for name, data in files.items():
    path = paths[0] / name
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fchmod(stream.fileno(), 0o755 if name == 'stocks_release.py' else 0o644)
        os.fsync(stream.fileno())
rehearsal = paths[1] / 'rehearsal'
rehearsal.mkdir(mode=0o711)
rehearsal.chmod(0o711)
link.symlink_to(paths[0] / 'stocks_release.py')
for directory in [*paths, link.parent]:
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    os.fsync(fd)
    os.close(fd)
print('installed stable stocks-release; no units, credentials, databases or sudo policy changed')
PY

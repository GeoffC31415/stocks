"""Single-owner WebAuthn state, deliberately independent of app/portfolio configuration.

Only public credential material and hashes of bearer secrets are persisted. All
state transitions use SQLite write transactions; ceremonies are committed consumed
before cryptographic verification, including unsuccessful verification.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import stat
import time
from contextlib import contextmanager
from pathlib import Path

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)


class AuthError(Exception):
    def __init__(self, status=401, detail="Authentication failed"):
        self.status = status
        self.detail = detail
        super().__init__(detail)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def private_file(path: Path) -> None:
    """Create exclusively, reject links and permissive existing files/directories."""
    if not path.is_absolute():
        raise ValueError("Auth database requires an absolute path")
    if any(part.is_symlink() for part in [path, *path.parents]):
        raise ValueError("Auth path must not contain symlinks")
    parent = path.parent.stat()
    if parent.st_uid != os.getuid() or parent.st_mode & 0o022:
        raise ValueError("Auth directory must be owned and not writable by others")
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        pass
    else:
        os.close(fd)
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o777 != 0o600
        or info.st_nlink != 1
    ):
        raise ValueError("Auth file must be a private owned regular file")
    for suffix in ("-journal", "-wal", "-shm"):
        sidecar = Path(str(path) + suffix)
        if sidecar.is_symlink():
            raise ValueError("Unsafe auth database sidecar")


class PasskeyStore:
    CEREMONY_TTL = 300
    RECENT_SECONDS = 300

    def __init__(
        self,
        path: Path,
        *,
        rp_id: str,
        origin: str,
        idle_seconds=86400,
        absolute_seconds=604800,
        clock=time.time,
    ):
        self.path = Path(path)
        self.rp_id = rp_id
        self.origin = origin
        self.idle_seconds = idle_seconds
        self.absolute_seconds = absolute_seconds
        self.clock = clock
        self._initialized = False
        private_file(self.path)
        with self.connection() as db:
            tables = list(db.execute("SELECT name FROM sqlite_master WHERE type='table'"))
            if tables and db.execute("PRAGMA application_id").fetchone()[0] != 0x53544B41:
                raise ValueError("Not a Portfolio authentication database")
            db.execute("PRAGMA application_id=0x53544B41")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS credentials (
                    id TEXT PRIMARY KEY, public_key BLOB NOT NULL, sign_count INTEGER NOT NULL,
                    device_type TEXT NOT NULL, backed_up INTEGER NOT NULL, label TEXT NOT NULL,
                    created_at REAL NOT NULL, last_used_at REAL);
                CREATE TABLE IF NOT EXISTS ceremonies (
                    id TEXT PRIMARY KEY, browser TEXT NOT NULL, purpose TEXT NOT NULL,
                    challenge BLOB NOT NULL, label TEXT NOT NULL, binding TEXT,
                    epoch TEXT NOT NULL, expires_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    hash TEXT PRIMARY KEY, credential_id TEXT NOT NULL,
                    created_at REAL NOT NULL, last_activity REAL NOT NULL,
                    recent_auth REAL NOT NULL, expires_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS recovery (
                    hash TEXT PRIMARY KEY, expires_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts (peer TEXT NOT NULL, browser TEXT NOT NULL,
                    created_at REAL NOT NULL);
            """)
            db.execute(
                "INSERT OR IGNORE INTO meta VALUES ('owner', ?)",
                (bytes_to_base64url(secrets.token_bytes(32)),),
            )
            db.execute("INSERT OR IGNORE INTO meta VALUES ('epoch', '0')")
        self._initialized = True

    @contextmanager
    def connection(self):
        private_file(self.path)
        db = sqlite3.connect(self.path, timeout=2, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA trusted_schema=OFF")
            db.execute("BEGIN IMMEDIATE")
            if self._initialized:
                self._cleanup(db)
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def meta(db, key):
        row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def credentials(self):
        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT id,label,created_at,last_used_at FROM credentials ORDER BY created_at,id"
                )
            ]

    def _issue(self, db, browser, purpose, options, label="", binding=None):
        if (
            db.execute("SELECT count(*) FROM ceremonies").fetchone()[0] >= 128
            or db.execute(
                "SELECT count(*) FROM ceremonies WHERE browser=?", (digest(browser),)
            ).fetchone()[0]
            >= 5
        ):
            raise AuthError(429, "Too many authentication attempts")
        ceremony_id = secrets.token_urlsafe(32)
        db.execute(
            "INSERT INTO ceremonies VALUES (?,?,?,?,?,?,?,?)",
            (
                ceremony_id,
                digest(browser),
                purpose,
                base64url_to_bytes(options["challenge"]),
                label,
                binding,
                self.meta(db, "epoch"),
                self.clock() + self.CEREMONY_TTL,
            ),
        )
        return {"ceremony_id": ceremony_id, "options": options}

    def _consume(self, ceremony_id, browser, purposes):
        with self.connection() as db:
            row = db.execute("SELECT * FROM ceremonies WHERE id=?", (ceremony_id,)).fetchone()
            db.execute("DELETE FROM ceremonies WHERE id=?", (ceremony_id,))
        if (
            not row
            or row["purpose"] not in purposes
            or row["expires_at"] <= self.clock()
            or not hmac.compare_digest(row["browser"], digest(browser))
        ):
            raise AuthError()
        return row

    def registration_options(self, browser, *, label, bootstrap=False, session_token=None):
        with self.connection() as db:
            self._not_recovering(db)
            existing = list(db.execute("SELECT id FROM credentials"))
            purpose, binding = "bootstrap", None
            if existing or not bootstrap:
                self._recent(db, session_token)
                purpose, binding = "add", digest(session_token)
            if len(existing) >= 16:
                raise AuthError(409, "Credential limit reached")
            options = self._registration_options(db, existing)
            return self._issue(db, browser, purpose, options, label, binding)

    def _registration_options(self, db, existing=()):
        return json.loads(
            options_to_json(
                generate_registration_options(
                    rp_id=self.rp_id,
                    rp_name="Portfolio",
                    user_name="owner",
                    user_id=base64url_to_bytes(self.meta(db, "owner")),
                    exclude_credentials=[
                        PublicKeyCredentialDescriptor(id=base64url_to_bytes(row[0]))
                        for row in existing
                    ],
                    authenticator_selection=AuthenticatorSelectionCriteria(
                        resident_key=ResidentKeyRequirement.REQUIRED,
                        require_resident_key=True,
                        user_verification=UserVerificationRequirement.REQUIRED,
                    ),
                    timeout=self.CEREMONY_TTL * 1000,
                )
            )
        )

    def registration_verify(self, ceremony_id, browser, credential, *, old_token=None):
        ceremony = self._consume(ceremony_id, browser, {"bootstrap", "add", "recovery"})
        try:
            verified = verify_registration_response(
                credential=credential,
                expected_challenge=ceremony["challenge"],
                expected_rp_id=self.rp_id,
                expected_origin=self.origin,
                require_user_presence=True,
                require_user_verification=True,
            )
        except Exception:
            raise AuthError() from None
        ident = bytes_to_base64url(verified.credential_id)
        with self.connection() as db:
            if ceremony["purpose"] != "recovery":
                self._not_recovering(db)
                if db.execute("SELECT count(*) FROM credentials").fetchone()[0] >= 16:
                    raise AuthError(409, "Credential limit reached")
            if ceremony["purpose"] == "add":
                self._recent(db, old_token)
                if not hmac.compare_digest(ceremony["binding"], digest(old_token)):
                    raise AuthError(403, "Recent passkey authentication required")
            if (
                ceremony["epoch"] != self.meta(db, "epoch")
                or (
                    ceremony["purpose"] == "bootstrap"
                    and db.execute("SELECT 1 FROM credentials").fetchone()
                )
                or db.execute("SELECT 1 FROM credentials WHERE id=?", (ident,)).fetchone()
            ):
                raise AuthError(409, "Credential conflict")
            if ceremony["purpose"] == "recovery":
                if self.meta(db, "recovery_pending") != "1":
                    raise AuthError()
                db.execute("DELETE FROM sessions")
                db.execute("DELETE FROM credentials")
                db.execute("DELETE FROM ceremonies")
                db.execute("DELETE FROM recovery")
                db.execute("DELETE FROM meta WHERE key='recovery_pending'")
                self._advance_epoch(db)
            db.execute(
                "INSERT INTO credentials VALUES (?,?,?,?,?,?,?,NULL)",
                (
                    ident,
                    verified.credential_public_key,
                    verified.sign_count,
                    verified.credential_device_type.value,
                    verified.credential_backed_up,
                    ceremony["label"],
                    self.clock(),
                ),
            )
            return self._new_session(db, ident, old_token)

    def login_options(self, browser):
        with self.connection() as db:
            self._not_recovering(db)
            options = json.loads(
                options_to_json(
                    generate_authentication_options(
                        rp_id=self.rp_id,
                        user_verification=UserVerificationRequirement.REQUIRED,
                        timeout=self.CEREMONY_TTL * 1000,
                    )
                )
            )
            return self._issue(db, browser, "login", options)

    def login_verify(self, ceremony_id, browser, credential, *, old_token=None):
        ceremony = self._consume(ceremony_id, browser, {"login"})
        with self.connection() as db:
            self._not_recovering(db)
            try:
                ident = bytes_to_base64url(base64url_to_bytes(credential["id"]))
                row = db.execute("SELECT * FROM credentials WHERE id=?", (ident,)).fetchone()
                handle = base64url_to_bytes(credential["response"]["userHandle"])
                if not row or not hmac.compare_digest(
                    handle, base64url_to_bytes(self.meta(db, "owner"))
                ):
                    raise AuthError()
                verified = verify_authentication_response(
                    credential=credential,
                    expected_challenge=ceremony["challenge"],
                    expected_rp_id=self.rp_id,
                    expected_origin=self.origin,
                    credential_public_key=row["public_key"],
                    credential_current_sign_count=row["sign_count"],
                    require_user_verification=True,
                )
            except Exception:
                raise AuthError() from None
            if ceremony["epoch"] != self.meta(db, "epoch"):
                raise AuthError()
            db.execute(
                "UPDATE credentials SET sign_count=?,backed_up=?,last_used_at=? WHERE id=?",
                (verified.new_sign_count, verified.credential_backed_up, self.clock(), ident),
            )
            return self._new_session(db, ident, old_token)

    def _new_session(self, db, ident, old_token):
        if old_token:
            db.execute("DELETE FROM sessions WHERE hash=?", (digest(old_token),))
        db.execute(
            "DELETE FROM sessions WHERE hash IN (SELECT hash FROM sessions ORDER BY created_at DESC,hash DESC LIMIT -1 OFFSET 31)"
        )
        token = secrets.token_urlsafe(32)
        now = self.clock()
        db.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?)",
            (digest(token), ident, now, now, now, now + self.absolute_seconds),
        )
        return token, self._session(db, token)

    def _session(self, db, token, *, touch=False):
        row = db.execute("SELECT * FROM sessions WHERE hash=?", (digest(token),)).fetchone()
        now = self.clock()
        if not row or row["expires_at"] <= now or row["last_activity"] + self.idle_seconds <= now:
            return None
        if touch:
            db.execute("UPDATE sessions SET last_activity=? WHERE hash=?", (now, digest(token)))
        return dict(row)

    def session(self, token):
        if not token or len(token) > 128:
            return None
        with self.connection() as db:
            return self._session(db, token, touch=True)

    def _recent(self, db, token):
        session = self._session(db, token) if token else None
        if not session or session["recent_auth"] + self.RECENT_SECONDS <= self.clock():
            raise AuthError(403, "Recent passkey authentication required")
        return session

    def is_recent(self, token):
        with self.connection() as db:
            try:
                self._recent(db, token)
                return True
            except AuthError:
                return False

    def revoke_current(self, token):
        with self.connection() as db:
            db.execute("DELETE FROM sessions WHERE hash=?", (digest(token or ""),))

    def revoke_all(self, token):
        with self.connection() as db:
            self._recent(db, token)
            db.execute("DELETE FROM sessions")

    def delete_credential(self, ident, token):
        with self.connection() as db:
            self._recent(db, token)
            if not db.execute("SELECT 1 FROM credentials WHERE id=?", (ident,)).fetchone():
                raise AuthError(409, "Credential conflict")
            if db.execute("SELECT count(*) FROM credentials").fetchone()[0] <= 1:
                raise AuthError(409, "Cannot delete last credential")
            db.execute("DELETE FROM sessions WHERE credential_id=?", (ident,))
            db.execute("DELETE FROM credentials WHERE id=?", (ident,))

    @staticmethod
    def _advance_epoch(db):
        db.execute("UPDATE meta SET value=? WHERE key='epoch'", (secrets.token_hex(16),))

    def _not_recovering(self, db):
        if self.meta(db, "recovery_pending") == "1":
            raise AuthError()

    def admin_revoke_all(self):
        with self.connection() as db:
            db.execute("DELETE FROM sessions")
            db.execute("DELETE FROM ceremonies")
            self._advance_epoch(db)

    def issue_recovery(self, output: Path, *, ttl=600):
        if not 60 <= ttl <= 900:
            raise ValueError("Recovery lifetime must be 60 to 900 seconds")
        output = Path(output)
        if (
            not output.is_absolute()
            or any(p.is_symlink() for p in output.parents)
            or output.parent.stat().st_uid != os.getuid()
            or output.parent.stat().st_mode & 0o022
        ):
            raise ValueError("Recovery output requires an owned private directory")
        token = secrets.token_urlsafe(32)
        # Never overwrite a token or follow links. If DB commit fails the file is
        # unusable, not an accidentally published valid recovery credential.
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(token + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            with self.connection() as db:
                db.execute("DELETE FROM recovery")
                db.execute("DELETE FROM sessions")
                db.execute("DELETE FROM ceremonies")
                self._advance_epoch(db)
                db.execute("INSERT OR REPLACE INTO meta VALUES ('recovery_pending','1')")
                db.execute("INSERT INTO recovery VALUES (?,?)", (digest(token), self.clock() + ttl))
        except BaseException:
            output.unlink(missing_ok=True)
            raise

    def recovery_options(self, browser, token, *, label):
        with self.connection() as db:
            row = db.execute("SELECT * FROM recovery WHERE hash=?", (digest(token),)).fetchone()
            if not row or row["expires_at"] <= self.clock():
                raise AuthError()
            db.execute("DELETE FROM recovery WHERE hash=?", (digest(token),))
            return self._issue(db, browser, "recovery", self._registration_options(db), label)

    def _cleanup(self, db):
        now = self.clock()
        db.execute("DELETE FROM ceremonies WHERE expires_at<=?", (now,))
        db.execute("DELETE FROM recovery WHERE expires_at<=?", (now,))
        db.execute("DELETE FROM attempts WHERE created_at<=?", (now - 60,))
        db.execute(
            "DELETE FROM sessions WHERE expires_at<=? OR last_activity<=?",
            (now, now - self.idle_seconds),
        )

    def rate_limit(self, peer, browser):
        with self.connection() as db:
            peer, browser = digest(peer), digest(browser)
            if (
                db.execute("SELECT count(*) FROM attempts").fetchone()[0] >= 100
                or db.execute("SELECT count(*) FROM attempts WHERE peer=?", (peer,)).fetchone()[0]
                >= 20
                or db.execute(
                    "SELECT count(*) FROM attempts WHERE browser=?", (browser,)
                ).fetchone()[0]
                >= 20
            ):
                raise AuthError(429, "Too many authentication attempts")
            db.execute("INSERT INTO attempts VALUES (?,?,?)", (peer, browser, self.clock()))

"""Real synthetic authenticators; no network, private config or portfolio data."""

import base64
import hashlib
import json
import secrets
import sqlite3

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

ORIGIN = "https://solarpi.hopto.org:5000"
RP = "solarpi.hopto.org"


def enc(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def dec(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class Authenticator:
    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.id = secrets.token_bytes(32)

    def register(self, options, origin=ORIGIN, rp=RP, flags=0x45):
        self.handle = options["user"]["id"]
        public = self.key.public_key().public_numbers()
        cose = cbor2.dumps(
            {1: 2, 3: -7, -1: 1, -2: public.x.to_bytes(32, "big"), -3: public.y.to_bytes(32, "big")}
        )
        auth = (
            hashlib.sha256(rp.encode()).digest()
            + bytes([flags])
            + bytes(4)
            + bytes(16)
            + len(self.id).to_bytes(2, "big")
            + self.id
            + cose
        )
        client = json.dumps(
            {"type": "webauthn.create", "challenge": options["challenge"], "origin": origin}
        ).encode()
        return {
            "id": enc(self.id),
            "rawId": enc(self.id),
            "type": "public-key",
            "response": {
                "clientDataJSON": enc(client),
                "attestationObject": enc(
                    cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth})
                ),
            },
        }

    def assertion(self, options, origin=ORIGIN, rp=RP, flags=5, count=0):
        client = json.dumps(
            {"type": "webauthn.get", "challenge": options["challenge"], "origin": origin}
        ).encode()
        auth = hashlib.sha256(rp.encode()).digest() + bytes([flags]) + count.to_bytes(4, "big")
        signature = self.key.sign(auth + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
        return {
            "id": enc(self.id),
            "rawId": enc(self.id),
            "type": "public-key",
            "response": {
                "clientDataJSON": enc(client),
                "authenticatorData": enc(auth),
                "signature": enc(signature),
                "userHandle": self.handle,
            },
        }


@pytest.fixture
def store(tmp_path):
    from app.passkeys import PasskeyStore

    return PasskeyStore(tmp_path / "auth.sqlite3", rp_id=RP, origin=ORIGIN)


def enroll(store, browser="browser", key=None):
    key = key or Authenticator()
    issued = store.registration_options(browser, label="Test key", bootstrap=True)
    token, session = store.registration_verify(
        issued["ceremony_id"], browser, key.register(issued["options"])
    )
    return key, token, session


def test_real_registration_login_persist_and_rotate(tmp_path):
    assert hasattr(__import__("app", fromlist=["passkeys"]), "passkeys"), "Passkey store missing"
    from app.passkeys import PasskeyStore

    path = tmp_path / "auth.sqlite3"
    store = PasskeyStore(path, rp_id=RP, origin=ORIGIN)
    key, token, session = enroll(store)
    assert session["credential_id"] == enc(key.id)
    assert path.stat().st_mode & 0o777 == 0o600
    assert token.encode() not in path.read_bytes()
    assert store.session(token) is not None
    reopened = PasskeyStore(path, rp_id=RP, origin=ORIGIN)
    options = reopened.login_options("browser")
    assert options["options"]["userVerification"] == "required"
    token2, _ = reopened.login_verify(
        options["ceremony_id"], "browser", key.assertion(options["options"]), old_token=token
    )
    assert token2 != token
    assert reopened.session(token) is None
    assert reopened.session(token2) is not None
    assert reopened.credentials()[0]["label"] == "Test key"


def test_manage_credentials_requires_recent_session_and_preserves_last(store):
    from app.passkeys import AuthError

    first, token, _ = enroll(store)
    with pytest.raises(AuthError) as error:
        store.registration_options("browser", label="Untrusted", bootstrap=True)
    assert error.value.status == 403
    second = Authenticator()
    issued = store.registration_options("browser", label="Second", session_token=token)
    token2, _ = store.registration_verify(
        issued["ceremony_id"], "browser", second.register(issued["options"]), old_token=token
    )
    assert store.session(token) is None
    assert len(store.credentials()) == 2
    store.delete_credential(enc(first.id), token2)
    assert len(store.credentials()) == 1
    with pytest.raises(AuthError) as error:
        store.delete_credential(enc(second.id), token2)
    assert error.value.status == 409
    store.revoke_all(token2)
    assert store.session(token2) is None


def test_add_is_bound_to_session_and_recent_auth(store):
    from app.passkeys import AuthError

    _, token, _ = enroll(store)
    issued = store.registration_options("browser", label="Second", session_token=token)
    key = Authenticator()
    with pytest.raises(AuthError):
        store.registration_verify(issued["ceremony_id"], "browser", key.register(issued["options"]))
    issued = store.registration_options("browser", label="Second", session_token=token)
    now = store.clock()
    store.clock = lambda: now + 301
    with pytest.raises(AuthError) as error:
        store.registration_options("browser", label="Stale", session_token=token)
    assert error.value.status == 403
    assert store.session(token)  # Valid, but not recent.
    store.revoke_current(token)
    assert store.session(token) is None


def test_recovery_blocks_old_keys_and_replaces_only_after_verification(store, tmp_path):
    from app.passkeys import AuthError

    key, token, _ = enroll(store)
    pending = store.login_options("browser")
    path = tmp_path / "recovery-token"
    store.issue_recovery(path)
    assert path.stat().st_mode & 0o777 == 0o600
    recovery_token = path.read_text().strip()
    assert recovery_token.encode() not in store.path.read_bytes()
    assert store.session(token) is None
    with pytest.raises(AuthError):
        store.login_verify(pending["ceremony_id"], "browser", key.assertion(pending["options"]))
    with pytest.raises(AuthError):
        store.login_options("browser")
    assert len(store.credentials()) == 1  # No premature key destruction.
    issued = store.recovery_options("new-browser", recovery_token, label="Recovered")
    with pytest.raises(AuthError):
        store.recovery_options("other-browser", recovery_token, label="Replay")
    replacement = Authenticator()
    token2, _ = store.registration_verify(
        issued["ceremony_id"], "new-browser", replacement.register(issued["options"])
    )
    assert store.session(token2)
    assert [c["id"] for c in store.credentials()] == [enc(replacement.id)]
    assert store.credentials()[0]["label"] == "Recovered"
    issued = store.login_options("browser")
    with pytest.raises(AuthError):
        store.login_verify(issued["ceremony_id"], "browser", key.assertion(issued["options"]))


@pytest.mark.parametrize("change", ["origin", "rp", "uv", "up", "signature", "handle", "unknown"])
def test_assertion_rejects_invalid_cryptography_and_identity(store, change):
    from app.passkeys import AuthError

    key, _, _ = enroll(store)
    issued = store.login_options("browser")
    kwargs = {"origin": "https://evil.test"} if change == "origin" else {}
    if change == "rp":
        kwargs["rp"] = "evil.test"
    if change == "uv":
        kwargs["flags"] = 1
    if change == "up":
        kwargs["flags"] = 4
    payload = key.assertion(issued["options"], **kwargs)
    if change == "signature":
        payload["response"]["signature"] = enc(b"bad-signature")
    if change == "handle":
        payload["response"]["userHandle"] = enc(b"unknown-owner")
    if change == "unknown":
        payload["id"] = payload["rawId"] = enc(b"unknown-key")
    with pytest.raises(AuthError):
        store.login_verify(issued["ceremony_id"], "browser", payload)
    with pytest.raises(AuthError):  # Failed verification still consumes ceremony.
        store.login_verify(issued["ceremony_id"], "browser", key.assertion(issued["options"]))


@pytest.mark.parametrize("change", ["origin", "rp", "uv", "up", "browser", "expiry"])
def test_registration_rejects_invalid_ceremonies(store, change):
    from app.passkeys import AuthError

    issued = store.registration_options("browser", label="New", bootstrap=True)
    key = Authenticator()
    kwargs = {"origin": "https://evil.test"} if change == "origin" else {}
    if change == "rp":
        kwargs["rp"] = "evil.test"
    if change == "uv":
        kwargs["flags"] = 0x41
    if change == "up":
        kwargs["flags"] = 0x44
    payload = key.register(issued["options"], **kwargs)
    if change == "expiry":
        now = store.clock()
        store.clock = lambda: now + 301
    with pytest.raises(AuthError):
        store.registration_verify(
            issued["ceremony_id"], "wrong" if change == "browser" else "browser", payload
        )
    assert store.credentials() == []
    with pytest.raises(AuthError):
        store.registration_verify(issued["ceremony_id"], "browser", key.register(issued["options"]))


def test_duplicates_replays_and_purpose(store):
    from app.passkeys import AuthError

    key, token, _ = enroll(store)
    issued = store.registration_options("browser", label="Duplicate", session_token=token)
    with pytest.raises(AuthError) as error:
        store.registration_verify(
            issued["ceremony_id"], "browser", key.register(issued["options"]), old_token=token
        )
    assert error.value.status == 409
    issued = store.login_options("browser")
    with pytest.raises(AuthError):
        store.registration_verify(
            issued["ceremony_id"], "browser", key.assertion(issued["options"])
        )
    with pytest.raises(AuthError):
        store.login_verify(issued["ceremony_id"], "browser", key.assertion(issued["options"]))


def test_zero_synced_counters_allowed_and_nonzero_rollback_rejected(store):
    from app.passkeys import AuthError

    key, _, _ = enroll(store)
    for count in [0, 0, 1, 2]:
        issued = store.login_options("browser")
        store.login_verify(
            issued["ceremony_id"], "browser", key.assertion(issued["options"], count=count)
        )
    issued = store.login_options("browser")
    with pytest.raises(AuthError):
        store.login_verify(
            issued["ceremony_id"], "browser", key.assertion(issued["options"], count=1)
        )


@pytest.mark.parametrize("kind", ["idle", "absolute"])
def test_session_expiry(store, kind):
    _, token, session = enroll(store)
    now = store.clock()
    if kind == "idle":
        store.clock = lambda: now + 86401
    else:
        for day in range(1, 7):
            store.clock = lambda day=day: now + day * 86000
            assert store.session(token)
        store.clock = lambda: session["expires_at"]
    assert store.session(token) is None


@pytest.mark.parametrize("unsafe", ["symlink", "permissions", "hardlink", "sidecar"])
def test_unsafe_database_paths_rejected(tmp_path, unsafe):
    import os

    from app.passkeys import PasskeyStore

    target = tmp_path / "target"
    target.touch(mode=0o600)
    path = tmp_path / "auth.db"
    if unsafe == "symlink":
        path.symlink_to(target)
    if unsafe == "hardlink":
        os.link(target, path)
    if unsafe == "permissions":
        path.touch(mode=0o644)
    if unsafe == "sidecar":
        (tmp_path / "auth.db-journal").symlink_to(target)
    with pytest.raises(ValueError):
        PasskeyStore(path, rp_id=RP, origin=ORIGIN)


def test_bounded_ceremonies_and_persistent_rate_budget(store):
    from app.passkeys import AuthError, PasskeyStore

    for _ in range(5):
        store.login_options("browser")
    with pytest.raises(AuthError) as error:
        store.login_options("browser")
    assert error.value.status == 429
    now = store.clock()
    store.clock = lambda: now + 301
    store.login_options("browser")
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM ceremonies").fetchone()[0] == 1
    for _ in range(20):
        store.rate_limit("peer", "browser")
    with pytest.raises(AuthError) as error:
        PasskeyStore(store.path, rp_id=RP, origin=ORIGIN).rate_limit("peer", "different")
    assert error.value.status == 429


def test_credentials_sessions_are_bounded(store):
    from app.passkeys import AuthError

    key, token, _ = enroll(store)
    for index in range(15):
        issued = store.registration_options("browser", label=f"Key {index}", session_token=token)
        token, _ = store.registration_verify(
            issued["ceremony_id"],
            "browser",
            Authenticator().register(issued["options"]),
            old_token=token,
        )
    with pytest.raises(AuthError) as error:
        store.registration_options("browser", label="Too many", session_token=token)
    assert error.value.status == 409
    for _ in range(35):
        issued = store.login_options("browser")
        store.login_verify(issued["ceremony_id"], "browser", key.assertion(issued["options"]))
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 32


def test_cli_explicit_database_no_configuration_and_no_token_output(store, tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    _, token, _ = enroll(store)
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    command = [sys.executable, "-m", "app.auth_cli"]
    missing = subprocess.run(command + ["revoke-all"], env=env, capture_output=True, text=True)
    assert missing.returncode != 0
    revoked = subprocess.run(
        command + ["--database", str(store.path), "revoke-all"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert revoked.returncode == 0, revoked.stderr
    assert store.session(token) is None
    output = tmp_path / "token.txt"
    issued = subprocess.run(
        command + ["--database", str(store.path), "recover", "--output", str(output)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert issued.returncode == 0, issued.stderr
    assert output.read_text().strip() not in issued.stdout + issued.stderr
    again = subprocess.run(
        command + ["--database", str(store.path), "recover", "--output", str(output)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert again.returncode != 0
    code = "import app.auth_cli, sys; assert 'app.config' not in sys.modules; assert 'app.database' not in sys.modules; assert 'app.main' not in sys.modules"
    assert subprocess.run([sys.executable, "-c", code], env=env).returncode == 0


def test_refuses_non_auth_database_without_modification(tmp_path):
    from app.passkeys import PasskeyStore

    path = tmp_path / "portfolio-sentinel.db"
    path.touch(mode=0o600)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE portfolio (private TEXT)")
    original = path.read_bytes()
    with pytest.raises(ValueError):
        PasskeyStore(path, rp_id=RP, origin=ORIGIN)
    assert path.read_bytes() == original

"""Single-user web boundary. Hashes use scrypt$<16-byte hex salt>$<32-byte hex key>."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import ipaddress
import re
import secrets
from collections import deque
from time import monotonic
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

    from app.config import Settings


def validate_public_settings(config: Settings) -> None:
    """Fail before migrations, with no credential-bearing validation messages."""
    if config.deployment_mode != "public":
        return
    try:
        origin = config.public_origin or ""
        parsed = urlsplit(origin)
        hostname = parsed.hostname or ""
        if ":" in hostname:
            ipaddress.IPv6Address(hostname)
            host_valid = True
        else:
            host_valid = len(hostname) <= 253 and all(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in hostname.split(".")
            )
        username = config.auth_username.get_secret_value() if config.auth_username else ""
        encoded = config.auth_password_hash.get_secret_value() if config.auth_password_hash else ""
        valid = (
            parsed.scheme == "https"
            and host_valid
            and not parsed.netloc.endswith(":")
            and bool(parsed.hostname)
            and not parsed.username
            and not parsed.password
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
            and origin == f"https://{parsed.netloc}"
            and re.fullmatch(r"[a-z0-9.\-\[\]:]+", parsed.netloc) is not None
            and (parsed.port is None or (0 < parsed.port <= 65535 and parsed.port != 443))
            and bool(username)
            and len(username.encode("utf-8")) <= 256
            and not any(ord(char) < 32 or ord(char) == 127 or char == ":" for char in username)
            and _HASH_PATTERN.fullmatch(encoded) is not None
        )
    except (ValueError, UnicodeError):
        valid = False
    if not valid:
        raise RuntimeError("Invalid public security configuration") from None


_HASH_PATTERN = re.compile(r"scrypt\$([0-9a-f]{32})\$([0-9a-f]{64})\Z")


class WebSecurityMiddleware:
    """Outer application boundary, including mounts, documentation and 404s."""

    def __init__(self, app: ASGIApp, config: Settings):
        self.app = app
        self.config = config
        validate_public_settings(config)
        # One bounded queue doubles as global and per-peer failure accounting.
        # Reservations are recorded before awaiting, then removed on success.
        self._attempts: deque[tuple[float, str, object]] = deque()
        self._hashing = 0
        self._cache_key = secrets.token_bytes(32)
        self._cached_auth: tuple[bytes, float] | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            # No WebSocket API is supported; never bypass the HTTP boundary.
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False
        sanitized = False

        async def secure_send(message):
            nonlocal sanitized
            if message["type"] == "http.response.start" and message["status"] >= 500:
                sanitized = True
                await JSONResponse({"detail": "Internal server error"}, status_code=500)(
                    scope,
                    receive,
                    header_send,
                )
                return
            if not sanitized:
                await header_send(message)

        async def header_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                if self.config.deployment_mode == "public":
                    headers = MutableHeaders(scope=message)
                    headers.update(
                        {
                            "Cache-Control": "no-store",
                            "X-Content-Type-Options": "nosniff",
                            "X-Frame-Options": "DENY",
                            "Referrer-Policy": "no-referrer",
                            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
                            "Content-Security-Policy": (
                                "default-src 'self'; script-src 'self'; "
                                "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                                "connect-src 'self'; object-src 'none'; base-uri 'none'; "
                                "frame-ancestors 'none'; form-action 'self';"
                            ),
                        }
                    )
                    # HSTS is hostname-wide, including unrelated HTTP services
                    # on other ports. Enable at the proxy only after auditing them.
            await send(message)

        try:
            await self.handle_http(scope, receive, secure_send)
        except Exception:
            if not started:
                await JSONResponse({"detail": "Internal server error"}, status_code=500)(
                    scope,
                    receive,
                    header_send,
                )
            elif not sanitized:
                # A streaming response cannot be rewritten after headers. Let the
                # ASGI server terminate it rather than imply successful completion.
                raise

    async def handle_http(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.config.deployment_mode == "local":
            try:
                loopback = ipaddress.ip_address(
                    str((scope.get("client") or (None,))[0])
                ).is_loopback
            except ValueError:
                loopback = False
            if not loopback:
                await JSONResponse({"detail": "Local access only"}, status_code=403)(
                    scope, receive, send
                )
                return
        if self.config.deployment_mode == "public":
            headers = Headers(scope=scope)
            # Only the trusted ASGI server may interpret proxy headers.
            authority = urlsplit(self.config.public_origin).netloc
            if scope.get("scheme") != "https" or headers.getlist("host") != [authority]:
                await JSONResponse({"detail": "Invalid request authority"}, status_code=400)(
                    scope, receive, send
                )
                return
            auth_status = await self.authenticate(
                headers, str((scope.get("client") or ("unknown",))[0])
            )
            if auth_status == 429:
                await JSONResponse(
                    {"detail": "Too many authentication attempts"},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )(scope, receive, send)
                return
            if auth_status != 200:
                response = JSONResponse(
                    {"detail": "Authentication required"},
                    status_code=401,
                    headers={"WWW-Authenticate": 'Basic realm="Portfolio", charset="UTF-8"'},
                )
                await response(scope, receive, send)
                return
            fetch_site = headers.getlist("sec-fetch-site")
            if (
                len(fetch_site) > 1
                or (
                    fetch_site
                    and fetch_site[0]
                    not in {
                        "same-origin",
                        "same-site",
                        "none",
                    }
                )
                or (
                    scope["method"] not in {"GET", "HEAD", "OPTIONS"}
                    and headers.getlist("origin") != [self.config.public_origin]
                )
            ):
                await JSONResponse({"detail": "Cross-origin request forbidden"}, status_code=403)(
                    scope,
                    receive,
                    send,
                )
                return
        await self.bounded_body(scope, receive, send)

    async def bounded_body(self, scope: Scope, receive: Receive, send: Send) -> None:
        headers = Headers(scope=scope)
        lengths = headers.getlist("content-length")
        if len(lengths) > 1 or (lengths and re.fullmatch(r"[0-9]{1,20}", lengths[0]) is None):
            await JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)(
                scope, receive, send
            )
            return
        declared = int(lengths[0]) if lengths else None
        limit = self.config.max_request_body_bytes
        if declared is not None and declared > limit:
            await JSONResponse({"detail": "Request body too large"}, status_code=413)(
                scope, receive, send
            )
            return
        # Buffer only up to the cap, before FastAPI's JSON/multipart parsing or
        # any dependency/handler runs. A receive wrapper alone is too late.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > limit:
                await JSONResponse({"detail": "Request body too large"}, status_code=413)(
                    scope, receive, send
                )
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        if declared is not None and declared != len(body):
            await JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)(
                scope, receive, send
            )
            return
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                payload = bytes(body)
                body.clear()
                return {"type": "http.request", "body": payload, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    async def authenticate(self, headers: Headers, peer: str) -> int:
        values = headers.getlist("authorization")
        username, password = "", ""
        valid = False
        if len(values) == 1 and len(values[0]) <= 8192:
            try:
                scheme, token = values[0].split(" ", 1)
                if scheme.lower() == "basic":
                    decoded = base64.b64decode(token, validate=True).decode("utf-8")
                    username, password = decoded.split(":", 1)
                    valid = True
            except (ValueError, UnicodeError, binascii.Error):
                pass
        assert self.config.auth_username is not None and self.config.auth_password_hash is not None
        expected_user = self.config.auth_username.get_secret_value()
        encoded = self.config.auth_password_hash.get_secret_value()
        if not valid:
            return 401
        now = monotonic()
        # Retain only one keyed digest, not Basic credentials or plaintext. This
        # single-user cache avoids scrypt per asset/API request on small machines.
        fingerprint = hmac.digest(
            self._cache_key, (values[0] + encoded + expected_user).encode(), "sha256"
        )
        if (
            self._cached_auth
            and now < self._cached_auth[1]
            and hmac.compare_digest(
                fingerprint,
                self._cached_auth[0],
            )
        ):
            return 200
        while self._attempts and self._attempts[0][0] <= now - 60:
            self._attempts.popleft()
        if (
            self._hashing >= 2
            or len(self._attempts) >= 30
            or sum(item[1] == peer for item in self._attempts) >= 5
        ):
            return 429
        reservation = (now, peer, object())
        self._attempts.append(reservation)
        # Always derive the key even for a wrong username; never block the loop.
        user_ok = hmac.compare_digest(username.encode("utf-8"), expected_user.encode("utf-8"))
        self._hashing += 1
        job = asyncio.create_task(asyncio.to_thread(verify_password, password, encoded))
        job.add_done_callback(self._hash_finished)
        # Cancelling an HTTP request must not release the slot while its worker
        # thread still holds scrypt's memory. No unbounded semaphore wait queue.
        password_ok = await asyncio.shield(job)
        if user_ok & password_ok:
            if reservation in self._attempts:
                self._attempts.remove(reservation)
            self._cached_auth = (fingerprint, monotonic() + 300)
            return 200
        return 401

    def _hash_finished(self, job: asyncio.Task) -> None:
        self._hashing -= 1
        if not job.cancelled():
            job.exception()  # Consume exceptions even if the request disconnected.


def hash_password(password: str) -> str:
    """Create a salted hash: fixed scrypt n=16384, r=8, p=1, dklen=32.

    Call from a getpass-based setup tool; never pass a password on a command line.
    """
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${key.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Verify only our fixed-cost format; malformed hashes fail closed."""
    match = _HASH_PATTERN.fullmatch(encoded)
    if match is None:
        return False
    salt, expected = (bytes.fromhex(part) for part in match.groups())
    actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32)
    return hmac.compare_digest(actual, expected)

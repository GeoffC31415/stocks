"""Narrow single-owner passkey API; no passwords or bearer tokens in JSON."""

from __future__ import annotations

import json
import re
import secrets
from typing import Annotated

from fastapi import APIRouter, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.passkeys import AuthError, PasskeyStore
from app.security import PREAUTH_COOKIE, SESSION_COOKIE


class SafeAuthRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def safe(request):
            try:
                return await handler(request)
            except AuthError as error:
                return JSONResponse({"detail": error.detail}, status_code=error.status)
            except RequestValidationError:
                # Default validation errors echo input, including recovery secrets.
                return JSONResponse({"detail": "Invalid authentication request"}, status_code=422)

        return safe


router = APIRouter(prefix="/api/auth", route_class=SafeAuthRoute)


class EmptyBody(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class RegistrationBody(EmptyBody):
    label: str = Field(min_length=1, max_length=80)

    @field_validator("label")
    @classmethod
    def validate_label(cls, value):
        value = value.strip()
        if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Invalid label")
        return value


class RecoveryBody(RegistrationBody):
    token: SecretStr = Field(min_length=43, max_length=128)


class VerificationBody(EmptyBody):
    ceremony_id: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    credential: dict = Field(max_length=12)

    @field_validator("credential")
    @classmethod
    def bound_credential(cls, value):
        if len(json.dumps(value)) > 14000:
            raise ValueError("Credential too large")
        return value


def store_for(request: Request) -> PasskeyStore:
    store = request.app.state.auth_store
    if store is None:
        raise AuthError(403, "Passkey authentication is not configured")
    return store


def token_for(request: Request):
    return request.cookies.get(SESSION_COOKIE)


def cookie(response, name, value, max_age):
    response.set_cookie(
        name, value, max_age=max_age, secure=True, httponly=True, samesite="strict", path="/"
    )


def browser_for(request, response):
    browser = request.cookies.get(PREAUTH_COOKIE, "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", browser):
        browser = secrets.token_urlsafe(32)
    cookie(response, PREAUTH_COOKIE, browser, 300)
    return browser


def budget(request, browser):
    store_for(request).rate_limit(request.client.host if request.client else "unknown", browser)


def session_json(request, session=None):
    config = request.app.state.web_config
    local = config.deployment_mode == "local"
    mode = "local" if local else config.auth_mode
    session = session if session is not None else getattr(request.state, "passkey_session", None)
    basic = getattr(request.state, "basic_authenticated", False)
    store = request.app.state.auth_store
    can_register = False
    if store:
        can_register = store.is_recent(token_for(request)) or (
            mode == "basic" and basic and not store.credentials()
        )
    return {
        "mode": mode,
        "authenticated": local or (basic if mode == "basic" else bool(session)),
        "passkey_authenticated": bool(session),
        "can_register": can_register,
        "expires_at": min(
            session["expires_at"], session["last_activity"] + config.auth_session_idle_seconds
        )
        if session
        else None,
    }


def authenticated(request):
    session = store_for(request).session(token_for(request))
    if not session:
        raise AuthError()
    return session


def finish(request, response, result):
    token, session = result
    config = request.app.state.web_config
    cookie(response, SESSION_COOKIE, token, config.auth_session_absolute_seconds)
    body = session_json(request, session)
    body["can_register"] = True
    return body


@router.get("/session")
def session_status(request: Request):
    return session_json(request)


@router.post("/register/options")
def register_options(body: RegistrationBody, request: Request, response: Response):
    store = store_for(request)
    browser = browser_for(request, response)
    budget(request, browser)
    return store.registration_options(
        browser,
        label=body.label,
        bootstrap=(
            request.app.state.web_config.auth_mode == "basic"
            and getattr(request.state, "basic_authenticated", False)
        ),
        session_token=token_for(request),
    )


@router.post("/register/verify")
def register_verify(body: VerificationBody, request: Request, response: Response):
    browser = request.cookies.get(PREAUTH_COOKIE, "")
    budget(request, browser)
    return finish(
        request,
        response,
        store_for(request).registration_verify(
            body.ceremony_id, browser, body.credential, old_token=token_for(request)
        ),
    )


@router.post("/login/options")
def login_options(body: EmptyBody, request: Request, response: Response):
    browser = browser_for(request, response)
    budget(request, browser)
    return store_for(request).login_options(browser)


@router.post("/login/verify")
def login_verify(body: VerificationBody, request: Request, response: Response):
    browser = request.cookies.get(PREAUTH_COOKIE, "")
    budget(request, browser)
    return finish(
        request,
        response,
        store_for(request).login_verify(
            body.ceremony_id, browser, body.credential, old_token=token_for(request)
        ),
    )


@router.post("/recovery/options")
def recovery_options(body: RecoveryBody, request: Request, response: Response):
    browser = browser_for(request, response)
    budget(request, browser)
    return store_for(request).recovery_options(
        browser, body.token.get_secret_value(), label=body.label
    )


@router.get("/credentials")
def credentials(request: Request):
    authenticated(request)
    return {"credentials": store_for(request).credentials()}


@router.delete("/credentials/{credential_id}")
def delete_credential(
    credential_id: Annotated[str, Field(max_length=1400, pattern=r"^[A-Za-z0-9_-]+$")],
    request: Request,
):
    store_for(request).delete_credential(credential_id, token_for(request))
    return {"ok": True}


@router.post("/logout")
def logout(body: EmptyBody, request: Request, response: Response):
    store_for(request).revoke_current(token_for(request))
    cookie(response, SESSION_COOKIE, "", 0)
    return {"ok": True}


@router.post("/logout-all")
def logout_all(body: EmptyBody, request: Request, response: Response):
    store_for(request).revoke_all(token_for(request))
    cookie(response, SESSION_COOKIE, "", 0)
    return {"ok": True}

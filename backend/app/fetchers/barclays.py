"""Barclays (Smart Investor / Direct Investing) login and export downloads.

Login route (verified 2026-09-22): surname + 12-digit membership number with
"remember me" -> "Passcode and memorable word" -> 5-digit passcode plus two
requested memorable-word characters. The PIN is not used on this route.

Lockout safety: a rejected credential writes a block marker; no further
automatic attempts are made until the marker is removed, because repeated
failures can lock the online-banking account.
"""

from __future__ import annotations

import re
from pathlib import Path  # noqa: TC003 - annotations only; kept simple
from typing import TYPE_CHECKING

from app.config import settings
from app.fetchers.base import (
    FetchError,
    NeedsAttention,
    broker_context,
    dismiss_cookies,
    pick_characters,
    requested_positions,
)
from app.services.sync_runner import StepResult

if TYPE_CHECKING:
    from playwright.async_api import Page

BARCLAYS_HOSTS = ("barclays.co.uk", "barclays.com")
LOGIN_URL = "https://bank.barclays.co.uk/olb/authlogin/loginAppContainer.do"


def block_marker() -> Path:
    return settings.resolved_browser_profile() / "barclays-login-blocked"


def _secret(name: str) -> str:
    value = getattr(settings, name)
    if value is None or not value.get_secret_value().strip():
        raise FetchError(f"Barclays: PORTFOLIO_{name.upper()} is not set in .env.")
    return value.get_secret_value().strip()


def _block(reason: str) -> None:
    marker = block_marker()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(reason + "\nDelete this file after checking your details to re-enable.\n")


async def _is_logged_in(page: Page) -> bool:
    if "authlogin" in page.url:
        return False
    return await page.get_by_role("link", name=re.compile(r"log ?out", re.I)).count() > 0 or (
        await page.get_by_role("button", name=re.compile(r"log ?out", re.I)).count() > 0
    )


async def login(page: Page) -> None:
    if block_marker().exists():
        raise NeedsAttention(
            "Barclays automatic login is paused after a rejected attempt; "
            f"check .env then delete {block_marker()}."
        )
    await page.goto(LOGIN_URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    await dismiss_cookies(page)
    if await _is_logged_in(page):
        return

    # Wait for either the empty identification form or the remembered-user view.
    surname = page.locator("#surnameMem")
    remembered = page.get_by_text(re.compile(r"Switch user", re.I))
    for _ in range(40):
        if (await surname.count() and await surname.is_visible()) or await remembered.count():
            break
        await page.wait_for_timeout(500)
    else:
        raise FetchError("Barclays: login page did not render.")
    await dismiss_cookies(page)
    if await surname.count() and await surname.is_visible():
        await surname.press_sequentially(_secret("barclays_surname"), delay=40)
        await page.locator("#membership0").press_sequentially(
            _secret("barclays_membership_number"), delay=40
        )
        if not await page.locator("#checkbox1_Y").is_checked():
            await page.locator("#checkbox1_Y").click(force=True)
    # Remembered user: step 1 shows the saved name and only needs Continue.
    await page.locator("#continue").click()
    passcode = page.locator("#passcode")
    option = page.get_by_text(re.compile(r"^\s*Passcode and memorable word\s*$", re.I))
    for _ in range(40):
        if (await passcode.count() and await passcode.is_visible()) or await option.count():
            break
        await page.wait_for_timeout(500)
    else:
        raise FetchError("Barclays: identification step did not reach the passcode page.")

    if not (await passcode.count() and await passcode.is_visible()):
        await option.first.click()
        await page.wait_for_selector("#passcode", state="visible", timeout=10_000)

    await page.locator("#passcode").press_sequentially(_secret("barclays_passcode"), delay=40)
    word = _secret("barclays_memorable_word")
    boxes = page.locator("input[id^='memorableCharacters-input-']")
    count = await boxes.count()
    if count < 1:
        raise FetchError("Barclays: memorable-word boxes not found.")
    for i in range(count):
        box = boxes.nth(i)
        label = await box.evaluate("e => (e.labels && e.labels[0] ? e.labels[0].innerText : '')")
        positions = requested_positions(label or "")
        if len(positions) != 1:
            raise FetchError(
                "Barclays: could not read which memorable-word character is requested."
            )
        await box.fill(pick_characters(word, positions)[0])

    submit = page.locator("#submitAuthentication")
    if not await submit.count():
        raise FetchError("Barclays: login button not found.")
    await submit.click()
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(8000)

    if "authlogin" in page.url and await page.locator("#passcode").count():
        body = (await page.locator("body").inner_text()).lower()
        if any(
            k in body for k in ("incorrect", "don't match", "do not match", "try again", "locked")
        ):
            _block("Barclays rejected the passcode/memorable word.")
            raise NeedsAttention(
                "Barclays rejected the passcode/memorable word; auto-login paused."
            )
        raise FetchError("Barclays: still on the login page after submitting.")
    if "authlogin" in page.url:
        # Any bounce back to the login flow after submitting credentials is treated as a
        # possible rejection: pause automation rather than risk an account lockout.
        heading = await page.locator("h2").all_inner_texts()
        reason = next((h.strip() for h in heading if "problem" in h.lower()), "returned to login")
        _block(f"Barclays login did not complete ({reason}).")
        raise NeedsAttention(f"Barclays login did not complete ({reason}); auto-login paused.")


async def fetch(inbox: Path, *, headless: bool = True) -> StepResult:
    """Log in and download Barclays exports.

    The post-login export route is not yet recorded (login has not completed
    under automation), so after a successful login this reports
    ``needs_attention`` rather than guessing at navigation.
    """
    needed = (
        "barclays_surname",
        "barclays_membership_number",
        "barclays_passcode",
        "barclays_memorable_word",
    )
    if not all(
        getattr(settings, n) and getattr(settings, n).get_secret_value().strip() for n in needed
    ):
        return StepResult("Barclays", "skipped", "not configured")
    if block_marker().exists():
        return StepResult(
            "Barclays", "needs_attention", f"auto-login paused; delete {block_marker()} to retry"
        )
    async with broker_context(
        settings.resolved_browser_profile() / "barclays", BARCLAYS_HOSTS, headless=headless
    ) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        try:
            await login(page)
        except NeedsAttention as exc:
            return StepResult("Barclays", "needs_attention", str(exc))
        except FetchError as exc:
            return StepResult("Barclays", "failed", str(exc))
    return StepResult("Barclays", "needs_attention", "logged in; export route not yet recorded")

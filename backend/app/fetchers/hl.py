"""Hargreaves Lansdown login (read-only use)."""

from __future__ import annotations

import datetime as dt
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
from app.services.export_classifier import ExportKind, UnrecognisedExport, classify_export
from app.services.sync_runner import StepResult

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.async_api import Page

HL_HOSTS = ("hl.co.uk",)
LOGIN_URL = "https://online.hl.co.uk/my-accounts/login-step-one"
HOME_URL = "https://online.hl.co.uk/my-accounts"


def _secret(name: str) -> str:
    value = getattr(settings, name)
    if value is None or not value.get_secret_value().strip():
        raise FetchError(f"HL: PORTFOLIO_{name.upper()} is not set in .env.")
    return value.get_secret_value().strip()


async def is_logged_in(page: Page) -> bool:
    return (
        "/my-accounts" in page.url
        and "login" not in page.url
        and await page.locator("a[href*='logout'], a:has-text('Log out')").count() > 0
    )


async def login(page: Page) -> None:
    await page.goto(HOME_URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(1500)
    await dismiss_cookies(page)
    if await is_logged_in(page):
        return
    if "login-step-one" not in page.url:
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await dismiss_cookies(page)

    await page.fill("#username", _secret("hl_username"))
    await page.fill("#date-of-birth", _secret("hl_date_of_birth"))
    await page.locator("form input[type=submit]").first.click()
    await page.wait_for_load_state("domcontentloaded")
    try:
        await page.wait_for_selector("#online-password-verification", timeout=15_000)
    except Exception as exc:
        raise FetchError("HL: step 1 was not accepted (username/date of birth).") from exc

    await page.fill("#online-password-verification", _secret("hl_password"))
    secure = _secret("hl_secure_number")
    for i in (1, 2, 3):
        box = page.locator(f"#secure-number-{i}")
        positions = requested_positions(await box.get_attribute("title") or "")
        if len(positions) != 1:
            raise FetchError("HL: could not read which Secure Number digit is requested.")
        await box.fill(pick_characters(secure, positions)[0])
    await page.locator("#submit").click()
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(3000)

    if await page.locator("#online-password-verification").count():
        raise FetchError("HL: step 2 was rejected (password/Secure Number).")
    body = (await page.locator("body").inner_text()).lower()
    if "verification code" in body or "one-time" in body or "passcode" in body:
        raise NeedsAttention("HL asked for a verification code.")
    if not await is_logged_in(page):
        raise FetchError(f"HL: login finished on an unexpected page ({page.url.split('?')[0]}).")


ACCOUNT_SUMMARY_CSV = (
    "https://online.hl.co.uk/my-accounts/account_summary_csv/sort/stock/sortdir/asc"
)
ACTIVITY_CSV = (
    "https://online.hl.co.uk/my-accounts/capital-transaction-history/filter//format/csv"
    "/period/custom/startDate/{start}/endDate/{end}"
)
# Overlapping windows are safe: orders are deduplicated per row by fingerprint.
ACTIVITY_WINDOW_DAYS = 90


async def _save(page: Page, url: str, inbox: Path, prefix: str, expected: ExportKind) -> Path:
    resp = await page.context.request.get(url)
    if resp.status != 200:
        raise FetchError(f"HL: {prefix} download returned HTTP {resp.status}.")
    data = await resp.body()
    try:
        kind = classify_export(prefix, data).kind
    except UnrecognisedExport as exc:
        raise FetchError(f"HL: {prefix} download was not a valid export.") from exc
    if kind is not expected:
        raise FetchError(f"HL: {prefix} download was {kind.value}, expected {expected.value}.")
    path = inbox / f"{prefix}-{dt.datetime.now():%Y%m%d-%H%M%S}.csv"
    tmp = path.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.rename(path)
    return path


async def fetch(inbox: Path, *, headless: bool = True) -> StepResult:
    """Download HL holdings and recent capital-account activity into the inbox."""
    async with broker_context(
        settings.resolved_browser_profile() / "hl", HL_HOSTS, headless=headless
    ) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        try:
            await login(page)
            # Visit the pages as a user would; the CSV endpoints are the pages' own Download links.
            link = page.locator("a[href*='/account_summary/account/']").first
            href = await link.get_attribute("href") if await link.count() else None
            if not href:
                raise FetchError("HL: account link not found on the accounts page.")
            await page.goto(href, wait_until="domcontentloaded")
            if not await page.locator("a[href*='account_summary_csv']").count():
                raise FetchError("HL: account summary Download link not found.")
            await _save(
                page, ACCOUNT_SUMMARY_CSV, inbox, "hl-account-summary", ExportKind.HL_HOLDINGS
            )
            end = dt.date.today()
            start = end - dt.timedelta(days=ACTIVITY_WINDOW_DAYS)
            await _save(
                page,
                ACTIVITY_CSV.format(start=start.isoformat(), end=end.isoformat()),
                inbox,
                "hl-activity",
                ExportKind.HL_ACTIVITY,
            )
        except NeedsAttention as exc:
            return StepResult("Hargreaves Lansdown", "needs_attention", str(exc))
        except FetchError as exc:
            return StepResult("Hargreaves Lansdown", "failed", str(exc))
    return StepResult("Hargreaves Lansdown", "ok", "holdings + 90-day activity downloaded")

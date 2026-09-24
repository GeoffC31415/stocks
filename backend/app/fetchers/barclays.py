"""Barclays (Smart Investor / Direct Investing) login and export downloads.

Login route (verified 2026-09-22): surname + 12-digit membership number with
"remember me" -> "Passcode and memorable word" -> 5-digit passcode plus two
requested memorable-word characters. The PIN is not used on this route.

Lockout safety uses two distinct files in the browser-profile directory:
``barclays-login-blocked`` is the permanent legacy/operator pause. Automatic
acknowledgement NEVER removes it. Operators pause by creating this file, not by
editing/replacing attempt state. Only an operator may clear it after review.
``barclays-login-attempt`` is exclusively created and fsynced before bank I/O;
only a verified, committed import can automatically acknowledge this attempt.
Uncertain attempts remain for review. For manual recovery, stop/quiesce workers,
review the outcome, then explicitly clear the relevant files before resuming.
A pause cannot interrupt an already in-flight bank call, but survives cleanup
and prevents the next login even if the current import has already committed.
"""

from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path  # noqa: TC003 - annotations only; kept simple
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urljoin, urlsplit
from zoneinfo import ZoneInfo

from app.config import settings
from app.fetchers.base import (
    FetchError,
    NeedsAttention,
    broker_context,
    dismiss_cookies,
    pick_characters,
    requested_positions,
)
from app.services.barclays_sync_service import FetchedPair, validate_pair
from app.services.export_classifier import ExportKind, UnrecognisedExport, classify_export
from app.services.sync_runner import StepResult

if TYPE_CHECKING:
    from playwright.async_api import Page

BARCLAYS_HOSTS = ("barclays.co.uk", "barclays.com")
LOGIN_URL = "https://bank.barclays.co.uk/olb/authlogin/loginAppContainer.do"


def operator_pause_marker() -> Path:
    """Permanent pause; preserves the legacy filename and is never auto-cleared."""
    return settings.resolved_browser_profile() / "barclays-login-blocked"


def block_marker() -> Path:
    """Compatibility alias for callers setting/checking the permanent pause."""
    return operator_pause_marker()


def attempt_marker() -> Path:
    """Automatic attempt state, NOT an operator pause mechanism."""
    return settings.resolved_browser_profile() / "barclays-login-attempt"


def _marker_exists(marker: Path) -> bool:
    # Dangling symlinks also block; unexpected filesystem errors fail closed.
    try:
        marker.lstat()
    except FileNotFoundError:
        return False
    return True


def _sync_directory(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _secret(name: str) -> str:
    value = getattr(settings, name)
    if value is None or not value.get_secret_value().strip():
        raise FetchError(f"Barclays: PORTFOLIO_{name.upper()} is not set in .env.")
    return value.get_secret_value().strip()


def _block(reason: str) -> None:
    """Record a durable permanent pause, independent of automatic attempt state."""
    marker = operator_pause_marker()
    marker.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(marker, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(reason + "\nAuto-login paused. Operator review required.\n")
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(marker.parent)


async def _is_logged_in(page: Page) -> bool:
    parsed = urlsplit(page.url)
    if parsed.scheme != "https" or parsed.netloc != "www.investments.barclays.co.uk":
        return False
    return await page.get_by_role("link", name=re.compile(r"log ?out", re.I)).count() > 0 or (
        await page.get_by_role("button", name=re.compile(r"log ?out", re.I)).count() > 0
    )


async def _logout(page: Page) -> None:
    """Best-effort read-only cleanup; never log browser exceptions or clear guards."""
    try:
        parsed = urlsplit(page.url)
        if parsed.scheme != "https" or parsed.netloc not in {
            "bank.barclays.co.uk", "www.investments.barclays.co.uk"
        }:
            return
        for role in ("link", "button"):
            control = page.get_by_role(role, name=re.compile(r"^log ?out$", re.I))
            if await control.count():
                await control.first.click(timeout=5000)
                return
    except Exception:
        # Preserve the original fetch failure and never disclose private URLs.
        pass


async def login(page: Page) -> tuple[int, int, int]:
    if _marker_exists(operator_pause_marker()):
        raise NeedsAttention("Barclays operator/legacy pause; operator review required.")
    # Write BEFORE any bank interaction. Exclusive creation serializes attempts;
    # a crash, cancellation, timeout or machine restart leaves the latch intact.
    marker = attempt_marker()
    marker.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise NeedsAttention(
            "Barclays attempt in progress or uncertain; operator review required."
        ) from None
    with os.fdopen(fd, "w") as stream:
        stream.write("Attempt in progress or outcome uncertain. Operator review required.\n")
        stream.flush()
        os.fsync(stream.fileno())
        stat = os.fstat(stream.fileno())
        identity = (stat.st_dev, stat.st_ino, stat.st_mtime_ns)
    # Persist the directory entry too: losing the latch on reboot risks retries.
    _sync_directory(marker.parent)
    try:
        if _marker_exists(operator_pause_marker()):
            raise NeedsAttention("Barclays operator pause; operator review required.")
        await _login_once(page)
        if not await _is_logged_in(page):
            raise NeedsAttention("Barclays authentication not verified; auto-login paused.")
        if _marker_exists(operator_pause_marker()):
            raise NeedsAttention("Barclays operator pause; operator review required.")
        stat = marker.stat()
        if (stat.st_dev, stat.st_ino, stat.st_mtime_ns) != identity:
            raise NeedsAttention("Barclays attempt state changed; operator review required.")
    except Exception:
        # Never include provider text, Playwright call logs or credential values.
        raise NeedsAttention("Barclays login not verified; auto-login paused.") from None
    return identity


async def _login_once(page: Page) -> None:
    await page.goto(LOGIN_URL, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    await dismiss_cookies(page)
    if await _is_logged_in(page):
        return
    if urlsplit(page.url).path == "/olb/balances/PersonalFinancialSummary.action":
        await open_investment_account(page)
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
    await open_investment_account(page)


async def open_investment_account(page: Page) -> Page:
    """Follow the observed account-card link, never the product/dealing menu.

    Manual login reaches the banking summary first. Its single account-card
    link redirects to Smart Investor; menu items with similar names are not
    account navigation. Ambiguous/multiple accounts require operator review.
    """
    try:
        initial = page.url
        parsed = urlsplit(initial)
        if parsed.scheme == "https" and parsed.netloc == "www.investments.barclays.co.uk":
            _account_root(initial)
            if await _is_logged_in(page) and page.url == initial:
                return page
            raise ValueError("Unverified investment session")
        if (
            parsed.scheme != "https"
            or parsed.netloc != "bank.barclays.co.uk"
            or parsed.path != "/olb/balances/PersonalFinancialSummary.action"
        ):
            raise ValueError("Unverified banking summary")
        logout = page.get_by_role("link", name=re.compile(r"^log ?out$", re.I))
        if not await logout.count():
            raise ValueError("Banking session missing logout")
        links = page.locator('a.account-name[href*="/olb/smartinvestor/tiaa/fnz/AccountHome.do"]')
        if await links.count() != 1:
            raise ValueError("Investment account is ambiguous")
        href = await links.get_attribute("href", timeout=5000)
        target = urlsplit(urljoin(initial, href or ""))
        query = parse_qs(target.query, keep_blank_values=True)
        if (
            page.url != initial
            or target.scheme != "https"
            or target.netloc != "bank.barclays.co.uk"
            or target.path != "/olb/smartinvestor/tiaa/fnz/AccountHome.do"
            or target.fragment
            or set(query) != {"hierarchyId"}
            or len(query["hierarchyId"]) != 1
            or not query["hierarchyId"][0].strip()
        ):
            raise ValueError("Unexpected investment account link")
        await page.goto(target.geturl(), wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_url(
            lambda url: urlsplit(str(url)).netloc == "www.investments.barclays.co.uk",
            timeout=30000,
        )
        _account_root(page.url)
        if not await _is_logged_in(page):
            raise ValueError("Investment session unverified")
        return page
    except Exception:
        raise NeedsAttention(
            "Barclays: investment account navigation not verified; operator review required."
        ) from None


def _account_root(url: str) -> str:
    parsed = urlsplit(url)
    match = re.match(r"^(/en-gb/SubAccount/[A-Za-z0-9-]+)/", parsed.path)
    if parsed.scheme != "https" or parsed.netloc != "www.investments.barclays.co.uk" or not match:
        raise FetchError("Barclays: authenticated investment account page required.")
    return "https://www.investments.barclays.co.uk" + match.group(1)


async def read_export(
    page: Page,
    href: str,
    suffix: str,
    expected: ExportKind,
    *,
    account_root: str | None = None,
) -> bytes:
    """GET only the observed export for the pinned account; never follow redirects."""
    try:
        return await _read_export(page, href, suffix, expected, account_root=account_root)
    except Exception:
        # Browser call logs and network errors can contain private URLs or credentials.
        raise FetchError("Barclays: account export not verified; no retry attempted.") from None


async def _read_export(
    page: Page,
    href: str,
    suffix: str,
    expected: ExportKind,
    *,
    account_root: str | None,
) -> bytes:
    approved = {
        ExportKind.BARCLAYS_HOLDINGS: "/Portfolio/InvestmentsOverview/GetInvestmentsFile",
        ExportKind.BARCLAYS_ORDERS: "/Orders/History/GetDocumentFile",
    }
    if approved.get(expected) != suffix:
        raise FetchError("Barclays: unapproved export endpoint.")
    url = urljoin(page.url, href)
    parsed = urlsplit(url)
    root = account_root if account_root is not None else _account_root(page.url)
    if _account_root(page.url) != root:
        raise FetchError("Barclays: account or session changed.")
    if (
        parsed.scheme != "https"
        or parsed.netloc != "www.investments.barclays.co.uk"
        or parsed.fragment
        or "https://" + parsed.netloc + parsed.path != root + suffix
    ):
        raise FetchError("Barclays: refused unexpected export link.")
    response = await page.request.get(url, max_redirects=0, max_retries=0, timeout=20000)
    if response.status != 200:
        raise FetchError("Barclays: export unavailable; no retry attempted.")
    data = await response.body()
    if _account_root(page.url) != root:
        raise FetchError("Barclays: account or session changed.")
    if not data or len(data) > 10 * 1024 * 1024:
        raise FetchError("Barclays: export empty or oversized.")
    try:
        kind = classify_export("export.xls", data).kind
    except UnrecognisedExport:
        raise FetchError("Barclays: export content invalid.") from None
    if kind != expected:
        raise FetchError("Barclays: wrong export type.")
    return data


async def collect_exports(page: Page) -> tuple[bytes, bytes]:
    """Collect a validated pair in memory; no login, persistence or dealing actions.

    Caller must start on the authenticated account Overview. The fetcher returns
    this pair in memory to the runner's atomic importer; neither export is ever
    published separately to the generic inbox.
    """
    try:
        return await _collect_exports(page)
    except NeedsAttention:
        raise NeedsAttention("Barclays: authenticated investment account page required.") from None
    except Exception:
        raise FetchError("Barclays: account exports not verified; no retry attempted.") from None


async def _collect_exports(page: Page) -> tuple[bytes, bytes]:
    root = _account_root(page.url)
    if not await _is_logged_in(page):
        raise NeedsAttention("Barclays: authenticated investment account page required.")
    holdings_link = page.locator("a").filter(has_text="Download investments")
    href = await holdings_link.get_attribute("href", timeout=5000)
    if not href:
        raise FetchError("Barclays: holdings export link missing.")
    holdings = await read_export(
        page,
        href,
        "/Portfolio/InvestmentsOverview/GetInvestmentsFile",
        ExportKind.BARCLAYS_HOLDINGS,
        account_root=root,
    )
    orders_link = page.get_by_role("link", name="Orders", exact=True)
    href = await orders_link.get_attribute("href", timeout=5000)
    if not href or urljoin(page.url, href) != root + "/Orders":
        raise FetchError("Barclays: unexpected orders navigation.")
    await orders_link.click(timeout=5000)
    await page.wait_for_load_state("domcontentloaded")
    if _account_root(page.url) != root or not await _is_logged_in(page):
        raise FetchError("Barclays: account or session changed.")
    await page.locator("#history-tab").click(timeout=5000)
    href = (
        await page.locator("a")
        .filter(has_text="Download order history")
        .get_attribute("href", timeout=5000)
    )
    if not href:
        raise FetchError("Barclays: orders export link missing.")
    orders = await read_export(
        page,
        href,
        "/Orders/History/GetDocumentFile",
        ExportKind.BARCLAYS_ORDERS,
        account_root=root,
    )
    return holdings, orders


def _acknowledge_attempt(marker: Path, identity: tuple[int, int, int]) -> None:
    """Clear only automatic attempt state, never the independent operator pause."""
    if marker != attempt_marker():
        raise NeedsAttention("Barclays invalid attempt path; operator review required.")
    stat = marker.stat()
    if (stat.st_dev, stat.st_ino, stat.st_mtime_ns) != identity:
        raise NeedsAttention("Barclays attempt state changed; operator review required.")
    marker.unlink()
    _sync_directory(marker.parent)


async def fetch(inbox: Path, *, headless: bool = True) -> StepResult | FetchedPair:
    """Opt-in, one guarded attempt; committed pairs clear only attempt state.

    Credentials alone never enable this path. The account must be pinned and
    the operator must explicitly enable it after supervised authentication.
    Nothing is written to the generic inbox, so one export cannot import alone.
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
    if _marker_exists(operator_pause_marker()):
        return StepResult(
            "Barclays", "needs_attention", "operator/legacy pause; operator review required"
        )
    if _marker_exists(attempt_marker()):
        return StepResult(
            "Barclays", "needs_attention",
            "attempt in progress or uncertain; operator review required",
        )
    if not settings.barclays_automation_enabled:
        return StepResult(
            "Barclays",
            "needs_attention",
            "unattended login disabled pending supervised authentication verification",
        )
    expected = settings.barclays_expected_account
    if expected is None or not expected.get_secret_value().strip():
        return StepResult(
            "Barclays", "needs_attention", "expected investment account is not configured"
        )
    try:
        async with broker_context(
            settings.resolved_browser_profile() / "barclays", BARCLAYS_HOSTS, headless=headless
        ) as context:
            page = await context.new_page()
            try:
                identity = await login(page)
                marker = attempt_marker()
                observed = dt.datetime.now(dt.UTC)
                holdings, orders = await collect_exports(page)
                as_of = observed.astimezone(ZoneInfo("Europe/London")).date()
                if dt.datetime.now(ZoneInfo("Europe/London")).date() != as_of:
                    raise NeedsAttention("Barclays export crossed the date boundary.")
                pair = validate_pair(holdings, orders, as_of=as_of)
                if pair.account_name != expected.get_secret_value():
                    raise NeedsAttention("Barclays export account identity is not verified.")
                return FetchedPair(
                    holdings,
                    orders,
                    observed,
                    lambda: _acknowledge_attempt(marker, identity),
                )
            finally:
                await _logout(page)
    except Exception:
        # Retain the durable guard on every failure, including close failures.
        return StepResult(
            "Barclays", "needs_attention", "sync not verified; operator review required"
        )

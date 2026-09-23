"""Barclays (Smart Investor / Direct Investing) login and export downloads.

Login route (verified 2026-09-22): surname + 12-digit membership number with
"remember me" -> "Passcode and memorable word" -> 5-digit passcode plus two
requested memorable-word characters. The PIN is not used on this route.

Lockout safety: every login attempt writes a persistent block marker before
bank interaction. Further automatic attempts remain paused for operator review,
because repeated failures can lock the online-banking account.
"""

from __future__ import annotations

import os
import re
from pathlib import Path  # noqa: TC003 - annotations only; kept simple
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlsplit

from app.config import settings
from app.fetchers.base import (
    FetchError,
    NeedsAttention,
    dismiss_cookies,
    pick_characters,
    requested_positions,
)
from app.services.export_classifier import ExportKind, UnrecognisedExport, classify_export
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
    marker.write_text(reason + "\nAuto-login paused. Operator review required.\n")


async def _is_logged_in(page: Page) -> bool:
    if urlsplit(page.url).hostname != "www.investments.barclays.co.uk":
        return False
    return await page.get_by_role("link", name=re.compile(r"log ?out", re.I)).count() > 0 or (
        await page.get_by_role("button", name=re.compile(r"log ?out", re.I)).count() > 0
    )


async def login(page: Page) -> None:
    # Write BEFORE any bank interaction. Exclusive creation serializes attempts;
    # a crash, cancellation, timeout or machine restart leaves the latch intact.
    marker = block_marker()
    marker.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise NeedsAttention("Barclays auto-login paused; operator review required.") from None
    with os.fdopen(fd, "w") as stream:
        stream.write("Attempt in progress or outcome uncertain. Operator review required.\n")
        stream.flush()
        os.fsync(stream.fileno())
    # Persist the directory entry too: losing the latch on reboot risks retries.
    directory_fd = os.open(marker.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    try:
        await _login_once(page)
        if not await _is_logged_in(page):
            raise NeedsAttention("Barclays authentication not verified; auto-login paused.")
    except Exception:
        # Never include provider text, Playwright call logs or credential values.
        raise NeedsAttention("Barclays login not verified; auto-login paused.") from None


async def _login_once(page: Page) -> None:
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

    Caller must start on the authenticated account Overview. Deliberately not
    wired into the scheduler until login-to-investments and atomic import are
    verified. A failed second export cannot publish a partial pair.
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


async def fetch(inbox: Path, *, headless: bool = True) -> StepResult:
    """Fail closed until unattended authentication and atomic import are verified.

    Post-login exports are mapped by collect_exports; that is not evidence that
    automated credentials are safe. Configuration alone must not enable login.
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
            "Barclays", "needs_attention", "auto-login paused; operator review required"
        )
    return StepResult(
        "Barclays",
        "needs_attention",
        "unattended login disabled pending authentication and import verification",
    )


def _rearm_after_verified_success() -> None:
    """Only a verified login + validated export pair clears the attempt latch."""
    block_marker().unlink(missing_ok=True)


async def sync(session, *, headless: bool = True, today=None) -> StepResult:  # noqa: ANN001
    """Guarded end-to-end Barclays refresh: one login, both exports, one transaction.

    Refuses unless ``barclays_auto_login`` is armed, credentials are configured
    and no latch exists. The latch is written before bank interaction and is
    cleared only after a verified login AND a successful atomic import; any
    other outcome (rejection, MFA, timeout, crash, invalid export) keeps it.
    """
    import datetime as dt

    from app.fetchers.base import broker_context
    from app.services.barclays_pair_import import BarclaysExportInvalid, import_barclays_pair

    preflight = await fetch(Path("."))
    if preflight.status == "skipped" or block_marker().exists():
        return preflight
    if not settings.barclays_auto_login:
        return StepResult("Barclays", "skipped", "unattended login not armed")

    async with broker_context(
        settings.resolved_browser_profile() / "barclays", BARCLAYS_HOSTS, headless=headless
    ) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        try:
            await login(page)  # writes the latch first; raises NeedsAttention otherwise
            await _open_investment_overview(page)
            holdings, orders = await collect_exports(page)
        except NeedsAttention as exc:
            return StepResult("Barclays", "needs_attention", str(exc))
        except FetchError as exc:
            return StepResult("Barclays", "needs_attention", f"{exc} Auto-login paused.")
        finally:
            await _logout(page)
    try:
        result = await import_barclays_pair(
            session, holdings, orders, as_of=today or dt.date.today()
        )
    except BarclaysExportInvalid as exc:
        return StepResult("Barclays", "needs_attention", f"{exc} Auto-login paused.")
    _rearm_after_verified_success()
    return StepResult(
        "Barclays",
        "ok" if "imported" in (result.holdings, result.orders) else "unchanged",
        f"holdings {result.holdings}, {result.new_orders} new orders",
    )


async def _open_investment_overview(page: Page) -> None:
    """From the banking landing page, open the (single) investment account Overview."""
    if urlsplit(page.url).hostname == "www.investments.barclays.co.uk":
        _account_root(page.url)
        return
    raise NeedsAttention(
        "Barclays: route from banking login to the investment account is not mapped yet."
    )


async def _logout(page: Page) -> None:
    try:
        control = page.get_by_role("link", name=re.compile(r"log ?out", re.I))
        if await control.count():
            await control.first.click(timeout=5000)
    except Exception:  # noqa: BLE001, S110 - best effort; the session expires anyway
        pass

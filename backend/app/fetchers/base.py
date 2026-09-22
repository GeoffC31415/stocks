"""Shared Playwright plumbing for broker download fetchers.

Safety properties (enforced here, not by each fetcher):
- Navigation is restricted to the broker's own hosts via request routing.
- ``safe_click`` refuses any control whose accessible text looks like a
  dealing/transfer action, even if a selector drifts onto it.
- Downloads are validated with the content classifier before they count.
- No credential value is ever logged; errors report the step name only.
"""

from __future__ import annotations

import datetime as dt
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.services.export_classifier import ExportKind, UnrecognisedExport, classify_export

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from playwright.async_api import BrowserContext, Locator, Page

DENY_TEXT = re.compile(
    r"\b(deal|buy|sell|trade|transfer|withdraw|place order|confirm order|top.?up|pay|switch)\b",
    re.IGNORECASE,
)
_NTH = re.compile(r"(\d+)(?:st|nd|rd|th)\b", re.IGNORECASE)


class FetchError(RuntimeError):
    """A scripted step failed; message names the step, never a secret."""


class NeedsAttention(FetchError):
    """The broker asked for something automation cannot supply (e.g. a device code)."""


class UnsafeAction(FetchError):
    """A click was refused by the dealing/transfer guard."""


def requested_positions(text: str) -> list[int]:
    """Parse '1st', '5th' ... into 1-based positions."""
    return [int(m) for m in _NTH.findall(text)]


def pick_characters(secret: str, positions: list[int]) -> list[str]:
    if not positions or any(p < 1 or p > len(secret) for p in positions):
        raise FetchError("Requested character position is outside the stored secret.")
    return [secret[p - 1] for p in positions]


def host_allowed(url: str, allowed: tuple[str, ...]) -> bool:
    if url.startswith(("data:", "blob:", "about:")):
        return True
    m = re.match(r"^[a-z]+://([^/:]+)", url, re.IGNORECASE)
    if not m:
        return False
    host = m.group(1).lower()
    return any(host == a or host.endswith("." + a) for a in allowed)


async def safe_click(locator: Locator, *, allow: re.Pattern[str] | None = None) -> None:
    text = " ".join(
        filter(
            None,
            [
                (await locator.inner_text(timeout=5000)).strip() if await locator.count() else "",
                await locator.get_attribute("aria-label") or "",
                await locator.get_attribute("value") or "",
                await locator.get_attribute("title") or "",
            ],
        )
    )
    if DENY_TEXT.search(text) and not (allow and allow.search(text)):
        raise UnsafeAction(f"Refused to click control labelled {text[:60]!r}.")
    await locator.click()


@asynccontextmanager
async def broker_context(
    profile_dir: Path, allowed_hosts: tuple[str, ...], *, headless: bool = True
) -> AsyncIterator[BrowserContext]:
    from playwright.async_api import async_playwright

    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_dir.chmod(0o700)
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            str(profile_dir),
            headless=headless,
            locale="en-GB",
            timezone_id="Europe/London",
            accept_downloads=True,
            viewport={"width": 1366, "height": 900},
            # The Surface's systemd sandbox (NoNewPrivileges, no user namespaces
            # under AppArmor) blocks Chromium's own sandbox; the unit confines it.
            chromium_sandbox=False,
        )

        async def _guard(route: Any) -> None:
            req = route.request
            # Only top-level document navigations are policed; sub-resources
            # (analytics, CDNs) are harmless to block or allow.
            if req.is_navigation_request() and not host_allowed(req.url, allowed_hosts):
                await route.abort()
            else:
                await route.continue_()

        await ctx.route("**/*", _guard)
        try:
            yield ctx
        finally:
            await ctx.close()


async def download(
    page: Page,
    trigger: Locator,
    inbox: Path,
    *,
    prefix: str,
    expected: ExportKind,
    allow: re.Pattern[str] | None = None,
    timeout_ms: int = 60_000,
) -> Path:
    async with page.expect_download(timeout=timeout_ms) as info:
        await safe_click(trigger, allow=allow)
    dl = await info.value
    suffix = Path(dl.suggested_filename).suffix or ".dat"
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    tmp = inbox / f".{prefix}-{stamp}{suffix}.part"
    await dl.save_as(tmp)
    try:
        kind = classify_export(dl.suggested_filename, tmp.read_bytes()).kind
    except UnrecognisedExport as exc:
        tmp.unlink(missing_ok=True)
        raise FetchError(f"{prefix}: download was not a valid export ({exc}).") from exc
    if kind is not expected:
        tmp.unlink(missing_ok=True)
        raise FetchError(f"{prefix}: expected {expected.value}, got {kind.value}.")
    final = inbox / f"{prefix}-{stamp}{suffix}"
    tmp.rename(final)
    return final


async def dismiss_cookies(page: Page) -> None:
    """Reject optional cookies on HL (OneTrust) and Barclays (Tealium, shadow DOM)."""
    for sel in ("#onetrust-reject-all-handler", "button:has-text('Reject all')"):
        loc = page.locator(sel)
        if await loc.count() and await loc.first.is_visible():
            await loc.first.click()
            return
    if await page.locator("#__tealiumGDPRecModal").count():
        reject = page.get_by_role("button", name="Reject optional cookies")
        if await reject.count():
            await reject.first.click()
            await page.wait_for_timeout(500)

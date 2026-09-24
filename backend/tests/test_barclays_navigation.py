"""Post-login navigation is read-only; no credentials or real bank traffic."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.fetchers import barclays
from app.fetchers.base import NeedsAttention

SUMMARY = "https://bank.barclays.co.uk/olb/balances/PersonalFinancialSummary.action"
ACCOUNT_LINK = "/olb/smartinvestor/tiaa/fnz/AccountHome.do?hierarchyId=synthetic"
ROOT = "https://www.investments.barclays.co.uk/en-gb/SubAccount/synthetic"


def banking_page(href=ACCOUNT_LINK, count=1):
    link = SimpleNamespace(
        count=AsyncMock(return_value=count), get_attribute=AsyncMock(return_value=href)
    )
    link.first = link
    page = SimpleNamespace(url=SUMMARY, locator=Mock(return_value=link))

    async def goto(url, **kwargs):
        page.url = ROOT + "/Portfolio"

    page.goto = AsyncMock(side_effect=goto)
    page.wait_for_url = AsyncMock()
    page.get_by_role = Mock(return_value=SimpleNamespace(count=AsyncMock(return_value=1)))
    return page


async def test_banking_summary_follows_observed_single_account_link():
    page = banking_page()
    result = await barclays.open_investment_account(page)
    assert result is page
    page.goto.assert_awaited_once_with(
        "https://bank.barclays.co.uk" + ACCOUNT_LINK, wait_until="domcontentloaded", timeout=30000
    )
    assert page.url == ROOT + "/Portfolio"


@pytest.mark.parametrize(
    "href",
    [
        "http://bank.barclays.co.uk" + ACCOUNT_LINK,
        "https://bank.barclays.co.uk.evil.example" + ACCOUNT_LINK,
        "https://user@bank.barclays.co.uk" + ACCOUNT_LINK,
        "/olb/transfers/securecms/t.do?pn=investmentaccount",
        ACCOUNT_LINK + "&hierarchyId=other",
        ACCOUNT_LINK + "&extra=1",
        ACCOUNT_LINK + "#fragment",
    ],
)
async def test_navigation_rejects_non_account_or_untrusted_links(href):
    page = banking_page(href)
    with pytest.raises(NeedsAttention):
        await barclays.open_investment_account(page)
    page.goto.assert_not_awaited()


@pytest.mark.parametrize("count", [0, 2])
async def test_ambiguous_account_requires_review(count):
    page = banking_page(count=count)
    with pytest.raises(NeedsAttention):
        await barclays.open_investment_account(page)
    page.goto.assert_not_awaited()


async def test_existing_banking_session_hands_off_without_secret_entry(monkeypatch):
    page = banking_page()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.locator = Mock(return_value=SimpleNamespace(count=AsyncMock(return_value=0)))
    page.get_by_text = Mock(return_value=SimpleNamespace(count=AsyncMock(return_value=0)))
    monkeypatch.setattr(barclays, "dismiss_cookies", AsyncMock())
    navigate = AsyncMock()
    monkeypatch.setattr(barclays, "open_investment_account", navigate)
    monkeypatch.setattr(
        barclays, "_secret", Mock(side_effect=AssertionError("must not enter credentials"))
    )
    await barclays._login_once(page)
    navigate.assert_awaited_once_with(page)

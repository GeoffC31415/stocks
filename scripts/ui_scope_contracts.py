"""Read-only browser checks for account/period URL and request agreement."""
import re
from urllib.parse import parse_qs, urlparse


def verify_scope_navigation(page, width: int) -> dict:
    original = page.url
    period = page.get_by_role("combobox", name="Performance period", exact=True)
    with page.expect_response(lambda response: "/api/portfolio/performance?" in response.url
                              and parse_qs(urlparse(response.url).query).get("period") == ["YTD"]):
        period.select_option("YTD")
    assert parse_qs(urlparse(page.url).query)["period"] == ["YTD"]
    account_select = page.locator("#mobile-account-filter")
    options = account_select.locator("option").evaluate_all("els => els.map(e => e.value)")
    assert len(options) > 1, "Account-switch fixture requires at least one named account"
    account = options[1]
    with page.expect_response(lambda response: "/api/portfolio/performance?" in response.url
                              and parse_qs(urlparse(response.url).query).get("account_name") == [account]) as response:
        if width < 768:
            account_select.select_option(account)
        else:
            page.locator("header").get_by_role("button", name=account, exact=True).click()
    payload = response.value.json()
    assert payload["scope"]["account_name"] == account
    assert payload["period"] == "YTD"
    page.go_back(wait_until="networkidle")
    assert parse_qs(urlparse(page.url).query)["account"] == ["all"]
    assert parse_qs(urlparse(page.url).query)["period"] == ["YTD"]
    page.go_back(wait_until="networkidle")
    assert page.url == original
    page.go_forward(wait_until="networkidle")
    assert period.input_value() == "YTD"
    page.go_back(wait_until="networkidle")
    return {"account_period_requests_match": True, "back_forward_restores_scope": True}


def verify_episode_navigation(page, payload: dict) -> dict:
    from playwright.sync_api import expect

    episodes = payload.get("drawdown_episodes", [])
    if not episodes:
        return {"episodes": 0}
    episode = episodes[0]
    page.get_by_role("link", name=re.compile("View episode from")).first.click()
    page.get_by_text(re.compile("Chart zoom:")).wait_for()
    assert parse_qs(urlparse(page.url).query)["episode"] == [episode["id"]], "Episode URL does not match the selected row"
    dots = page.locator('[aria-label="Snapshot performance chart"] .recharts-area-dot')
    expect(dots).to_have_count(episode["observations"])
    page.get_by_role("button", name="Show full chart window", exact=True).click()
    expect(dots).to_have_count(len(payload["flow_adjusted_curve"]))
    return {"episodes": len(episodes), "zoom_and_reset": True}

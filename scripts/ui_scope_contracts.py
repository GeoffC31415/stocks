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


def verify_timeline_navigation(page, *, touch: bool, output) -> dict:
    from playwright.sync_api import expect

    with page.expect_response(lambda response: "/api/portfolio/timeline?" in response.url) as pending:
        page.get_by_role("checkbox", name="Show timeline events", exact=True).click()
    expect(page.get_by_role("checkbox", name="Show timeline events", exact=True)).to_be_checked()
    payload = pending.value.json()
    assert payload["event_count"] > 0, "Timeline fixture must contain real source records"
    day_counts = {}
    for event in payload["events"]:
        if event["kind"] in ("trade", "snapshot"):
            day_counts[event["date"]] = day_counts.get(event["date"], 0) + 1
    markers = page.get_by_role("button", name=re.compile("^Timeline events on "))
    expect(markers.first).to_be_visible()
    assert markers.count() <= 12
    right = 0
    plot = page.get_by_label("Snapshot performance chart", exact=True)
    plot_top = plot.bounding_box()["y"]
    observation_top = min(dot.bounding_box()["y"] for dot in plot.locator(".recharts-area-dot").all())
    for marker in markers.all():
        date = marker.get_attribute("data-event-date")
        assert marker.get_attribute("aria-label") == f"Timeline events on {date}: {day_counts[date]}"
        box = marker.bounding_box()
        assert box and box["width"] >= 24 and box["height"] >= 24
        assert box["x"] >= right and box["x"] + box["width"] <= page.viewport_size["width"], "Timeline markers overlap or clip"
        assert box["y"] >= plot_top and box["y"] + box["height"] < observation_top, "Timeline markers cover observations"
        right = box["x"] + box["width"]
    if touch:
        markers.first.tap()
    else:
        markers.first.focus()
        markers.first.press("Enter")

    def open_source(kind):
        link = page.get_by_role("link", name=re.compile(f"^View source {kind} ")).first
        expect(link).to_be_visible()
        with page.expect_response(lambda response: "/api/portfolio/timeline/source/" in response.url) as source:
            link.tap() if touch else link.click()
        page.get_by_role("heading", name="Source record", exact=True).wait_for()
        assert source.value.status == 200
        record = source.value.json()
        assert record["source_type"] == kind
        assert str(record["source_id"]) == parse_qs(urlparse(page.url).query)["record"][0]
        page.go_back(wait_until="networkidle")
        expect(page.get_by_role("checkbox", name="Show timeline events", exact=True)).to_be_checked()

    open_source("import")
    crowded_date = max(day_counts, key=day_counts.get)
    crowded_count = day_counts[crowded_date]
    assert crowded_count >= 2, "Browser fixture requires crowded same-day events"
    day = page.locator(f"#timeline-day-{crowded_date}")
    for _ in range(len(day_counts)):
        if day.count():
            break
        page.get_by_role("button", name=re.compile("^Show more dates")).click()
    if day.locator("..").get_attribute("open") is None:
        day.click()
    expect(page.get_by_role("link", name=re.compile("^View source "))).to_have_count(crowded_count)
    open_source("order")
    page.evaluate("document.activeElement?.blur(); window.scrollTo(0, 0)")
    page.mouse.move(0, 0)
    page.screenshot(path=str(output / f"timeline-{page.viewport_size['width']}.png"), full_page=True)
    page.get_by_role("checkbox", name="Show timeline events", exact=True).click()
    expect(page.get_by_role("checkbox", name="Show timeline events", exact=True)).not_to_be_checked()
    return {"source_types_opened": ["import", "order"], "crowded_day_events": crowded_count,
            "back_preserves_timeline": True, "touch": touch}

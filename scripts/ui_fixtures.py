"""Adversarial browser payloads, in memory only; never modify stored data."""
from __future__ import annotations

EMPTY_SUMMARY = {
    "as_of_date": None, "import_batch_id": None,
    "total_value_gbp": 0, "total_book_cost_gbp": 0, "total_pnl_gbp": 0,
    "by_account": {}, "by_group": {}, "allocation": [], "group_allocation": [],
    "worst_pct": [], "best_pct": [],
}


def long_names(payload):
    """Stress names without changing financial numbers, IDs or list sizes."""
    prefix = "SyntheticVeryLongUnbrokenDisplayNameForResponsiveVerification" * 2
    if isinstance(payload, list):
        return [long_names(item) for item in payload]
    if not isinstance(payload, dict):
        return payload
    result = {}
    for key, value in payload.items():
        if key in {"security_name", "account_name"} and isinstance(value, str):
            result[key] = prefix + value
        elif key == "by_account" and isinstance(value, dict):
            result[key] = {prefix + account: total for account, total in value.items()}
        else:
            result[key] = long_names(value)
    return result


def verify_accessibility(page, *, touch: bool) -> dict:
    """Exercise native keyboard/touch activation, dismissal and reduced motion."""
    skip = page.get_by_role("link", name="Skip to main content", exact=True)
    skip.focus()
    skip.press("Enter")
    assert page.evaluate("document.activeElement.id") == "main-content"
    animated = page.locator('[data-testid="ambient-background"] *').evaluate_all(
        "elements => elements.filter(e=>getComputedStyle(e).animationName!=='none').length"
    )
    assert animated == 0, "Reduced-motion preference must stop ambient animation"
    buttons = page.locator('button[aria-haspopup="dialog"]')
    definitions = buttons.count()
    for index in range(definitions):
        trigger = buttons.nth(index)
        trigger.focus()
        trigger.press("Enter")
        popup = page.get_by_role("dialog")
        popup.wait_for()
        bounds = popup.bounding_box()
        assert bounds and bounds["x"] >= 0 and bounds["y"] >= 0
        assert bounds["x"] + bounds["width"] <= page.viewport_size["width"] + 1
        assert bounds["y"] + bounds["height"] <= page.viewport_size["height"] + 1
        popup.press("Escape")
        assert trigger.evaluate("e=>document.activeElement===e"), "Escape must return definition focus"
        trigger.press("Space")
        page.get_by_role("button", name="Close definition").click()
        assert trigger.evaluate("e=>document.activeElement===e")
        if touch:
            trigger.tap()
            page.touchscreen.tap(1, 1)
        else:
            trigger.click()
            page.mouse.click(1, 1)
        assert page.get_by_role("dialog").count() == 0, "Outside pointer must dismiss definition"
    return {"definitions_checked": definitions, "reduced_motion": True, "touch": touch}


def focus_controls(page) -> dict:
    """Focus every visible control; overflow must reveal it, not clip it."""
    checked, failures = 0, []
    controls = page.locator("main button, main a[href], main input, main select, main [tabindex='0'], header button, header select")
    for index in range(controls.count()):
        control = controls.nth(index)
        if not control.is_visible() or not control.is_enabled():
            continue
        control.focus()
        box = control.bounding_box()
        checked += 1
        if box and (box["x"] < -1 or box["x"] + box["width"] > page.viewport_size["width"] + 1):
            failures.append(control.get_attribute("aria-label") or control.inner_text()[:80])
    return {"checked": checked, "failures": failures}

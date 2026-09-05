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

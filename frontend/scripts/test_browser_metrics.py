"""Fail-closed measurement gates, including a deliberate real Chrome shift."""
import pytest
from playwright.sync_api import sync_playwright
from browser_metrics import BUDGETS, install_observer, capture_metrics, budget_failures, chart_fold_failure


def test_budgets_reject_each_excess_independently():
    for key, limit in BUDGETS.items():
        values = {name: 0 for name in BUDGETS}
        values[key] = limit + 1
        assert len(budget_failures(values)) == 1
        assert budget_failures(values)[0].startswith(key)


def test_ordinary_fold_does_not_infer_warning_exception():
    metrics = {'chart': {'top': 845}, 'viewport': {'height': 844}}
    assert chart_fold_failure(metrics)
    assert not chart_fold_failure(metrics, critical_warning=True)
    assert not chart_fold_failure(metrics, zoom=2)
    assert chart_fold_failure({'chart': None, 'viewport': {'height':844}})


def test_capture_refuses_absent_observer():
    class Page:
        def evaluate(self, _script):
            return {'observerInstalled': False}
    with pytest.raises(RuntimeError, match='observer'):
        capture_metrics(Page())


def test_real_chrome_observer_detects_deliberate_shift():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True, args=['--no-sandbox'])
        try:
            context = browser.new_context(viewport={'width':390, 'height':844})
            install_observer(context)
            context.route('**/*', lambda route: route.fulfill(content_type='text/html', body='<div id="reserve"></div><p style="height:300px">SYNTHETIC moving content</p>'))
            page = context.new_page()
            page.goto('http://fixture.test/', wait_until='networkidle')
            page.evaluate('document.querySelector("#reserve").style.height="150px"')
            page.wait_for_timeout(200)
            assert capture_metrics(page)['cls'] > 0.01
            context.close()
        finally:
            browser.close()

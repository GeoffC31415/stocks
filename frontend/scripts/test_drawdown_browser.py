"""Real Chrome regression: hover only recorded drawdown observations."""
import os
from pathlib import Path
from threading import Thread

import pytest
from playwright.sync_api import sync_playwright, expect
from preview_demo import make_server


def assert_drawdown_hover(page):
    plot = page.get_by_role('region', name='Snapshot drawdown chart', exact=True)
    expect(plot).to_be_visible()
    dots = plot.locator('.recharts-area-dot')
    expect(dots).to_have_count(5)
    # Scroll the stable region, not a Recharts dot replaced during responsive resize.
    # Locator.hover retries detached dots while retaining exact date/value assertions.
    plot.scroll_into_view_if_needed()
    dots.nth(2).hover(force=True)
    tooltip = plot.get_by_role('tooltip')
    expect(tooltip).to_contain_text('2026-06-01')
    expect(tooltip).to_contain_text('-2.884615%')
    assert '2026-06-02' not in tooltip.inner_text()
    return {'recorded_observations': dots.count(), 'date': '2026-06-01', 'drawdown': '-2.884615%'}


def test_actual_drawdown_hover():
    dist = os.environ.get('STOCKS_TEST_DIST')
    if not dist:
        pytest.skip('Set STOCKS_TEST_DIST to the isolated frontend build')
    server = make_server(Path(dist), 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True, args=['--no-sandbox'])
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 900}, reduced_motion='reduce')
                base = f'http://127.0.0.1:{server.server_port}'
                page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(base + '/') and route.request.method == 'GET' else route.abort())
                page.goto(base + '/portfolio?tab=performance', wait_until='networkidle')
                assert_drawdown_hover(page)
                # Critical unavailable-window exception: preserve the reason,
                # show no fabricated/raw fallback chart, do not waive ordinary fold checks.
                import copy
                from preview_demo import PERF
                unavailable = copy.deepcopy(PERF)
                unavailable['metrics'] = {'total_return_pct': {'status': 'unavailable', 'value': None, 'unit': 'percent',
                    'method': 'Synthetic unavailable-window gate', 'start_date': None, 'end_date': None,
                    'observations': 0, 'reasons': [{'code': 'synthetic_critical', 'message': 'SYNTHETIC critical missing flow evidence. No return is valid.', 'action_href': None}]}}
                page.route('**/api/portfolio/performance*', lambda route: route.fulfill(json=unavailable))
                page.goto(base + '/', wait_until='networkidle')
                expect(page.get_by_role('heading', name='Portfolio overview', exact=True)).to_be_visible()
                expect(page.get_by_text('SYNTHETIC critical missing flow evidence. No return is valid.', exact=True).first).to_be_visible()
                expect(page.get_by_role('region', name='Snapshot performance chart', exact=True)).to_have_count(0)
                expect(page.get_by_text('Flow-adjusted performance unavailable for this window. Raw account values are not a substitute for investment returns.', exact=True)).to_be_visible()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()

"""Real Chrome refresh-read faults on GET-only synthetic data; no broker or DB."""
import argparse
import json
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect
from preview_demo import make_server


def verify(dist, out):
    out.mkdir(parents=True, exist_ok=True)
    server = make_server(dist, 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    results = []
    try:
        with sync_playwright() as driver:
            browser = driver.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True, args=['--no-sandbox'])
            try:
                for width, height in [(390, 844), (1440, 900)]:
                    context = browser.new_context(viewport={'width': width, 'height': height}, reduced_motion='reduce')
                    state = {'fail': True, 'reads': 0}
                    forbidden, errors = [], []
                    def guard(route):
                        request = route.request
                        if urlsplit(request.url).netloc != urlsplit(base).netloc or request.method != 'GET':
                            forbidden.append(request.method + ' ' + request.url)
                            route.abort()
                        elif urlsplit(request.url).path == '/api/sync/status':
                            state['reads'] += 1
                            if state['fail']:
                                route.fulfill(status=503, content_type='application/json', body='{"detail":"Synthetic unavailable refresh status"}')
                            else:
                                route.continue_()
                        else:
                            route.continue_()
                    context.route('**/*', guard)
                    page = context.new_page()
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(base + '/data?tab=confidence', wait_until='networkidle')
                    header = page.get_by_role('banner')
                    panel = page.get_by_role('region', name='Data confidence')
                    for surface in [header, panel]:
                        expect(surface.get_by_role('alert')).to_contain_text('Refresh status unavailable.')
                        expect(surface.get_by_text('Refresh outcome:', exact=False)).to_have_count(0)
                    expect(header.get_by_text('Checking refresh…')).to_have_count(0)
                    # The lazy panel can mount after Topbar's first read has settled; that is a new observer, not a retry.
                    assert 1 <= state['reads'] <= 2, state
                    initial_reads = state['reads']
                    page.wait_for_timeout(500)
                    assert state['reads'] == initial_reads, state
                    page.screenshot(path=str(out / f'{width}-initial-503.png'), full_page=True)
                    state['fail'] = False
                    panel.get_by_role('button', name='Retry refresh status').click()
                    for surface in [header, panel]:
                        expect(surface.get_by_text('Refresh outcome: partial', exact=True)).to_be_visible()
                        expect(surface.get_by_role('alert')).to_have_count(0)
                    expect(panel.get_by_text('Checked: 2026-09-01T18:30:00+00:00', exact=True)).to_be_visible()
                    assert state['reads'] == initial_reads + 1, state
                    # Remount the confidence query using real in-app navigation, retaining the shared cache.
                    state['fail'] = True
                    page.get_by_role('tab', name='Analysis settings', exact=True).click()
                    page.get_by_role('tab', name='Data confidence', exact=True).click()
                    for surface in [header, panel]:
                        expect(surface.get_by_role('alert')).to_contain_text('showing cached evidence; current status is unknown')
                        expect(surface.get_by_text('Cached refresh outcome: partial', exact=True)).to_be_visible()
                        expect(surface.get_by_text('Refresh outcome: partial', exact=True)).to_have_count(0)
                    expect(panel.get_by_text('Checked: 2026-09-01T18:30:00+00:00', exact=True)).to_be_visible()
                    expect(panel.get_by_text('Attempt: 2026-09-29T18:29:00+00:00', exact=True)).to_be_visible()
                    account = header.get_by_role('combobox', name='Account', exact=True) if width < 768 else header.get_by_role('button', name='DEMO ISA', exact=True)
                    if width < 768:
                        account.select_option('DEMO ISA')
                    else:
                        account.click()
                    expect(panel.get_by_role('alert')).to_contain_text('current status is unknown')
                    panel.get_by_role('button', name='Retry refresh status').click()
                    page.wait_for_load_state('networkidle')
                    expect(header.get_by_text('Cached refresh outcome: partial', exact=True)).to_be_visible()
                    assert state['reads'] == initial_reads + 3, state
                    expect(panel.get_by_text('Checked: 2026-09-01T18:30:00+00:00', exact=True)).to_be_visible()
                    geometry = page.evaluate('() => ({width:innerWidth,scrollWidth:document.documentElement.scrollWidth})')
                    assert geometry['scrollWidth'] <= width, geometry
                    page.screenshot(path=str(out / f'{width}-cached-503.png'), full_page=True)
                    page.evaluate('window.scrollTo(0, 0)')
                    page.screenshot(path=str(out / f'{width}-cached-503-viewport.png'))
                    if width < 768:
                        page.evaluate('window.scrollTo(0, document.documentElement.scrollHeight)')
                        clearance = page.evaluate('''() => ({contentBottom:document.querySelector('[data-testid="route-content"]').getBoundingClientRect().bottom,navTop:document.querySelector('nav[aria-label="Mobile"]').getBoundingClientRect().top})''')
                        assert clearance['contentBottom'] <= clearance['navTop'] + 1, clearance
                        page.screenshot(path=str(out / f'{width}-cached-503-bottom.png'))
                    state['fail'] = False
                    header.get_by_role('button', name='Retry refresh status').click()
                    expect(panel.get_by_text('Refresh outcome: partial', exact=True)).to_be_visible()
                    expect(header.get_by_role('alert')).to_have_count(0)
                    assert not forbidden and not errors, (forbidden, errors)
                    results.append({'width': width, 'height': height, 'refresh_reads': state['reads'], 'geometry': geometry,
                                    'initial_503': True, 'cached_503': True, 'account_change': True, 'retry_recovery': True,
                                    'forbidden_requests': forbidden, 'page_errors': errors})
                    context.close()
            finally:
                browser.close()
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        assert not thread.is_alive()
        (out / 'refresh-status.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    assert len(results) == 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    verify(args.dist, args.out)

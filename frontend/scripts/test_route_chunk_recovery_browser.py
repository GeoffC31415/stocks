"""Cold late-chunk GET failure containment in the built app, without DB or writes."""
import argparse
import json
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright
from preview_demo import make_server


def verify(dist, out):
    out.mkdir(parents=True, exist_ok=True)
    server = make_server(dist, 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    rows = []
    try:
        with sync_playwright() as driver:
            browser = driver.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True, args=['--no-sandbox'])
            try:
                for width, height in [(390, 844), (1440, 900)]:
                    context = browser.new_context(viewport={'width': width, 'height': height}, reduced_motion='reduce')
                    state = {'deny': True, 'blocked_chunks': [], 'documents': 0}
                    forbidden, errors = [], []
                    row = {'width': width, 'height': height, 'state': state, 'forbidden_requests': forbidden, 'page_errors': errors}
                    rows.append(row)
                    def guard(route):
                        request = route.request
                        if not request.url.startswith(base + '/') or request.method != 'GET':
                            forbidden.append(request.method + ' ' + request.url)
                            route.abort()
                        elif '/assets/ActivityWorkspace-' in request.url and state['deny']:
                            state['blocked_chunks'].append(request.url)
                            route.fulfill(status=503, body='Synthetic transient chunk failure', content_type='text/plain')
                        else:
                            if request.resource_type == 'document':
                                state['documents'] += 1
                            route.continue_()
                    context.route('**/*', guard)
                    page = context.new_page()
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    try:
                        page.goto(base + '/?account=DEMO+ISA&period=1Y', wait_until='networkidle')
                        expect(page.get_by_role('heading', name='Portfolio overview', exact=True)).to_be_visible()
                        assert not state['blocked_chunks'], state
                        navigation = page.get_by_role('navigation', name='Mobile' if width < 1024 else 'Primary', exact=True)
                        navigation.get_by_role('link', name='Activity', exact=True).click()
                        alert = page.get_by_role('alert').filter(has_text='Unable to load this workspace.')
                        expect(alert).to_be_visible()
                        expect(alert).to_contain_text('Reload the page to try again, or choose another workspace.')
                        expect(page.get_by_role('banner')).to_be_visible()
                        expect(navigation).to_be_visible()
                        expect(alert.get_by_role('button', name='Reload workspace')).to_be_visible()
                        assert urlsplit(page.url).path == '/activity'
                        assert parse_qs(urlsplit(page.url).query)['account'] == ['DEMO ISA']
                        assert parse_qs(urlsplit(page.url).query)['period'] == ['1Y']
                        assert len(state['blocked_chunks']) == 1, state
                        page.wait_for_timeout(600)
                        assert state['documents'] == 1 and len(state['blocked_chunks']) == 1, state
                        geometry = page.evaluate('() => ({width:innerWidth, scrollWidth:document.documentElement.scrollWidth})')
                        assert geometry['scrollWidth'] <= width, geometry
                        row['contained_url'] = page.url
                        row['geometry'] = geometry
                        page.screenshot(path=str(out / f'{width}-contained.png'))
                        # A different, previously unvisited lazy route must load without the old error.
                        navigation.get_by_role('link', name='Portfolio', exact=True).click()
                        expect(page.get_by_role('heading', name='Holdings', exact=True)).to_be_visible()
                        expect(alert).to_have_count(0)
                        assert state['documents'] == 1, state
                        navigation.get_by_role('link', name='Activity', exact=True).click()
                        expect(alert).to_be_visible()
                        assert len(state['blocked_chunks']) == 1, state  # lazy caches the rejection
                        # Include route-specific query and hash in reload recovery, not just global scope.
                        failed_url = base + '/activity?account=DEMO+ISA&period=1Y&tab=changes&from=2&to=5#source'
                        page.evaluate('(url) => { history.pushState({}, "", url); window.dispatchEvent(new PopStateEvent("popstate")); }', failed_url)
                        expect(alert).to_be_visible()
                        expected_url = page.url
                        assert expected_url == failed_url
                        state['deny'] = False
                        alert.get_by_role('button', name='Reload workspace').click()
                        expect(page.get_by_role('heading', name='Snapshot diff', exact=True)).to_be_visible()
                        expect(alert).to_have_count(0)
                        assert page.url == expected_url, (expected_url, page.url)
                        assert state['documents'] == 2, state
                        expect(page.get_by_role('banner')).to_be_visible()
                        expect(navigation).to_be_visible()
                        assert not forbidden and not errors, (forbidden, errors)
                        row.update({'other_route_loaded': True, 'cached_rejection_contained': True, 'reload_recovered': True, 'recovered_url': page.url})
                    finally:
                        context.close()
            finally:
                browser.close()
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        assert not thread.is_alive()
        (out / 'route-chunk-recovery.json').write_text(json.dumps({'server_thread_stopped': True, 'rows': rows}, indent=2))
    assert len(rows) == 2
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    verify(args.dist, args.out)

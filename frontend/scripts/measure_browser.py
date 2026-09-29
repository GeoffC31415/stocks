"""Measure baseline/final with the exact same synthetic fixture, never real data."""
import argparse
import json
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright
from browser_metrics import BUDGETS, VIEWPORTS, ZOOM_NOTE, install_observer, capture_metrics, budget_failures, chart_fold_failure
from preview_demo import make_server


def measure(dist, *, enforce=False):
    rows = []
    server = make_server(dist, 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True, args=['--no-sandbox'])
            try:
                for width, height, zoom in VIEWPORTS:
                    for path, heading in [('/', 'Portfolio overview'), ('/portfolio?tab=performance', 'Performance workspace'), ('/portfolio?tab=holdings', 'Holdings'), ('/tax', 'Capital Gains Tax')]:
                        context = browser.new_context(viewport={'width':width, 'height':height}, device_scale_factor=zoom, reduced_motion='reduce')
                        install_observer(context)
                        blocked, errors = [], []
                        def guard(route):
                            if route.request.url.startswith(base + '/') and route.request.method == 'GET':
                                route.continue_()
                            else:
                                blocked.append(route.request.url)
                                route.abort()
                        context.route('**/*', guard)
                        page = context.new_page()
                        page.on('pageerror', lambda e: errors.append(str(e)))
                        page.goto(base + path, wait_until='networkidle')
                        page.get_by_role('heading', name=heading, exact=True).first.wait_for()
                        page.wait_for_timeout(1500)  # real clock, include deferred layout
                        metrics = capture_metrics(page)
                        failures = budget_failures(metrics)
                        if path == '/':
                            failure = chart_fold_failure(metrics, zoom=zoom)
                            if failure: failures.append(failure)
                        if errors or blocked: failures.append('browser-or-external-request-error')
                        rows.append({'route':path, 'width':width, 'height':height, 'zoom':zoom, 'metrics':metrics, 'failures':failures})
                        context.close()
            finally:
                browser.close()
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        assert not thread.is_alive()
    return {'dist':str(dist), 'budgets':BUDGETS, 'zoom_note':ZOOM_NOTE, 'rows':rows, 'enforced':enforce}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--enforce', action='store_true')
    args = parser.parse_args()
    report = measure(args.dist, enforce=args.enforce)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps([{'route':row['route'], 'width':row['width'], 'height':row['height'], 'zoom':row['zoom'], **{k:row['metrics'][k] for k in BUDGETS}, 'chart':row['metrics']['chart'], 'failures':row['failures']} for row in report['rows']], indent=2))
    if args.enforce and any(row['failures'] for row in report['rows']): raise SystemExit(1)


if __name__ == '__main__': main()

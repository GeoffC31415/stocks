"""Overview DOM/visual hierarchy on real full-route Chrome, synthetic GET-only data."""
import argparse
import json
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright, expect
from preview_demo import make_server
from browser_metrics import install_observer, capture_metrics, budget_failures, chart_fold_failure


def verify(dist, out):
    out.mkdir(parents=True, exist_ok=True)
    server = make_server(dist, 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    results = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True, args=['--no-sandbox'])
            try:
                for width, height in [(390, 844), (1440, 900)]:
                    context = browser.new_context(viewport={'width': width, 'height': height}, reduced_motion='reduce')
                    install_observer(context)
                    errors = []
                    def guard(route):
                        if route.request.url.startswith(base + '/') and route.request.method == 'GET':
                            route.continue_()
                        else:
                            errors.append('blocked ' + route.request.url)
                            route.abort()
                    context.route('**/*', guard)
                    page = context.new_page()
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    page.goto(base, wait_until='networkidle')
                    page.get_by_role('heading', name='Portfolio overview').wait_for()
                    page.wait_for_timeout(1500)
                    page.screenshot(path=str(out / f'{width}-viewport.png'))
                    page.screenshot(path=str(out / f'{width}-full.png'), full_page=True)
                    layout = page.evaluate('''() => {
                      const root=document.querySelector('[data-testid="portfolio-briefing"]');
                      const value=[...root.querySelectorAll('p')].find(e=>e.textContent==='Portfolio value').parentElement.querySelector('.tabular');
                      const secondary=[...root.querySelectorAll('article')];
                      const chart=root.querySelector('[aria-label="Snapshot performance chart"]');
                      const changes=root.querySelector('#attribution-title')?.closest('section');
                      const allocation=root.querySelector('#allocation-brief-title')?.closest('section');
                      const items=[value,...secondary,chart,changes,allocation];
                      const boxes=items.map(e=>{const r=e.getBoundingClientRect();return {text:e.textContent.slice(0,70),left:r.left,top:r.top,bottom:r.bottom,font:parseFloat(getComputedStyle(e.matches('article') ? e.querySelector('.tabular') : e).fontSize)}});
                      const nav=document.querySelector('nav[aria-label="Mobile"]')?.getBoundingClientRect();
                      return {boxes,navTop:nav?.top,domOrder:items.every((e,i)=>!i||Boolean(items[i-1].compareDocumentPosition(e)&Node.DOCUMENT_POSITION_FOLLOWING)),scrollWidth:document.documentElement.scrollWidth,width:innerWidth};
                    }''')
                    metrics = capture_metrics(page)
                    failures = budget_failures(metrics)
                    fold = chart_fold_failure(metrics)
                    if fold: failures.append(fold)
                    if not layout['domOrder']: failures.append('incorrect-dom-order')
                    boxes = layout['boxes']
                    if width < 768 and not boxes[0]['bottom'] <= min(boxes[1]['top'], boxes[2]['top']): failures.append('value-not-before-secondary')
                    if width >= 768 and not boxes[0]['left'] < min(boxes[1]['left'], boxes[2]['left']): failures.append('desktop-value-not-first')
                    if width < 768 and not boxes[3]['top'] < layout['navTop']: failures.append('chart-start-obscured-by-mobile-nav')
                    if not max(boxes[1]['bottom'], boxes[2]['bottom']) <= boxes[3]['top']: failures.append('secondary-not-before-chart')
                    if width < 768 and not boxes[3]['bottom'] <= boxes[4]['top']: failures.append('changes-not-after-chart')
                    if not boxes[4]['bottom'] <= boxes[5]['top']: failures.append('allocation-not-after-changes')
                    if not boxes[0]['font'] > max(boxes[1]['font'], boxes[2]['font']): failures.append('primary-value-not-dominant')
                    toolbar = page.locator('header').filter(has=page.get_by_role('combobox', name='Performance period'))
                    if width < 768:
                        controls = toolbar.locator('select, button')
                        tops = controls.evaluate_all('els => els.filter(e=>e.getBoundingClientRect().width>0).map(e=>e.getBoundingClientRect().top)')
                        if max(tops) - min(tops) > 2: failures.append('mobile-toolbar-controls-wrap')
                    if layout['scrollWidth'] > width: failures.append('horizontal-overflow')
                    expect(page.get_by_text('Latest account snapshots · includes cash')).to_be_visible()
                    expect(page.get_by_text('API deposits less withdrawals where synced; trade proxies for other accounts. Performance window, not investment gain.')).to_be_visible()
                    expect(page.get_by_text('Carried-forward account valuations may mask', exact=False)).to_be_visible()
                    expect(page.get_by_text('Covered valuation dates:', exact=False)).to_be_visible()
                    results.append({'width': width, 'height': height, 'layout': layout, 'metrics': metrics, 'failures': failures + errors})
                    context.close()
            finally:
                browser.close()
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        assert not thread.is_alive()
        (out / 'hierarchy.json').write_text(json.dumps(results, indent=2))
    print(json.dumps([{'width': r['width'], 'chart': r['metrics']['chart'], 'cls': r['metrics']['cls'], 'failures': r['failures']} for r in results], indent=2))
    assert len(results) == 2 and all(not r['failures'] for r in results), 'Overview hierarchy/geometry failed'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    verify(args.dist, args.out)

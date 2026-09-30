"""Compare production UI layout/style with a candidate on the same GET-only fixtures.

Both builds must be isolated. Never reads production assets, databases or credentials.
Truthful status/caveat text may increase height; compare original component sizing,
classes, typography, colour and document order, not whole-page pixel equality.
"""
import argparse
import json
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright, expect
from preview_demo import make_server

ROUTES = {
    '/': 'Portfolio overview',
    '/portfolio?tab=holdings': 'Holdings',
    '/portfolio?tab=performance': 'Performance workspace',
    '/activity?tab=orders': 'Order history',
    '/data?tab=import': 'Import data',
}

CONTRACT = """() => {
 const style = el => {
   if (!el) return null;
   const r=el.getBoundingClientRect(), s=getComputedStyle(el);
   return {class:el.className, width:r.width, font:s.fontSize, lineHeight:s.lineHeight,
     color:s.color, background:s.backgroundColor, padding:s.padding, gap:s.gap};
 };
 const text = (selector, value) => [...document.querySelectorAll(selector)].find(e=>e.textContent===value);
 const chart=document.querySelector('[aria-label="Snapshot performance chart"]');
 const panel=chart?.parentElement;
 const tile=text('p','Snapshot investment return');
 const table=document.querySelector('[aria-label="Holdings table"]');
 const empty=text('p','Select a holding');
 const hero=text('p','Portfolio value');
 const attribution=document.querySelector('#attribution-title')?.closest('section');
 const before=(a,b)=>!!a&&!!b&&Boolean(a.compareDocumentPosition(b)&Node.DOCUMENT_POSITION_FOLLOWING);
 return {
   briefing:style(document.querySelector('[data-testid="portfolio-briefing"]')),
   heroGrid:style(hero?.closest('section')?.parentElement),
   hero:style(hero?.closest('section')),
   metricCards:[...document.querySelectorAll('[data-testid="portfolio-briefing"] article')].map(style),
   attribution:style(attribution), attributionExpanded:!!attribution&&!attribution.querySelector('details'),
   performance:style(panel), chart:style(chart),
   metricBeforeChart:tile&&chart?before(tile,chart):null,
   performancePeriods:panel?[...panel.querySelectorAll('button')].map(e=>e.textContent).filter(t=>['1M','3M','6M','1Y','YTD','ALL'].includes(t)):null,
   holdingsTableColumn:style(table?.parentElement?.parentElement),
   holdingsDetailColumn:style(empty?.parentElement?.parentElement),
   holdingsGrid:style(empty?.parentElement?.parentElement?.parentElement),
   tabs:[...document.querySelectorAll('[role="tab"]')].map(e=>({text:e.textContent,style:style(e)})),
   mobileNav:[...document.querySelectorAll('nav[aria-label="Mobile"] a')].map(e=>({text:e.textContent,style:style(e)})),
   periodSelect:style(document.querySelector('select[aria-label="Performance period"]')),
   refreshButton:style(document.querySelector('button[aria-label="Refresh data"]')),
   accountSelect:style(document.querySelector('select[aria-label="Account"]')),
   observationLedger:!!document.querySelector('table[aria-label="Exact snapshot and drawdown observations"]'),
 };
}"""


def verify(baseline, candidate, out):
    out.mkdir(parents=True, exist_ok=True)
    servers = [make_server(dist, 0) for dist in (baseline, candidate)]
    threads = [Thread(target=server.serve_forever, daemon=True) for server in servers]
    for thread in threads:
        thread.start()
    results = []
    try:
        with sync_playwright() as driver:
            browser = driver.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True, args=['--no-sandbox'])
            try:
                for width in (390, 1440):
                    for route, heading in ROUTES.items():
                        contracts = []
                        for label, server in zip(('baseline', 'candidate'), servers):
                            base = f'http://127.0.0.1:{server.server_port}'
                            context = browser.new_context(viewport={'width': width, 'height': 900}, reduced_motion='reduce')
                            forbidden, errors = [], []
                            def guard(request):
                                if request.request.url.startswith(base + '/') and request.request.method == 'GET':
                                    request.continue_()
                                else:
                                    forbidden.append(request.request.url)
                                    request.abort()
                            context.route('**/*', guard)
                            page = context.new_page()
                            page.on('pageerror', lambda error: errors.append(str(error)))
                            page.goto(base + route, wait_until='networkidle')
                            page.get_by_role('heading', name=heading, exact=True).first.wait_for()
                            if route == '/':
                                expect(page.locator('#attribution-title')).to_be_visible()
                                page.get_by_role('region', name='Snapshot performance chart').wait_for()
                            if route == '/portfolio?tab=holdings':
                                expect(page.get_by_text('Select a holding', exact=True)).to_be_visible()
                            if route == '/portfolio?tab=performance':
                                page.get_by_role('region', name='Snapshot performance chart').wait_for()
                            contracts.append(page.evaluate(CONTRACT))
                            slug = 'overview' if route == '/' else route.split('?')[0].strip('/') + '-' + route.split('=')[-1]
                            page.screenshot(path=str(out / f'{width}-{slug}-{label}.png'), full_page=True)
                            if route == '/':
                                page.screenshot(path=str(out / f'{width}-overview-{label}-viewport.png'))
                            assert not forbidden and not errors, (forbidden, errors)
                            context.close()
                        differences = {key: {'baseline': contracts[0][key], 'candidate': contracts[1][key]}
                                       for key in contracts[0] if contracts[0][key] != contracts[1][key]}
                        results.append({'width': width, 'route': route, 'differences': differences, 'contract': contracts[1]})
            finally:
                browser.close()
    finally:
        for server, thread in zip(servers, threads):
            server.shutdown(); server.server_close(); thread.join(timeout=5)
            assert not thread.is_alive()
        (out / 'production-ui-comparison.json').write_text(json.dumps(results, indent=2))
    failures = [row for row in results if row['differences']]
    print(json.dumps({'comparisons': len(results), 'failures': len(failures), 'report': str(out / 'production-ui-comparison.json')}))
    assert len(results) == 10 and not failures, 'Production layout/style differs; inspect the comparison report'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    verify(args.baseline, args.candidate, args.out)

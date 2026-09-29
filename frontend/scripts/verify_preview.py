"""Real Chrome verification against GET-only synthetic preview; no live system."""
import argparse
import json
import pathlib
import re
from urllib.parse import urlsplit, parse_qsl
from playwright.sync_api import sync_playwright, expect
from browser_metrics import VIEWPORTS, BUDGETS, ZOOM_NOTE, install_observer, capture_metrics, budget_failures, chart_fold_failure
from test_drawdown_browser import assert_drawdown_hover

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url',default='http://127.0.0.1:8794')
parser.add_argument('--out',required=True,type=pathlib.Path)
parser.add_argument('--check-local-security-redirect',action='store_true',help='Compatibility flag: local-mode security redirect is always mandatory')
args=parser.parse_args()
assert urlsplit(args.url).hostname=='127.0.0.1', 'Use only the loopback fixture preview'
args.out.mkdir(parents=True,exist_ok=True)
results=[]
ROUTES = {
 '/': 'Portfolio overview',
 '/portfolio?tab=holdings': 'Holdings',
 '/portfolio?tab=performance': 'Performance workspace',
 '/portfolio?tab=returns': 'Position analysis',
 '/portfolio?tab=allocation': 'Allocation & concentration',
 '/portfolio?tab=income': 'DRIP purchase proxy',
 '/portfolio?tab=groups': 'Groups',
 '/activity?tab=orders': 'Order history',
 '/activity?tab=changes': 'Snapshot diff',
 '/activity?tab=imports': 'Import history',
 '/activity?tab=source&source=import&record=5': 'Source record',
 '/tax': 'Capital Gains Tax',
 '/data?tab=import': 'Import data',
 '/data?tab=classifications': 'Classification queue',
 '/data?tab=matching': 'Matching health',
 '/data?tab=settings': 'Income proxy settings',
 '/data?tab=confidence': 'Data confidence',
 '/help': 'Help & site guide',
 '/demo/chart-first.html': None,
 '/demo/ledger-first.html': None,
}
with sync_playwright() as driver:
 browser=driver.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox'])
 try:
  for width,height,zoom in VIEWPORTS:
   label=f"{width}x{height}-zoom{zoom}"
   context=browser.new_context(viewport={'width':width,'height':height},device_scale_factor=zoom,reduced_motion='reduce')
   install_observer(context)
   context.route('**/*', lambda route: route.continue_() if urlsplit(route.request.url).netloc==urlsplit(args.url).netloc and route.request.method=='GET' else route.abort())
   page=context.new_page()
   page_errors=[]
   console_errors=[]
   http_errors=[]
   page.on('pageerror',lambda error:page_errors.append(str(error)))
   page.on('console',lambda message:console_errors.append(message.text) if message.type=='error' else None)
   page.on('response',lambda response:http_errors.append({'url':response.url,'status':response.status}) if response.status>=400 else None)
   for route, heading in ROUTES.items():
    page_errors.clear();console_errors.clear();http_errors.clear()
    page.goto(args.url+route);page.wait_for_load_state('networkidle')
    if heading:page.get_by_role('heading',name=heading,exact=True).first.wait_for()
    if route=='/portfolio?tab=returns':page.get_by_role('cell',name='DEMO global equity — synthetic order journey').wait_for()
    if route=='/activity?tab=orders':page.get_by_role('status').filter(has_text='of 1 matching transactions').wait_for()
    if route=='/activity?tab=source&source=import&record=5':page.get_by_role('heading',name='DEMO synthetic snapshot source').wait_for()
    if route=='/tax':
     page.get_by_role('button',name=re.compile('DEMO global equity')).click()
     page.get_by_text('Pool · 1 · £100').wait_for()
    if route in ['/data?tab=confidence','/data?tab=import']:
     evidence=page.locator('[aria-label="Refresh evidence"]').filter(has_text='Checked:')
     expect(evidence).to_contain_text('Checked: 2026-09-01T18:30:00+00:00')
     expect(evidence).to_contain_text('Attempt: 2026-09-29T18:29:00+00:00')
     expect(evidence).to_contain_text('Coverage: partial')
    metrics=capture_metrics(page)
    metric_failures=budget_failures(metrics)
    if route=='/':
     fold=chart_fold_failure(metrics,zoom=zoom)
     if fold:metric_failures.append(fold)
     expect(page.get_by_text(re.compile('Carried-forward account valuations may mask'))).to_be_visible()
     expect(page.get_by_text(re.compile('Trade-derived proxy flows are assumptions'))).to_be_visible()
    geometry=page.evaluate('''() => ({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,heading:document.querySelector('h1')?.textContent,wrappedNavLabels:[...document.querySelectorAll('nav[aria-label=Mobile] a span')].filter(el=>el.getBoundingClientRect().height>parseFloat(getComputedStyle(el).lineHeight)+1&&el.getBoundingClientRect().width>0).map(el=>el.textContent),smallTargets:[...document.querySelectorAll('button,select,summary,nav a')].filter(el=>{const r=el.getBoundingClientRect();const s=getComputedStyle(el);return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&(r.height<44||(el.tagName==='BUTTON'||el.closest('nav'))&&r.width<44)}).map(el=>({text:el.textContent,label:el.getAttribute('aria-label'),height:el.getBoundingClientRect().height,width:el.getBoundingClientRect().width})),overflow:[...document.body.querySelectorAll('*')].filter(el=>{const r=el.getBoundingClientRect();return r.width>0&&r.right>innerWidth+1&&!el.closest('[data-testid="ambient-background"]')&&!(el.tagName==='DIV'&&!el.textContent?.trim()&&el.children.length===0&&el.parentElement?.closest('[class*="overflow-hidden"]')?.getBoundingClientRect().right<=innerWidth+1)&&!el.closest('[class*="overflow-auto"]')}).slice(0,10).map(el=>({tag:el.tagName,text:el.textContent?.slice(0,80),right:el.getBoundingClientRect().right}))})''')
    results.append({'route':route,'viewport':width,'height':height,'zoom':zoom,'zoom_note':ZOOM_NOTE if zoom==2 else None,'metrics':metrics,'metric_failures':metric_failures,**geometry,'page_errors':list(page_errors),'console_errors':list(console_errors),'http_errors':list(http_errors),'loadedScripts':page.evaluate("() => performance.getEntriesByType('resource').filter(row=>row.name.split('?')[0].endsWith('.js')).map(row=>row.name)")})
    page.screenshot(path=str(args.out/f'{label}-{re.sub(r"[^a-zA-Z0-9]+","-",route).strip("-") or "overview"}.png'),full_page=True)
    if route=="/" and width<1024:page.screenshot(path=str(args.out/f"{label}-overview-viewport.png"))
    if width<1024 and route in ['/tax','/portfolio?tab=returns','/activity?tab=orders','/data?tab=confidence']:
     page.evaluate('window.scrollTo(0,0)')
     page.screenshot(path=str(args.out/f'{label}-{re.sub(r"[^a-zA-Z0-9]+","-",route).strip("-")}-viewport.png'))
     page.evaluate('window.scrollTo(0,document.documentElement.scrollHeight)')
     clearance=page.evaluate('''() => ({contentBottom:document.querySelector('[data-testid="route-content"]').getBoundingClientRect().bottom,navTop:document.querySelector('nav[aria-label="Mobile"]').getBoundingClientRect().top})''')
     results[-1]['bottomClearance']=clearance
     assert clearance['contentBottom']<=clearance['navTop']+1, f'{route} final content is obscured by mobile nav: {clearance}'
     page.screenshot(path=str(args.out/f'{label}-{re.sub(r"[^a-zA-Z0-9]+","-",route).strip("-")}-bottom.png'))
     if route=='/portfolio?tab=returns':
      table=page.locator('table').locator('..')
      scrolling=table.evaluate('''el => {const bounds=el.getBoundingClientRect();el.scrollLeft=el.scrollWidth;const last=el.querySelector('th:last-child').getBoundingClientRect();return {clientWidth:el.clientWidth,scrollWidth:el.scrollWidth,scrollLeft:el.scrollLeft,right:bounds.right,lastRight:last.right,lastLeft:last.left,left:bounds.left}}''')
      assert scrolling['scrollWidth']>scrolling['clientWidth'] and scrolling['scrollLeft']>0
      assert scrolling['lastRight']<=scrolling['right']+1 and scrolling['lastLeft']>=scrolling['left']
      results[-1]['returnsHorizontalScroll']=scrolling
      page.screenshot(path=str(args.out/f'{label}-holding-returns-horizontal-end.png'))
    (args.out/"geometry.json").write_text(json.dumps(results,indent=2))
   redirects = {'/holdings':('/portfolio','holdings'),'/positions':('/portfolio','returns'),'/groups':('/portfolio','groups'),'/orders':('/activity','orders'),'/diff':('/activity','changes'),'/import':('/data','import'),'/matching':('/data','matching'),'/cgt':('/tax',None)}
   redirects['/security']=('/',None)
   for source,(destination,tab_key) in redirects.items():
    page.goto(args.url+source);page.wait_for_load_state('networkidle')
    expect(page).to_have_url(re.compile(re.escape(args.url+destination)+r'(?:\?|$)'))
    if source=='/security':page.get_by_role('heading',name='Portfolio overview',exact=True).wait_for()
    if tab_key:assert dict(parse_qsl(urlsplit(page.url).query)).get('tab')==tab_key
   results.append({'viewport':width,'height':height,'zoom':zoom,'redirects':list(redirects),'passed':True})
   page_errors.clear();console_errors.clear();http_errors.clear()
   page.goto(args.url+'/portfolio?tab=holdings&account=DEMO+ISA&period=1Y');page.wait_for_load_state('networkidle')
   row=page.get_by_role('button',name='View DEMO-GLOBAL in DEMO ISA')
   row.click();close=page.get_by_role('button',name='Close instrument detail');close.wait_for()
   expect(close).to_be_focused()
   if width<1024:assert page.get_by_role('dialog',name='Instrument detail').get_attribute('aria-modal')=='true'
   page.screenshot(path=str(args.out/f'{label}-holding-selection.png'),full_page=width>=1024)
   close.press('Escape');expect(row).to_be_focused()
   assert 'inst=' not in page.url and 'period=1Y' in page.url
   page.get_by_role('searchbox',name='Search holdings').fill('missing-demo')
   page.get_by_text('No holdings match the active filters.').wait_for()
   page.get_by_role('button',name='Clear filters').click()
   assert 'account=DEMO' in page.url and 'period=1Y' in page.url
   tab=page.get_by_role('tab',name='Holdings');tab.focus();tab.press('ArrowRight')
   page.get_by_role('heading',name='Performance workspace').wait_for()
   page.get_by_role('table',name='Exact snapshot and drawdown observations').wait_for()
   assert page.get_by_role('table',name='Exact snapshot and drawdown observations').locator('tbody tr').count()==5
   hover=assert_drawdown_hover(page)
   page.get_by_role('button',name='Inspect observation 2026-06-01').click()
   assert '2026-06-01' in page.get_by_role('status').filter(has_text='flow-adjusted drawdown').inner_text()
   page.get_by_role('button',name='Current-price reconstruction').click()
   page.get_by_role('alert').filter(has_text='Unable to load Current-price reconstruction').wait_for()
   page.get_by_role('button',name='Snapshot history').click()
   assert page.get_by_role('heading',name='Snapshot history').is_visible()
   results.append({'viewport':width,'interaction':'selection, mobile dialog, Escape focus return, scoped clear, arrow tabs, exact five observations, dated inspection, independent history failure','passed':True,'height':height,'zoom':zoom,'drawdown_hover':hover,'page_errors':list(page_errors)})
   context.close()
 finally:browser.close()
(args.out/'geometry.json').write_text(json.dumps(results,indent=2))
print(json.dumps({"geometry_rows":sum("route" in row for row in results),"interaction_rows":sum("interaction" in row for row in results),"report":str(args.out/"geometry.json")}))
failures=[row for row in results if row.get('scrollWidth',0)>row.get('width',0) or row.get('overflow') or row.get('smallTargets') or row.get('wrappedNavLabels') or row.get('page_errors') or row.get('console_errors') or row.get('http_errors') or row.get('metric_failures')]
if failures:raise SystemExit(f'{len(failures)} geometry/error rows require attention; see geometry.json')

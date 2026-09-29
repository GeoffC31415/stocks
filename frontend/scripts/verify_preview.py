"""Real Chrome verification against GET-only synthetic preview; no live system."""
import argparse
import json
import pathlib
import re
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url',default='http://127.0.0.1:8794')
parser.add_argument('--out',required=True,type=pathlib.Path)
args=parser.parse_args()
assert urlsplit(args.url).hostname=='127.0.0.1', 'Use only the loopback fixture preview'
args.out.mkdir(parents=True,exist_ok=True)
results=[]
with sync_playwright() as driver:
 browser=driver.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox'])
 try:
  for width in [320,390,1440]:
   context=browser.new_context(viewport={'width':width,'height':1000})
   context.route('**/*', lambda route: route.continue_() if urlsplit(route.request.url).netloc==urlsplit(args.url).netloc and route.request.method=='GET' else route.abort())
   page=context.new_page()
   page_errors=[]
   page.on('pageerror',lambda error:page_errors.append(str(error)))
   for route in ['/', '/portfolio?tab=holdings', '/portfolio?tab=performance', '/portfolio?tab=groups', '/help', '/data?tab=confidence', '/demo/chart-first.html','/demo/ledger-first.html']:
    page.goto(args.url+route);page.wait_for_load_state('networkidle')
    if '/demo/' not in route:page.locator('h1,h2').first.wait_for()
    geometry=page.evaluate('''() => ({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,heading:document.querySelector('h1')?.textContent,wrappedNavLabels:[...document.querySelectorAll('nav[aria-label=Mobile] a span')].filter(el=>el.getBoundingClientRect().height>parseFloat(getComputedStyle(el).lineHeight)+1&&el.getBoundingClientRect().width>0).map(el=>el.textContent),smallTargets:[...document.querySelectorAll('button,select,summary,nav a')].filter(el=>{const r=el.getBoundingClientRect();const s=getComputedStyle(el);return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&(r.height<44||(el.tagName==='BUTTON'||el.closest('nav'))&&r.width<44)}).map(el=>({text:el.textContent,label:el.getAttribute('aria-label'),height:el.getBoundingClientRect().height,width:el.getBoundingClientRect().width})),overflow:[...document.body.querySelectorAll('*')].filter(el=>{const r=el.getBoundingClientRect();return r.width>0&&r.right>innerWidth+1&&!el.closest('[class*="overflow-auto"]')}).slice(0,10).map(el=>({tag:el.tagName,text:el.textContent?.slice(0,80),right:el.getBoundingClientRect().right}))})''')
    results.append({'route':route,'viewport':width,**geometry,'loadedScripts':page.evaluate("() => performance.getEntriesByType('resource').filter(row=>row.name.split('?')[0].endsWith('.js')).map(row=>row.name)")})
    page.screenshot(path=str(args.out/f'{width}-{re.sub(r"[^a-zA-Z0-9]+","-",route).strip("-") or "overview"}.png'),full_page=True)
    if route=="/" and width<1024:page.screenshot(path=str(args.out/f"{width}-overview-viewport.png"))
    (args.out/"geometry.json").write_text(json.dumps(results,indent=2))
   page.goto(args.url+'/portfolio?tab=holdings&account=DEMO+ISA&period=1Y');page.wait_for_load_state('networkidle')
   row=page.get_by_role('button',name='View DEMO-GLOBAL in DEMO ISA')
   row.click();close=page.get_by_role('button',name='Close instrument detail');close.wait_for()
   expect(close).to_be_focused()
   if width<1024:assert page.get_by_role('dialog',name='Instrument detail').get_attribute('aria-modal')=='true'
   page.screenshot(path=str(args.out/f'{width}-holding-selection.png'),full_page=width>=1024)
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
   page.get_by_role('button',name='Inspect observation 2026-06-01').click()
   assert '2026-06-01' in page.get_by_role('status').filter(has_text='flow-adjusted drawdown').inner_text()
   page.get_by_role('button',name='Current-price reconstruction').click()
   page.get_by_role('alert').filter(has_text='Unable to load Current-price reconstruction').wait_for()
   page.get_by_role('button',name='Snapshot history').click()
   assert page.get_by_role('heading',name='Snapshot history').is_visible()
   results.append({'viewport':width,'interaction':'selection, mobile dialog, Escape focus return, scoped clear, arrow tabs, exact five observations, dated inspection, independent history failure','passed':True,'page_errors':page_errors})
   context.close()
 finally:browser.close()
(args.out/'geometry.json').write_text(json.dumps(results,indent=2))
print(json.dumps({"geometry_rows":sum("route" in row for row in results),"interaction_rows":sum("interaction" in row for row in results),"report":str(args.out/"geometry.json")}))
failures=[row for row in results if row.get('scrollWidth',0)>row.get('width',0) or row.get('smallTargets') or row.get('wrappedNavLabels') or row.get('page_errors')]
if failures:raise SystemExit(f'{len(failures)} geometry/error rows require attention; see geometry.json')

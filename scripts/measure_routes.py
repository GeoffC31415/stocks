"""Read-only route timing rehearsal; run unchanged before and after."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument('--repo', type=Path, required=True)
parser.add_argument('--database', type=Path, required=True)
parser.add_argument('--dist', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
a = parser.parse_args()
sys.path.insert(0, str(a.repo / 'scripts'))
spec = importlib.util.spec_from_file_location('rehearsal', a.repo / 'scripts/verify_analysis_ui.py')
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)
from ui_contracts import ROUTES, request_allowed
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
base = f'http://127.0.0.1:{port}'
original = hashlib.sha256(a.database.read_bytes()).hexdigest()
report = []
with a.output.with_suffix('.log').open('w') as log:
    server = subprocess.Popen([sys.executable, str(a.repo / 'scripts/verify_analysis_ui.py'), '--database', str(a.database), '--dist', str(a.dist), '--serve', str(port)], stdout=log, stderr=log, env={**os.environ, 'PORTFOLIO_DATABASE_URL':'sqlite+aiosqlite:///:memory:'})
    try:
        harness.wait_ready(server, base)
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True, args=['--no-sandbox'])
            try:
                for width in (390, 1440):
                    for view, contract in ROUTES.items():
                        for trial in range(3):
                            page = browser.new_page(viewport={'width':width,'height':1000}, reduced_motion='reduce')
                            errors = []
                            page.on('pageerror', lambda e: errors.append(str(e)))
                            page.add_init_script("window.__cls=0; new PerformanceObserver(l => { for (const x of l.getEntries()) if (!x.hadRecentInput) window.__cls+=x.value; }).observe({type:'layout-shift',buffered:true});")
                            def guard(route):
                                r=route.request
                                if request_allowed(r.method,r.url,base,view): route.continue_()
                                elif r.url.startswith('https://fonts.googleapis.com/'): route.fulfill(status=200,content_type='text/css',body='')
                                else: errors.append('blocked '+r.method+' '+r.url);route.abort()
                            page.route('**/*',guard)
                            page.goto(base+contract['url'],wait_until='networkidle')
                            page.get_by_role('heading',name=contract['heading'],exact=True).wait_for()
                            data=page.evaluate("""() => ({cls:window.__cls, requests:performance.getEntriesByType('resource').filter(r=>r.name.includes('/api/')).map(r=>({path:new URL(r.name).pathname, duration:r.duration})), height:document.documentElement.scrollHeight, width:document.documentElement.scrollWidth})""")
                            report.append({'route':view,'width':width,'trial':trial,**data,'errors':errors})
                            page.close()
            finally: browser.close()
    finally:
        server.terminate()
        try: server.wait(timeout=5)
        except subprocess.TimeoutExpired: server.kill();server.wait(timeout=5)
assert hashlib.sha256(a.database.read_bytes()).hexdigest()==original
assert all(not r['errors'] for r in report), 'Page/network errors'
a.output.write_text(json.dumps(report,indent=2))
print(f'{len(report)} route timing samples; source unchanged; {a.output}')

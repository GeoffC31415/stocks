"""Real Chromium read-only R3 journeys; import verify_r3_navigation after matrix.
Synthetic scenario is explicitly browser-only; every other payload is copied DB.
"""
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import json
import re
import traceback
from ui_contracts import allowed_gets
from starlette.routing import compile_path


def verify_r3_navigation(browser, base, output, width):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    result = {"width": width, "checks": [], "failures": [], "blocked": [], "errors": [], "requests": []}
    patterns = [compile_path(p)[0] for p in allowed_gets()]
    def journey(name, fn, synthetic=False):
        page = browser.new_page(viewport={"width": width, "height": 1000}, reduced_motion="reduce", has_touch=width <= 390)
        page.set_default_timeout(6000)
        state = {"delay": False, "held": [], "payloads": {}, "synthetic": synthetic}
        def guard(route):
            req = route.request
            u = urlsplit(req.url)
            if req.method == "GET" and req.url.startswith("https://fonts.googleapis.com/"):
                route.fulfill(status=200, content_type="text/css", body="")
                return
            if req.method != "GET" or u.netloc != urlsplit(base).netloc or u.scheme != "http" or (u.path.startswith('/api/') and not any(p.fullmatch(u.path) for p in patterns)):
                result["blocked"].append({"journey": name, "method": req.method, "url": req.url})
                route.abort()
                return
            if synthetic and u.path == '/api/portfolio/allocation-targets':
                route.fulfill(json=TARGET)
            elif synthetic and u.path == '/api/portfolio/allocation-scenario':
                state['scenario_query'] = parse_qs(u.query)
                route.fulfill(json={"before": TARGET, "after": {**TARGET, "invested_value_gbp": 150, "groups": [{**TARGET['groups'][0], "actual_value_gbp":150}]}, "assumption": "SYNTHETIC browser-only contribution; no orders created."})
            elif state['delay'] and u.path == '/api/orders/page':
                state['held'].append(route)
            else:
                route.continue_()
        def received(response):
            p = urlsplit(response.url).path
            if p.startswith('/api/'):
                result['requests'].append({'journey':name,'url':response.url,'status':response.status})
                if response.status == 200:
                    try:
                        state['payloads'][p] = response.json()
                    except Exception:
                        pass
        page.route('**/*', guard)
        page.on('response', received)
        page.on('pageerror', lambda e: result['errors'].append(str(e)))
        try:
            evidence = fn(page, state)
            result['checks'].append({'name':name,'status':'passed','synthetic':synthetic,'evidence':evidence})
        except Exception as exc:
            result['failures'].append(name + ': ' + str(exc))
            result['checks'].append({'name':name,'status':'failed','synthetic':synthetic,'url':page.url,'error':str(exc),'traceback':traceback.format_exc(),'dom':page.locator('main').inner_text()[:14000], 'payloads':state['payloads']})
        finally:
            for route in state['held']:
                try: route.abort()
                except Exception: pass
            page.close()
    def goto(page, path):
        page.goto(base + path, wait_until='networkidle', timeout=20000)
    def qs(url): return {k:v[0] for k,v in parse_qs(urlsplit(url).query).items()}
    def detail(page):
        panel = page.get_by_role('dialog' if width <= 390 else 'region', name='Instrument detail', exact=True)
        panel.wait_for(state='visible')
        page.get_by_role('link', name='View matching orders', exact=True).wait_for()
        return panel
    def orders(page, state):
        page.get_by_role('region', name='Order results', exact=True).wait_for()
        page.wait_for_load_state('networkidle')
        data = state['payloads']['/api/orders/page']
        assert data['items'], 'Matching orders must be nonempty'
        return data
    def allocation(page, state):
        goto(page, '/portfolio?tab=allocation&account=all&period=1Y')
        page.get_by_role('table', name='By asset class', exact=True).wait_for()
        data=state['payloads']['/api/portfolio/allocation']
        link=page.locator('a[href*="allocation_category="]').first
        h=qs(link.get_attribute('href'))
        expected=sorted(data['category_instruments'][h['allocation_category']])
        assert sorted(map(int,h['instrument_ids'].split(',')))==expected
        assert h['allocation_dimension']=='asset_class'
        link.click()
        page.locator('[data-holding-id]').first.wait_for()
        page.wait_for_load_state('networkidle')
        actual=sorted(map(int,page.locator('[data-holding-id]').evaluate_all('(els)=>els.map(e=>e.dataset.holdingId)')))
        assert actual==expected, (actual,expected)
        row=page.locator('[data-holding-id]').first
        iid=row.get_attribute('data-holding-id')
        baseline=qs(page.url)
        for close in ('button','escape'):
            row.click(); detail(page)
            assert qs(page.url)['inst']==iid
            if close=='button': page.get_by_role('button', name='Close instrument detail').click()
            else: page.keyboard.press('Escape')
            page.wait_for_function('(id)=>document.activeElement?.dataset.holdingId===id',arg=iid)
            assert qs(page.url)==baseline, 'Closing changed filters'
        row.click(); detail(page)
        page.go_back(); page.locator('[data-holding-id]').first.wait_for()
        assert 'inst' not in qs(page.url)
        page.go_forward(); detail(page)
        assert qs(page.url)['inst']==iid
        page.get_by_role('button', name='Close instrument detail').click()
        return {'category':h['allocation_category'],'exact_ids':expected,'focus_close_escape':True,'back_forward':True}
    def account(page,state):
        goto(page,'/portfolio?tab=holdings&account=all')
        page.locator('[data-holding-id]').first.wait_for()
        page.wait_for_load_state('networkidle')
        instruments=state['payloads']['/api/instruments']
        accounts=sorted({i['account_name'] for i in instruments})
        assert len(accounts)>1,'Need multiple fixture accounts'
        item=next(i for i in instruments if not i.get('is_cash'))
        other=next(a for a in accounts if a!=item['account_name'])
        page.locator(f'[data-holding-id="{item["id"]}"]').click();detail(page)
        page.wait_for_load_state('networkidle')
        # Close overlay, switch actual topbar account, then restore out-of-scope ID
        page.get_by_role('button',name='Close instrument detail').click()
        page.wait_for_function('!new URL(location.href).searchParams.has("inst")')
        start=len(result['requests'])
        if width<=390: page.get_by_role('combobox',name='Account',exact=True).select_option(other)
        else: page.locator('header').get_by_role('button',name=other,exact=True).click()
        page.wait_for_load_state('networkidle')
        target=page.evaluate('(id)=>{const u=new URL(location.href);u.searchParams.set("inst",id);return u.href}',str(item['id']))
        page.goto(target,wait_until='networkidle')
        page.get_by_role('alert').filter(has_text='Instrument not available in the selected account').wait_for()
        assert not any(re.search(r'/api/instruments/\d+/(history|orders)',r['url']) for r in result['requests'][start:]),'Out-of-scope detail fetched'
        return {'out_of_scope_id':item['id'],'account':other,'history_fetches':0}
    def contributor(page,state):
        goto(page,'/?account=all&period=ALL')
        link=page.locator('a[href*="tab=changes"][href*="inst="]').first
        link.wait_for()
        expected=qs(link.get_attribute('href'))
        assert all(k in expected for k in ('from','to','inst'))
        link.click()
        explore=page.get_by_role('link',name=re.compile('^Explore .* holding$')).first
        explore.wait_for()
        assert all(qs(page.url).get(k)==expected[k] for k in ('from','to','inst'))
        explore.click();detail(page)
        holding_url=page.url
        assert all(qs(page.url).get(k)==expected[k] for k in ('from','to','inst'))
        page.get_by_role('link',name='View matching orders',exact=True).click()
        data=orders(page,state)
        assert all(str(x['instrument_id'])==expected['inst'] for x in data['items'])
        page.go_back();detail(page)
        assert page.url==holding_url
        return {'comparison':{k:expected[k] for k in ('from','to','inst')},'order_count':data['total_count'],'back_restores_holding':True}
    def income(page,state,prior):
        goto(page,'/portfolio?tab=income&account=all')
        page.get_by_role('heading',name='Holding contributions to the change').wait_for()
        data=state['payloads']['/api/orders/income']
        evidence=[]
        for prior in (prior,):
            field='prior_recorded_gbp' if prior else 'current_recorded_gbp'
            row=next(d for d in data['drivers'] if d['instrument_id'] is not None and (d[field] or 0)>0)
            li=page.locator('li').filter(has=page.get_by_role('link',name=row['name']+' matching purchases',exact=True))
            link=li.get_by_role('link',name='Prior-period purchases',exact=True) if prior else li.get_by_role('link',name=row['name']+' matching purchases',exact=True)
            expected=qs(link.get_attribute('href'))
            assert expected['kind']=='drip'
            assert expected['from_date']==data['prior_start' if prior else 'current_start']
            assert expected['to_date']==data['prior_end' if prior else 'as_of']
            # Independently prove stored-order scope before following the actual link.
            probe=page.evaluate('async (p)=>{const q=new URLSearchParams({account_name:p.account,instrument_ids:p.inst,kind:p.kind,from_date:p.from_date,to_date:p.to_date,limit:"100",offset:"0"});const r=await fetch("/api/orders/page?"+q);if(!r.ok)throw Error("Order scope probe "+r.status);return r.json()}',expected)
            assert probe['items'], 'Income scope has no matching stored orders'
            assert all(x['is_drip'] and x['instrument_id']==row['instrument_id'] and x['account_name']==row['account_name'] and expected['from_date']<=x['order_date'][:10]<=expected['to_date'] for x in probe['items'])
            link.click(); payload=orders(page,state)
            for item in payload['items']:
                assert item['instrument_id']==row['instrument_id']
                assert item['account_name']==row['account_name']
                assert item['is_drip'] is True
                assert expected['from_date']<=item['order_date'][:10]<=expected['to_date']
            evidence.append({'prior':prior,'count':payload['total_count'],'scope':expected})
            page.go_back();page.get_by_role('heading',name='Holding contributions to the change').wait_for()
        return evidence
    def pagination(page,state):
        goto(page,'/activity?tab=orders&account=all&kind=all&from_date=2000-01-01&to_date=2099-12-31')
        first=orders(page,state)
        assert first['has_more'] and first['total_count']>100
        text=page.get_by_text('Full-filter totals (not just this page):',exact=False).inner_text()
        first_rows=page.get_by_role('region',name='Order results',exact=True).inner_text()
        state['delay']=True
        page.get_by_role('button',name='Next page',exact=True).click()
        page.get_by_role('status').filter(has_text='Loading matching transactions').wait_for()
        assert page.get_by_role('region',name='Order results',exact=True).count()==0,'Stale rows while fetching'
        assert page.get_by_text('Full-filter totals (not just this page):',exact=False).count()==0,'Stale totals while fetching'
        assert state['held'],'No delayed request intercepted'
        state['delay']=False
        for r in state['held']: r.continue_()
        state['held']=[]
        second=orders(page,state)
        assert second['offset']==first['limit']
        assert second['totals']==first['totals'] and second['total_count']==first['total_count']
        assert not ({x['id'] for x in first['items']}&{x['id'] for x in second['items']})
        assert page.get_by_text('Full-filter totals (not just this page):',exact=False).inner_text()==text
        page.wait_for_function('document.activeElement?.getAttribute("aria-label")==="Order results"')
        page.get_by_role('button',name='Previous page',exact=True).click()
        page.get_by_role('status').filter(has_text=f'Showing 1–{first["limit"]} of').wait_for()
        page.wait_for_function('(text)=>document.querySelector("[aria-label=\\"Order results\\"]")?.innerText===text',arg=first_rows)
        assert qs(page.url)['offset']=='0'
        assert page.get_by_text('Full-filter totals (not just this page):',exact=False).inner_text()==text
        return {'total_count':first['total_count'],'totals':first['totals'],'delayed_rows_hidden':True,'results_focused':True}
    def targets(page,state):
        goto(page,'/portfolio?tab=allocation&account=all')
        link=page.get_by_role('link',name='Resolve target configuration',exact=True)
        link.wait_for()
        assert state['payloads']['/api/portfolio/allocation-targets']['status']=='unavailable'
        assert urlsplit(link.get_attribute('href')).path=='/portfolio' and qs(link.get_attribute('href'))['tab']=='groups'
        link.click();page.wait_for_load_state('networkidle')
        assert urlsplit(page.url).path=='/portfolio' and qs(page.url)['tab']=='groups'
        page.get_by_role('heading',name=re.compile('Groups')).first.wait_for()
        return {'resolution_url':page.url,'mutations_clicked':False}
    def scenario(page,state):
        goto(page,'/portfolio?tab=allocation&account=all')
        page.get_by_label('Contribution (GBP)',exact=True).fill('50')
        page.get_by_label('Synthetic core allocation (GBP)',exact=True).fill('50')
        page.get_by_role('button',name='Calculate scenario',exact=True).click()
        region=page.get_by_role('region',name='Scenario results',exact=True)
        region.wait_for()
        assert '£150' in region.inner_text()
        payload=json.loads(state['scenario_query']['scenario'][0])
        assert payload=={'contribution_gbp':50,'allocations':[{'group_id':1,'amount_gbp':50}],'cash_policy':'excluded'}
        page.get_by_role('button',name='Reset scenario',exact=True).click()
        assert region.count()==0
        assert page.get_by_label('Contribution (GBP)',exact=True).input_value()=='0'
        return {'fixture':'browser route.fulfill only','submitted':payload,'reset_clears_results':True}
    for name,fn in [('allocation-holdings-close-history',allocation),('account-out-of-scope',account),('contributor-comparison-holding-orders',contributor),('income-current-orders',lambda p,s:income(p,s,False)),('income-prior-orders',lambda p,s:income(p,s,True)),('orders-pagination-delay-focus',pagination),('invalid-target-resolution',targets)]:
        journey(name,fn)
    journey('synthetic-scenario-form',scenario,True)
    if result['blocked'] or result['errors'] or any(r['status']>=400 for r in result['requests']): result['failures'].append('browser/API/allowlist errors')
    (output/f'r3-navigation-{width}.json').write_text(json.dumps(result,indent=2))
    return result

TARGET={'status':'available','account_name':None,'invested_value_gbp':100,'excluded_cash_gbp':25,'tolerance_pp':2,'target_sum_tolerance_pp':0.01,'cash_policy':'Cash excluded','reasons':[], 'groups':[{'group_id':1,'name':'Synthetic core','instrument_ids':[1],'actual_value_gbp':100,'actual_weight_pct':100,'target_weight_pct':100,'drift_pp':0,'gap_gbp':0,'within_tolerance':True}]}

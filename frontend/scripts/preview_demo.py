"""Loopback-only, synthetic, GET-only built-frontend preview. No upstream proxy."""
import argparse
import json
import pathlib
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

DATES = ['2026-01-01','2026-03-01','2026-06-01','2026-08-01','2026-09-01']
VALUES = [100,104,101,107,106.2]
SCOPE = dict(account_name='DEMO ISA',requested_start=None,requested_end=None,effective_start=DATES[0],effective_end=DATES[-1],valuation_dates=[dict(account_name='DEMO ISA',date=DATES[-1])],warnings=['DEMO synthetic observations. Carried-forward valuations may mask account changes.'])
INSTRUMENTS = [dict(id=i,identifier=f'DEMO-{i}',security_name=name,ticker=ticker,account_name='DEMO ISA',group_ids=[1] if i==1 else [],is_cash=False,is_closed=False,asset_class='Equity',sector='Diversified',region='Global',latest_value_gbp=value,latest_book_cost_gbp=value-1000,pnl_gbp=1000,pnl_pct=5,delta_value_gbp_since_prev_snapshot=250,latest_pct_change=None,drawdown_from_peak_pct=None,quantity_unchanged_snapshot_count=1,latest_quantity=100,source_currency='GBP') for i,name,ticker,value in [(1,'Global equity DEMO with a deliberately long security name','DEMO-GLOBAL',95400),(2,'Bond fund DEMO','DEMO-BOND',20000)]]
PERF = dict(period='ALL',coverage_start=DATES[0],period_start=DATES[0],period_end=DATES[-1],start_value_gbp=100000,end_value_gbp=106200,total_return_pct=6.2,annualised_return_pct=None,annualised_volatility_pct=None,sharpe_ratio=None,sortino_ratio=None,max_drawdown_pct=-2.884615,max_drawdown_raw_pct=-2.884615,best_period_return_pct=5.94,worst_period_return_pct=-2.88,num_periods=4,annualisation_factor=None,risk_free_annual_pct=0,method='DEMO Modified Dietz',notes=[],benchmarks=[],scope=SCOPE,growth_curve=[dict(as_of_date=date,value_gbp=value*1000,normalized_value=value) for date,value in zip(DATES,VALUES)],flow_adjusted_curve=[dict(date=date,index=value) for date,value in zip(DATES,VALUES)],drawdown_curve=[dict(date=date,index=value,drawdown_pct=dd,at_peak=dd==0) for date,value,dd in zip(DATES,VALUES,[0,0,-2.884615,0,-.747664])],drawdown_episodes=[])
PERF['flow_adjusted']=dict(contributions_gbp=5000,withdrawals_gbp=0,net_external_flow_gbp=5000,total_return_pct=6.2,annualised_return_pct=None,annualised_volatility_pct=None,sharpe_ratio=None,sortino_ratio=None,max_drawdown_pct=-2.884615,num_periods=4,annualisation_factor=None,method='DEMO Modified Dietz',notes=['Trade proxies used in this synthetic fixture.'])
SUMMARY=dict(as_of_date=DATES[-1],import_batch_id=5,position_count=2,total_value_gbp=125400,total_book_cost_gbp=110000,total_pnl_gbp=15400,cash_value_gbp=10000,by_account={'DEMO ISA':125400},by_group={'Core DEMO':95400},allocation=[dict(label='Equity DEMO',value_gbp=115400,weight_pct=100)],group_allocation=[],worst_pct=[],best_pct=[],scope=SCOPE)
CONFIDENCE=dict(scope=SCOPE,evaluated_on='2026-09-29',stale_after_days=14,snapshots=[dict(account_name='DEMO ISA',date=DATES[-1],age_days=28)],transactions=dict(count=0,first_date=None,last_date=None,unmatched_count=0,review_count=0,completeness='unknown'),classification={},market_history=dict(covered_value_gbp=0,non_cash_value_gbp=115400,covered_pct=0,aligned_observations=0,cache_gate_met=False,validation_pending=True,reasons=['DEMO provider validation unavailable.']),metric_reasons=[],attention=[])
FIXTURES={
 '/api/auth/session':dict(mode='local',authenticated=True,passkey_authenticated=False,can_register=False,expires_at=None),
 '/api/portfolio/summary':SUMMARY,
 '/api/portfolio/performance':PERF,
 '/api/portfolio/timeseries':[dict(as_of_date=date,total_value_gbp=value*1000,total_book_cost_gbp=100000) for date,value in zip(DATES,VALUES)],
 '/api/portfolio/data-confidence':CONFIDENCE,
 '/api/instruments':INSTRUMENTS,
 '/api/instruments/1/history':[], '/api/instruments/2/history':[], '/api/instruments/1/orders':[], '/api/instruments/2/orders':[],
 '/api/groups':[dict(id=1,name='Core DEMO',color=None,target_allocation_pct=None)],
 '/api/portfolio/allocation-targets':dict(status='unavailable',account_name='DEMO ISA',invested_value_gbp=115400,excluded_cash_gbp=10000,tolerance_pp=2,target_sum_tolerance_pp=.01,cash_policy='Cash excluded',reasons=['DEMO target configuration unavailable.'],groups=[]),
 '/api/matching/summary':dict(orders_total=0,orders_matched=0,orders_unmatched=0,orders_review=0),
 '/api/portfolio/attribution':dict(from_batch=dict(id=4,as_of_date='2026-08-01'),to_batch=dict(id=5,as_of_date='2026-09-01'),opening_value_gbp=124150,closing_value_gbp=125400,raw_value_change_gbp=1250,contributions_gbp=500,withdrawals_gbp=0,drip_proxy_gbp=0,net_external_flow_gbp=500,residual_market_movement_gbp=750,reconciliation_difference_gbp=0,top_contributors=[],top_detractors=[],notes=['DEMO attribution estimate; not a measured investment return.']),
 '/api/sync/status':dict(manual_sync_enabled=False,service_trigger_enabled=False,accounts=[],stale_after_days=14,running=False,next_run_at=None,schedule='DEMO disabled',last_run=json.loads((pathlib.Path(__file__).parents[1]/'src/components/__tests__/fixtures/public-sync-v2.json').read_text())),
 '/api/trading212/status':dict(configured=False,account_name='DEMO ISA'),
 '/api/imports':[],
}
# Explicit synthetic populated Tax/Activity/returns fixtures, not broker observations.
DEMO_NAME = 'DEMO global equity — synthetic order journey'
DEMO_ORDER = dict(id=1,security_name=DEMO_NAME,instrument_id=1,instrument=dict(id=1,security_name=DEMO_NAME,identifier='DEMO-1'),order_date='2026-08-01T12:00:00',order_status='Executed',account_name='DEMO ISA',side='Buy',quantity=10,cost_proceeds_gbp=1000,cost_proceeds_gbp_reason=None,country='GB',is_drip=False,match_status='matched',match_method='synthetic',match_confidence=1,matched_at=None)
DEMO_SALE = dict(order_id=2,order_date='2026-09-01',quantity=1,proceeds_gbp=120,total_cost=100,realised_gain=20,matches=[dict(source='pool',quantity=1,cost=100,proceeds=120)],pool_quantity_before=10,pool_cost_before=1000)
FIXTURES.update({
 '/api/portfolio/returns':dict(period_start=DATES[0],period_end=DATES[-1],start_value_gbp=None,end_value_gbp=None,contributions_gbp=None,withdrawals_gbp=None,net_external_flow_gbp=None,absolute_gain_after_flows_gbp=None,modified_dietz_return_pct=None,annualised_return_pct=None,method='DEMO unavailable',notes=['DEMO independent money-weighted return not supplied.']),
 '/api/orders/unlinked':dict(count=0,orders=[]),
 '/api/portfolio/allocation':dict(dimension='asset_class',group_by='security',account_name='DEMO ISA',cash_policy='excluded_all_dimensions',denominator_description='DEMO intentionally empty allocation response for empty-state geometry only.',totalValue=0,top1Pct=0,top5Pct=0,hhi=0,categories=[],holdings=[],classification=dict(holding_count=0,classified_count=0,classified_count_pct=0,total_value_gbp=0,classified_value_gbp=0,classified_value_pct=0)),
 '/api/orders/page':dict(items=[DEMO_ORDER],total_count=1,offset=0,limit=100,has_more=False,totals=dict(buy_gbp=1000,sell_gbp=0,drip_gbp=0),totals_reasons=dict(buy_gbp=None,sell_gbp=None,drip_gbp=None),classification_basis='DEMO stored synthetic classification'),
 '/api/orders/analytics':dict(total_orders=1,total_buy_gbp=1000,total_drip_gbp=0,total_sell_gbp=0,cash_deployed_gbp=1000,net_cash_invested_gbp=1000,drip_count=0,buy_count=1,sell_count=0,drip_threshold_gbp=100,annual_drip=[],first_order_date='2026-08-01'),
 '/api/orders/positions':[dict(security_name=DEMO_NAME,is_closed=False,discretionary_buy_gbp=1000,total_drip_gbp=0,total_sell_gbp=0,net_cost_gbp=1000,current_value_gbp=1100,estimated_pnl_gbp=100,realized_pnl_gbp=None,annualised_return_pct=None,order_count=1,drip_count=0,first_order_date='2026-08-01')],
 '/api/groups/performance':[],
 '/api/cgt/summary':dict(instruments=[dict(instrument_id=1,security_name=DEMO_NAME,identifier='DEMO-1',account_name='DEMO ISA',is_exempt=True,total_proceeds_gbp=120,total_cost_gbp=100,total_gain_gbp=20,total_loss_gbp=0,net_gain_gbp=20,tax_year_summaries=[],sales=[DEMO_SALE])],tax_year_totals=[dict(tax_year='2026/27',taxable_proceeds=0,taxable_cost=0,taxable_gain=0,taxable_loss=0,annual_exempt_amount=None,gain_after_exemption=None,exempt_proceeds=120,exempt_cost=100,exempt_gain=20,exempt_loss=0,gain_count=1,loss_count=0,instrument_count=1,exempt_count=1)]),
 '/api/imports':[dict(id=i,as_of_date=date,created_at=date+'T12:00:00',filename='DEMO synthetic snapshot',row_count=2) for i,date in [(4,'2026-08-01'),(5,'2026-09-01')]],
 '/api/imports/diff':dict(rows=[]),
 '/api/matching/summary':dict(orders_total=1,orders_matched=1,orders_unmatched=0,orders_auto_review=0,instruments_with_reconciliation_issues=0),
 '/api/orders/income':dict(basis='DEMO synthetic stored reinvestment proxy',account_name='DEMO ISA',as_of='2026-09-29',current_start='2026-01-01',prior_start='2025-01-01',prior_end='2025-09-29',first_transaction_date='2026-08-01',latest_transaction_date='2026-08-01',completeness='unknown',current_recorded_gbp=0,prior_recorded_gbp=None,change_gbp=None,current_count=0,prior_count=0,warnings=['DEMO income coverage unknown.'],months=[],drivers=[]),
 '/api/portfolio/timeline/source/import/5':dict(source_type='import',source_id=5,title='DEMO synthetic snapshot source',occurred_at='2026-09-01T12:00:00',valuation_date='2026-09-01',account_names=['DEMO ISA'],instrument_id=None,amount_gbp=None,details={'fixture':'Synthetic only'},note='DEMO record, not a real import.'),
})
BANNER='<div style="padding:12px;background:#78350f;color:#fef3c7;font:600 14px system-ui">DEMO / SYNTHETIC DATA — isolated GET-only preview. No broker or database connection. Production UI preservation candidate; not a deployment.</div>'
class Handler(SimpleHTTPRequestHandler):
 def send_json(self,body,status=200):
  raw=json.dumps(body).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 def do_GET(self):
  url=urlsplit(self.path);path=url.path
  if path.startswith('/api/'):
   if path in FIXTURES:return self.send_json(FIXTURES[path])
   return self.send_json({'detail':'No synthetic fixture for this read. No live request was made.'},404)
  target=pathlib.Path(self.translate_path(path))
  if target.is_file() and target.suffix!='.html':return super().do_GET()
  if target.is_file() and target.suffix=='.html':raw=target.read_text()
  elif '.' not in pathlib.Path(path).name:raw=(pathlib.Path(self.directory)/'index.html').read_text()
  else:return self.send_error(404,'Preview asset not found')
  if '/demo/' not in path:raw=raw.replace('<body>','<body>'+BANNER)
  encoded=raw.encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(encoded)));self.end_headers();self.wfile.write(encoded)
 def mutation(self):return self.send_json({'detail':'DEMO preview rejects all mutations.'},405)
 do_POST=do_PATCH=do_PUT=do_DELETE=mutation
 def log_message(self,*args):pass

def make_server(root,port):
 return ThreadingHTTPServer(('127.0.0.1',port),partial(Handler,directory=str(root)))
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--dist',required=True,type=pathlib.Path);parser.add_argument('--port',type=int,default=8794);args=parser.parse_args()
 if not (args.dist/'index.html').is_file():parser.error('Build into an isolated directory first.')
 server=make_server(args.dist,args.port)
 print(f'DEMO preview: http://127.0.0.1:{server.server_port} (GET-only synthetic fixture data)',flush=True)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close()

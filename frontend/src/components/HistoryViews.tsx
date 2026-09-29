import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import { ChartPanel, type ChartTab } from './ChartPanel';
export function HistoryViews({account,dripThreshold}:{account?:string;dripThreshold:number}) {
 const [view,setView]=useState<ChartTab>('value');
 const snapshots=useQuery({queryKey:['timeseries',account??'all'],queryFn:()=>api.getTimeseries(account),enabled:view==='value'});
 const cash=useQuery({queryKey:['cashflow',dripThreshold,account??'all'],queryFn:()=>api.getCashflowTimeseries(dripThreshold,account),enabled:view!=='value'});
 const orders=useQuery({queryKey:['order-analytics',dripThreshold,account??'all'],queryFn:()=>api.getOrderAnalytics(dripThreshold,account),enabled:view==='estimated'});
 const hasOrders=(orders.data?.total_orders??0)>0;
 const estimated=useQuery({queryKey:['estimated-timeseries',account??'all'],queryFn:()=>api.getEstimatedTimeseries(account),enabled:view==='estimated'&&hasOrders});
 const active=view==='value'?[snapshots]:view==='deployment'?[cash]:hasOrders?[cash,orders,estimated]:[cash,orders];
 const error=active.some(q=>q.isError),pending=active.some(q=>q.isPending);
 const label=view==='value'?'Snapshot history':view==='deployment'?'Capital deployment':'Current-price reconstruction';
 return <section className="space-y-3">
  <ChartPanel view={view} onViewChange={setView} hasOrders={true} cashflow={error||pending?[]:cash.data??[]} timeseries={view==='value'&&!error&&!pending?snapshots.data??[]:[]} estimatedTimeseries={error||pending?[]:estimated.data??[]} unavailable={error||pending} />
  {error?<div role="alert"><p>Unable to load {label}. Other history views remain independent.</p><button type="button" onClick={()=>active.forEach(q=>void q.refetch())}>Retry {label}</button></div>:pending?<p role="status">Loading {label}…</p>:view==='estimated'&&!hasOrders?<p>No recorded orders to reconstruct holdings.</p>:null}
 </section>;
}

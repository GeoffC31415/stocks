import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
beforeEach(()=>{let value:string|null=null;vi.stubGlobal('localStorage',{getItem:()=>value,setItem:(_k:string,v:string)=>{value=v;}});});
import { TargetDriftPanel } from '../TargetDriftPanel';
import { AllocationScenarioPanel } from '../AllocationScenarioPanel';
import { Groups } from '../../routes/Groups';
import { api } from '../../lib/api';
vi.mock('../../lib/api',async original=>({...await original<typeof import('../../lib/api')>(),api:{getInstruments:vi.fn().mockResolvedValue([]),getGroups:vi.fn().mockResolvedValue([]),createGroup:vi.fn().mockResolvedValue({id:3,name:'New tag',target_allocation_pct:null})}}));
const before={status:'available',account_name:null,invested_value_gbp:100,excluded_cash_gbp:25,tolerance_pp:2,target_sum_tolerance_pp:0.01,cash_policy:'Cash excluded',reasons:[],groups:[{group_id:1,name:'Core',actual_value_gbp:100,actual_weight_pct:100,target_weight_pct:100,drift_pp:0,gap_gbp:0,within_tolerance:true,instrument_ids:[1]}]};
const response=(data:unknown)=>({ok:true,json:async()=>data});
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.clearAllMocks();});
function setup(children:React.ReactNode){const client=new QueryClient({defaultOptions:{queries:{retry:false}}});render(<QueryClientProvider client={client}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>);return client;}
async function submit(){fireEvent.change(await screen.findByLabelText('Contribution (GBP)'),{target:{value:'50'}});fireEvent.change(screen.getByLabelText('Core allocation (GBP)'),{target:{value:'50'}});fireEvent.click(screen.getByRole('button',{name:'Calculate scenario'}));}
it('tolerance edits update sibling prerequisites and clear results',async()=>{
 const requests:string[]=[];
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>{requests.push(String(url));if(String(url).includes('allocation-scenario'))return response({before,after:{...before,invested_value_gbp:150},assumption:'Hypothetical contribution; no orders created.'});const tolerance=Number(new URL(String(url),'http://test').searchParams.get('tolerance_pp'));return response({...before,tolerance_pp:tolerance});}));
 setup(<><TargetDriftPanel/><AllocationScenarioPanel/></>);
 await submit();await screen.findByRole('table',{name:'Before and hypothetical after'});
 fireEvent.change(screen.getByLabelText('Target drift tolerance'),{target:{value:'12'}});
 await waitFor(()=>expect(requests.some(x=>x.includes('allocation-targets')&&x.includes('tolerance_pp=12'))).toBe(true));
 await waitFor(()=>expect(screen.queryByRole('table',{name:'Before and hypothetical after'})).not.toBeInTheDocument());
 fireEvent.change(screen.getByLabelText('Contribution (GBP)'),{target:{value:'60'}});
 fireEvent.change(screen.getByLabelText('Core allocation (GBP)'),{target:{value:'60'}});
 fireEvent.click(screen.getByRole('button',{name:'Calculate scenario'}));
 await waitFor(()=>expect(requests.filter(x=>x.includes('allocation-scenario'))).toHaveLength(2));
 expect(new URL(requests.filter(x=>x.includes('allocation-scenario'))[1],'http://test').searchParams.get('tolerance_pp')).toBe('12');
});
it('adding a group refreshes target prerequisites',async()=>{
 const fetcher=vi.fn(async()=>response(before));vi.stubGlobal('fetch',fetcher);
 setup(<Groups/>);await screen.findByRole('region',{name:'Target comparison'});
 const calls=fetcher.mock.calls.length;
 fireEvent.change(screen.getByPlaceholderText('Group name (e.g. Tech, ETFs, EM)'),{target:{value:'New tag'}});
 fireEvent.click(screen.getByRole('button',{name:'Add group'}));
 await waitFor(()=>expect(api.createGroup).toHaveBeenCalled());
 await waitFor(()=>expect(screen.getByPlaceholderText('Group name (e.g. Tech, ETFs, EM)')).toHaveValue(''));
 await waitFor(()=>expect(fetcher.mock.calls.length).toBeGreaterThan(calls));
 expect(screen.getByRole('region',{name:'Target comparison'})).toBeInTheDocument();
});
it('recalculation after baseline change never exposes previous cached scenario',async()=>{
 let scenarios=0;
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>{if(!String(url).includes('allocation-scenario'))return response(before);scenarios++;if(scenarios===2)return new Promise(()=>{});return response({before,after:{...before,invested_value_gbp:150},assumption:'OLD BASELINE RESULT'});}));
 const client=setup(<AllocationScenarioPanel/>);await submit();await screen.findByText('OLD BASELINE RESULT');
 client.setQueryData(['allocation-targets',null,2],{...before,invested_value_gbp:200,groups:[{...before.groups[0],actual_value_gbp:200}]});
 await waitFor(()=>expect(screen.queryByText('OLD BASELINE RESULT')).not.toBeInTheDocument());
 await submit();await waitFor(()=>expect(scenarios).toBe(2));
 expect(screen.queryByText('OLD BASELINE RESULT')).not.toBeInTheDocument();
});

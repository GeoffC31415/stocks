import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { api, type Instrument, type PortfolioSummary } from '../../lib/api';
vi.mock('../../state/useTargetDrift',()=>({useTargetDrift:()=>({query:{data:{status:'available',groups:[{group_id:1,name:'Core',instrument_ids:[1],actual_value_gbp:100,actual_weight_pct:45,target_weight_pct:50,gap_gbp:10,drift_pp:-5,within_tolerance:false}]}}})}));
import { Holdings } from '../Holdings';
import { PreferencesContext } from '../../state/usePreferences';
vi.mock('../../components/MatchingWarningBanner',()=>({MatchingWarningBanner:()=>null}));
const holding={id:1,ticker:'AAA',security_name:'Source Alpha',identifier:'source-id',account_name:'ISA',group_ids:[],latest_value_gbp:100} as unknown as Instrument;
function Navigation(){const loc=useLocation();const nav=useNavigate();return <><output>{loc.search}</output><button onClick={()=>nav(-1)}>Browser back</button></>;}
function show(url='/?inst=1',account='ISA') {return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><MemoryRouter initialEntries={[url]}><PreferencesContext.Provider value={{accountFilter:account,dripThreshold:100,setAccountFilter:()=>{},setDripThreshold:()=>{}}}><Navigation/><Holdings/></PreferencesContext.Provider></MemoryRouter></QueryClientProvider>);}
beforeEach(()=>{
 vi.restoreAllMocks();
 vi.spyOn(api,'getInstruments').mockResolvedValue([holding]);
 vi.spyOn(api,'getSummary').mockResolvedValue({total_value_gbp:1000,group_allocation:[]} as unknown as PortfolioSummary);
 vi.spyOn(api,'getOrderAnalytics').mockRejectedValue(new Error('offline'));
 vi.spyOn(api,'getInstrumentHistory').mockResolvedValue([]);
 vi.spyOn(api,'getInstrumentOrders').mockResolvedValue([]);
});
it.each(['01','1e2','1&inst=2','2'])('never requests unconfirmed scoped detail %s',async id=>{
 show('/?inst='+id); await waitFor(()=>expect(screen.getByRole('alert')).toHaveTextContent(/invalid|not available/i));
 expect(api.getInstrumentHistory).not.toHaveBeenCalled(); expect(api.getInstrumentOrders).not.toHaveBeenCalled();
});
it('opens with focus, closes with Escape and preserves search and table scroll',async()=>{
 show('/?q=AAA&sort=value');
 const row=await screen.findByRole('button',{name:'View AAA in ISA'}); row.focus();
 const table=screen.getByRole('region',{name:'Holdings table'}); table.scrollTop=90;
 fireEvent.click(row); const close=await screen.findByRole('button',{name:'Close instrument detail'});
 await waitFor(()=>expect(close).toHaveFocus());
 expect(await screen.findByText('No history available.')).toBeInTheDocument();
 expect(screen.getByText('source-id')).toBeInTheDocument();
 fireEvent.keyDown(close,{key:'Escape'});
 await waitFor(()=>expect(row).toHaveFocus());
 expect(screen.getByText('?q=AAA&sort=value')).toBeInTheDocument(); expect(table.scrollTop).toBe(90);
});
it('traps narrow drawer focus and follows browser back to close',async()=>{
 vi.stubGlobal('matchMedia',()=>({matches:true,addEventListener:()=>{},removeEventListener:()=>{}}));
 show('/?q=AAA');
 const row=await screen.findByRole('button',{name:'View AAA in ISA'}); fireEvent.click(row);
 const dialog=await screen.findByRole('dialog',{name:'Instrument detail'});
 expect(dialog).toHaveAttribute('aria-modal','true');
 const close=screen.getByRole('button',{name:'Close instrument detail'});
 close.focus(); fireEvent.keyDown(close,{key:'Tab',shiftKey:true});
 expect(screen.getByRole('button',{name:'Show instrument timeline'})).toHaveFocus();
 fireEvent.keyDown(document.activeElement!,{key:'Tab'}); expect(close).toHaveFocus();
 fireEvent.click(screen.getByRole('button',{name:'Browser back'}));
 await waitFor(()=>expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
 expect(row).toHaveFocus(); vi.unstubAllGlobals();
});
it('does not fetch detail while scoped instruments are unresolved',async()=>{
 vi.mocked(api.getInstruments).mockImplementation(()=>new Promise(()=>{}));
 show(); expect(screen.getByText(/Checking instrument account scope/)).toBeInTheDocument();
 expect(api.getInstrumentHistory).not.toHaveBeenCalled(); expect(api.getInstrumentOrders).not.toHaveBeenCalled();
});
it('reports history and orders failure independently with retries',async()=>{
 vi.mocked(api.getInstrumentHistory).mockRejectedValue(new Error('history offline'));
 vi.mocked(api.getInstrumentOrders).mockRejectedValue(new Error('orders offline'));
 show(); expect(await screen.findByRole('button',{name:'Retry history'})).toBeInTheDocument();
 expect(await screen.findByRole('button',{name:'Retry orders'})).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Retry history'}));await waitFor(()=>expect(api.getInstrumentHistory).toHaveBeenCalledTimes(2));
});

it('connects authoritative target drift and matching order navigation',async()=>{
 show('/?inst=1&period=1Y&from=2&to=4');
 expect(await screen.findByText(/Core.*gap/)).toBeInTheDocument();
 const link=screen.getByRole('link',{name:'View matching orders'});
 const p=new URL(link.getAttribute('href')!,'http://test').searchParams;
 expect(p.get('inst')).toBe('1');expect(p.get('account')).toBe('ISA');expect(p.get('period')).toBe('1Y');expect(p.get('from')).toBe('2');
});

import {render,screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {it,expect} from 'vitest';
import type {SnapshotAttribution,GroupPerformance} from '../../lib/api';
import {ContributionDetails} from '../ContributionDetails';
import {GroupPerformancePanel} from '../GroupPerformancePanel';
it('links a contributor to the selected holding with comparison and period intact',()=>{
 const attribution={notes:[],movements:[{instrument_id:1,security_name:'Alpha',identifier:'A',account_name:'ISA'}]} as unknown as SnapshotAttribution;
 render(<MemoryRouter initialEntries={['/activity?tab=changes&from=2&to=5&period=1Y']}><ContributionDetails attribution={attribution} instrumentId={1}/></MemoryRouter>);
 const href=screen.getByRole('link',{name:'Explore Alpha holding'}).getAttribute('href')!;
 const p=new URL(href,'http://test').searchParams;expect(p.get('inst')).toBe('1');expect(p.get('from')).toBe('2');expect(p.get('to')).toBe('5');expect(p.get('period')).toBe('1Y');
});
it('links group results to a real membership filter',()=>{
 const group={group_id:3,name:'Core',member_count:1,total_current_value_gbp:100,total_net_cost_gbp:100,total_pnl_gbp:0,timeseries:[],members:[]} as unknown as GroupPerformance;
 render(<MemoryRouter initialEntries={['/portfolio?account=ISA&period=6M']}><GroupPerformancePanel groups={[group]} isLoading={false}/></MemoryRouter>);
 const href=screen.getByRole('link',{name:'Explore Core holdings'}).getAttribute('href')!;
 expect(href).toContain('group=3');expect(href).toContain('account=ISA');expect(href).toContain('period=6M');
});

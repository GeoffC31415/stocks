import { render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { expect, it, vi } from 'vitest';
import { PortfolioWorkspace } from '../PortfolioWorkspace';
import { ActivityWorkspace } from '../ActivityWorkspace';
import { DataWorkspace } from '../DataWorkspace';
vi.mock('../Holdings',()=>({Holdings:()=> <p>Holdings page</p>}));
vi.mock('../PerformanceWorkspace',()=>({PerformanceWorkspace:()=>null}));
vi.mock('../Positions',()=>({Positions:()=>null}));vi.mock('../Groups',()=>({Groups:()=>null}));
vi.mock('../../components/AllocationAnalysisPanel',()=>({AllocationAnalysisPanel:()=>null}));vi.mock('../../components/IncomeAnalysisPanel',()=>({IncomeAnalysisPanel:()=>null}));
vi.mock('../Orders',()=>({Orders:()=> <p>Orders page</p>}));vi.mock('../Diff',()=>({Diff:()=>null}));vi.mock('../ImportActivity',()=>({ImportActivity:()=>null}));vi.mock('../TimelineSourceView',()=>({TimelineSourceView:()=> <p>Source page</p>}));
vi.mock('../Import',()=>({ImportPage:()=> <p>Import page</p>}));vi.mock('../MatchingWorkspace',()=>({MatchingWorkspace:()=>null}));vi.mock('../../components/ClassificationQueue',()=>({ClassificationQueue:()=>null}));vi.mock('../../components/AnalysisSettings',()=>({AnalysisSettings:()=>null}));vi.mock('../../components/DataConfidencePanel',()=>({DataConfidencePanel:()=>null}));
function Probe(){return <output data-testid="url">{useLocation().search}</output>}
it.each([[PortfolioWorkspace,'holdings','Holdings page'],[ActivityWorkspace,'orders','Orders page'],[DataWorkspace,'import','Import page']] as const)('validates unknown tab with linked selected panel in workspace %s',(Page,key,text)=>{
 render(<MemoryRouter initialEntries={['/?tab=BOGUS&account=ISA&period=1Y']}><Page/><Probe/></MemoryRouter>);
 expect(screen.getByText(text)).toBeInTheDocument();
 const panel=screen.getByRole('tabpanel');expect(panel).toHaveAttribute('aria-labelledby',`workspace-tab-${key}`);
 expect(screen.getByTestId('url')).toHaveTextContent(`tab=${key}&account=ISA&period=1Y`);
});
it('preserves production portfolio navigation labels',()=>{render(<MemoryRouter><PortfolioWorkspace/></MemoryRouter>);expect(screen.getAllByRole('tab').map(tab=>tab.textContent)).toEqual(['Holdings','Performance','Returns','Allocation','Income','Groups']);});
it('keeps source inspection reachable without adding a production navigation tab',()=>{render(<MemoryRouter initialEntries={['/?tab=source']}><ActivityWorkspace/><Probe/></MemoryRouter>);expect(screen.queryByRole('tab',{name:'Source record'})).not.toBeInTheDocument();expect(screen.getByText('Source page')).toBeInTheDocument();expect(screen.getByTestId('url')).toHaveTextContent('tab=source');});
it('preserves production activity navigation labels',()=>{render(<MemoryRouter><ActivityWorkspace/></MemoryRouter>);expect(screen.getAllByRole('tab').map(tab=>tab.textContent)).toEqual(['Orders','Snapshot changes','Import history']);});

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
it('labels holding returns distinctly from portfolio performance',()=>{render(<MemoryRouter><PortfolioWorkspace/></MemoryRouter>);expect(screen.getByRole('tab',{name:'Holding returns'})).toBeInTheDocument();});
it('keeps the valid source inspection tab selected',()=>{render(<MemoryRouter initialEntries={['/?tab=source']}><ActivityWorkspace/></MemoryRouter>);expect(screen.getByRole('tab',{name:'Source record'})).toHaveAttribute('aria-selected','true');expect(screen.getByText('Source page')).toBeInTheDocument();});

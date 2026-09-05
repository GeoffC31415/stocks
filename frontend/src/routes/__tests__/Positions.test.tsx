import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {render,screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {it,expect,vi} from 'vitest';
import {Positions} from '../Positions';
vi.mock('../../lib/api',()=>({api:{getOrderPositions:()=>new Promise(()=>{}),getOrderAnalytics:()=>new Promise(()=>{}),getGroupPerformance:()=>Promise.resolve([])}}));
vi.mock('../../components/MatchingWarningBanner',()=>({MatchingWarningBanner:()=>null}));
it('keeps the Returns heading and pending space without falsely showing empty positions',()=>{render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><Positions/></MemoryRouter></QueryClientProvider>);expect(screen.getByRole('heading',{name:'Position analysis'})).toBeInTheDocument();expect(screen.getByRole('status')).toHaveTextContent('Loading');expect(screen.queryByText('No positions yet')).not.toBeInTheDocument();});

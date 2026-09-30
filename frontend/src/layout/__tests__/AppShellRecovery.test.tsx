import { lazy, Suspense } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Link, MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { AppShell } from '../AppShell';

vi.mock('../../lib/api', () => ({ api: { getSummary: vi.fn().mockResolvedValue({ by_account: { ISA: {} } }) } }));
vi.mock('../Topbar', () => ({ Topbar: () => <header>Persistent header</header> }));
vi.mock('../Sidebar', () => ({ Sidebar: () => <nav><Link to="/activity?account=ISA&period=1Y&tab=changes&from=2&to=5#source">Activity</Link><Link to="/help?account=ISA&period=1Y">Help</Link></nav> }));
vi.mock('../MobileNav', () => ({ MobileNav: () => null }));
vi.mock('../../components/AuroraBackground', () => ({ AuroraBackground: () => null }));
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('contains a rejected lazy workspace inside the shell and permits another route', async () => {
  const store = new Map<string, string>();
  vi.stubGlobal('localStorage', { getItem: (key: string) => store.get(key) ?? null, setItem: (key: string, value: string) => store.set(key, value) });
  // A fresh lazy instance reproduces the cached rejection of a failed dynamic import.
  const FailedWorkspace = lazy(() => Promise.reject(new Error('Synthetic chunk GET 503')));
  const logged = vi.spyOn(console, 'error').mockImplementation(() => {});
  function Location() { const location = useLocation(); return <output data-testid="location">{location.pathname}{location.search}{location.hash}</output>; }
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={['/?account=ISA&period=1Y']}>
      <Routes><Route element={<AppShell />}>
        <Route path="/" element={<h1>Dashboard loaded</h1>} />
        <Route path="/activity" element={<Suspense fallback={<p>Loading workspace…</p>}><FailedWorkspace /></Suspense>} />
        <Route path="/help" element={<h1>Help loaded</h1>} />
      </Route></Routes><Location />
    </MemoryRouter>
  </QueryClientProvider>);
  expect(await screen.findByText('Dashboard loaded')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('link', { name: 'Activity' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Unable to load this workspace.');
  expect(screen.getByRole('banner')).toHaveTextContent('Persistent header');
  expect(screen.getByRole('navigation')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Reload workspace' })).toBeInTheDocument();
  expect(screen.getByRole('alert')).toHaveTextContent('Reload the page to try again, or choose another workspace.');
  expect(screen.getByTestId('location')).toHaveTextContent('/activity?account=ISA&period=1Y&tab=changes&from=2&to=5#source');
  fireEvent.click(screen.getByRole('link', { name: 'Help' }));
  expect(await screen.findByText('Help loaded')).toBeInTheDocument();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  expect(screen.getByRole('banner')).toBeInTheDocument();
  // Returning must contain React.lazy's cached rejection rather than promise an ineffective reset.
  fireEvent.click(screen.getByRole('link', { name: 'Activity' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Unable to load this workspace.');
  expect(logged).toHaveBeenCalled();
});

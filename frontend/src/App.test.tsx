import { render, screen, waitFor } from '@testing-library/react';
import { Outlet } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import App from './App';
vi.mock('./layout/AppShell',()=>({AppShell:()=> <><p>Persistent app shell</p><Outlet /></>}));
vi.mock('./auth/AuthProvider',()=>({useAuth:()=>({session:{mode:'passkey'}})}));
vi.mock('./routes/Overview',()=>({Overview:()=> <h1>Overview loaded</h1>}));
vi.mock('./routes/PortfolioWorkspace',()=>({PortfolioWorkspace:()=> <h1>Portfolio loaded</h1>}));
vi.mock('./auth/Security',()=>({Security:()=> <h1>Security loaded</h1>}));
beforeEach(()=>window.history.replaceState({},'', '/'));
it('reserves route loading geometry within the persistent shell',async()=>{
 render(<App/>);expect(screen.getByText('Persistent app shell')).toBeInTheDocument();
 const loading=screen.getByRole('status',{name:'Loading workspace'});expect(loading).toHaveClass('min-h-[560px]');
 expect(await screen.findByText('Overview loaded')).toBeInTheDocument();
});
it('keeps legacy instrument scope through lazy route resolution',async()=>{
 window.history.replaceState({},'', '/holdings?inst=7&account=ISA&period=1Y');render(<App/>);
 expect(await screen.findByText('Portfolio loaded')).toBeInTheDocument();
 await waitFor(()=>expect(window.location.pathname).toBe('/portfolio'));
 expect(new URLSearchParams(window.location.search).get('inst')).toBe('7');
 expect(new URLSearchParams(window.location.search).get('tab')).toBe('holdings');
});
it('keeps passkey security route reachable',async()=>{window.history.replaceState({},'', '/security');render(<App/>);expect(await screen.findByText('Security loaded')).toBeInTheDocument();});

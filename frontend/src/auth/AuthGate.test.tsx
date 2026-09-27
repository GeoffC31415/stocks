import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { AuthProvider } from './AuthProvider';
import { AuthGate } from './AuthGate';
import { requestJson } from '../lib/api';

import { startAuthentication, startRegistration, browserSupportsWebAuthn } from '@simplewebauthn/browser';
vi.mock('@simplewebauthn/browser', () => ({ WebAuthnAbortService: {cancelCeremony: vi.fn()}, startAuthentication: vi.fn(), startRegistration: vi.fn(), browserSupportsWebAuthn: vi.fn(() => true) }));
const transport = vi.fn();

it('signs in via the browser helper, prevents duplicate clicks, and preserves the deep link', async () => {
  window.history.replaceState({}, '', '/holdings?account=test#position');
  transport.mockResolvedValueOnce(json(signedOut)).mockResolvedValueOnce(json({ceremony_id:'login-1', options:{challenge:'challenge'}})).mockResolvedValueOnce(json(signedIn)).mockResolvedValue(json({}));
  let resolve!: (value: unknown) => void;
  vi.mocked(startAuthentication).mockImplementationOnce(() => new Promise<unknown>(r => { resolve = r; }) as ReturnType<typeof startAuthentication>);
  mount();
  const button = await screen.findByRole('button', {name:'Sign in with a passkey'});
  fireEvent.click(button); fireEvent.click(button);
  await waitFor(() => expect(startAuthentication).toHaveBeenCalledWith({optionsJSON:{challenge:'challenge'}}));
  expect(button).toBeDisabled();
  await act(async () => resolve({id:'credential'}));
  expect(await screen.findByText('Private portfolio')).toBeInTheDocument();
  expect(transport.mock.calls[2][1]).toMatchObject({method:'POST', credentials:'same-origin', body:JSON.stringify({ceremony_id:'login-1',credential:{id:'credential'}})});
  expect(window.location.pathname + window.location.search + window.location.hash).toBe('/holdings?account=test#position');
});
it('offers a calm retry after passkey cancellation without verification', async () => {
  transport.mockResolvedValueOnce(json(signedOut)).mockResolvedValue(json({ceremony_id:'login-1',options:{}}));
  vi.mocked(startAuthentication).mockRejectedValueOnce(new DOMException('cancelled', 'NotAllowedError'));
  mount(); fireEvent.click(await screen.findByRole('button', {name:'Sign in with a passkey'}));
  expect(await screen.findByRole('status')).toHaveTextContent('cancelled');
  expect(screen.getByRole('button', {name:'Sign in with a passkey'})).toBeEnabled();
  expect(transport).toHaveBeenCalledTimes(2);
});
it('explains unsupported browsers and disables sign-in', async () => {
  vi.mocked(browserSupportsWebAuthn).mockReturnValueOnce(false);
  transport.mockResolvedValueOnce(json(signedOut)); mount();
  expect(await screen.findByRole('button', {name:'Sign in with a passkey'})).toBeDisabled();
  expect(screen.getByText(/browser does not support passkeys/)).toBeInTheDocument();
});
it('expires the app on an API 401, clears queries and mutations, and never refresh-loops', async () => {
  transport.mockResolvedValueOnce(json(signedIn)).mockResolvedValueOnce(json({private:'data'}));
  const client = mount();
  await screen.findByText('Private portfolio');
  await waitFor(() => expect(client.getQueryData(['private'])).toEqual({private:'data'}));
  client.getMutationCache().build(client, {mutationKey:['private-mutation']});
  transport.mockResolvedValueOnce(json({detail:'expired'},401));
  await act(async () => { await expect(requestJson('/api/expired')).rejects.toThrow('expired'); });
  expect(screen.queryByText('Private portfolio')).not.toBeInTheDocument();
  expect(client.getQueryCache().getAll()).toHaveLength(0);
  expect(client.getMutationCache().getAll()).toHaveLength(0);
  expect(transport).toHaveBeenCalledTimes(3);
  expect(screen.getByRole('button', {name:'Sign in with a passkey'})).toBeInTheDocument();
});
it('locks and clears caches immediately on logout, before the server responds', async () => {
  transport.mockResolvedValueOnce(json(signedIn)).mockResolvedValueOnce(json({private:'data'}));
  const client = mount();
  await screen.findByText('Private portfolio');
  await waitFor(() => expect(client.getQueryData(['private'])).toBeDefined());
  let resolve!: (value:Response) => void;
  transport.mockReturnValueOnce(new Promise<Response>(r => {resolve=r;}));
  fireEvent.click(screen.getByRole('button', {name:'Log out'}));
  expect(screen.queryByText('Private portfolio')).not.toBeInTheDocument();
  expect(client.getQueryCache().getAll()).toHaveLength(0);
  await act(async () => resolve(json({ok:true})));
  expect(transport.mock.calls[2]).toEqual(['/api/auth/logout', expect.objectContaining({method:'POST',body:'{}'})]);
});
it('expires at the server deadline without issuing another request', async () => {
  transport.mockResolvedValueOnce(json({...signedIn,expires_at:Date.now()/1000 + 0.15})).mockResolvedValue(json({}));
  mount(); await screen.findByText('Private portfolio');
  await waitFor(() => expect(screen.queryByText('Private portfolio')).not.toBeInTheDocument());
  expect(transport).toHaveBeenCalledTimes(2);
});
it('local mode bypasses all auth chrome', async () => {
  transport.mockResolvedValueOnce(json({...signedIn,mode:'local'})).mockResolvedValue(json({}));
  mount(); await screen.findByText('Private portfolio');
  expect(screen.queryByRole('button', {name:'Log out'})).not.toBeInTheDocument();
  expect(screen.queryByRole('button', {name:'Security / passkeys'})).not.toBeInTheDocument();
});
it('enrolls named first and backup passkeys, reads back the list, and explains Basic migration', async () => {
  const basic = {...signedIn, mode:'basic', passkey_authenticated:false};
  const keys: {id:string;label:string;created_at:number;last_used_at:null}[] = [];
  let nextLabel = '';
  transport.mockImplementation(async (url:string, init?:RequestInit) => {
    if (url === '/api/auth/session') return json(basic);
    if (url === '/api/auth/credentials') return keys.length ? json({credentials:keys}) : json({detail:'Authentication required'},401);
    if (url === '/api/auth/register/options') { nextLabel=JSON.parse(String(init?.body)).label; return json({ceremony_id:'reg',options:{challenge:'registration'}}); }
    if (url === '/api/auth/register/verify') { keys.push({id:String(keys.length),label:nextLabel,created_at:1,last_used_at:null}); return json({...basic,passkey_authenticated:true}); }
    return json({});
  });
  vi.mocked(startRegistration).mockResolvedValue({id:'new-key'} as Awaited<ReturnType<typeof startRegistration>>);
  mount(); await screen.findByText('Private portfolio');
  expect(screen.getByText(/old password remains required until an administrator/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', {name:'Security / passkeys'}));
  expect(transport.mock.calls.filter(c => c[0] === '/api/auth/credentials')).toHaveLength(0);
  expect(await screen.findByText('No passkeys registered.')).toBeInTheDocument();
  expect(screen.getByLabelText('Passkey name')).toHaveAttribute('maxlength', '80');
  fireEvent.change(screen.getByLabelText('Passkey name'), {target:{value:'Gaming PC'}});
  fireEvent.click(screen.getByRole('button', {name:'Add passkey'}));
  expect(await screen.findByText('Gaming PC')).toBeInTheDocument();
  expect(startRegistration).toHaveBeenCalledWith({optionsJSON:{challenge:'registration'}});
  expect(screen.getByText(/independent backup passkey/)).toBeInTheDocument();
  expect(screen.getByText(/not yet passwordless/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Passkey name'), {target:{value:'Backup key'}});
  fireEvent.click(screen.getByRole('button', {name:'Add passkey'}));
  expect(await screen.findByText('Backup key')).toBeInTheDocument();
  expect(keys).toHaveLength(2);
  expect(transport.mock.calls.filter(c => c[0] === '/api/auth/credentials')).toHaveLength(2);
});
it('requires explicit reauthentication and retry for a protected change, then confirms removal and guards the last key', async () => {
  let recent = false;
  let keys = [{id:'a/b',label:'Primary',created_at:1,last_used_at:null}, {id:'backup',label:'Backup',created_at:1,last_used_at:null}];
  transport.mockImplementation(async (url:string, init?:RequestInit) => {
    if (url === '/api/auth/session') return json(signedIn);
    if (url === '/api/auth/credentials') return json({credentials:keys});
    if (url === '/api/auth/credentials/a%2Fb' && init?.method === 'DELETE') {
      if (!recent) return json({detail:'recent verification required'},403);
      keys=keys.slice(1); return json({ok:true});
    }
    if (url === '/api/auth/login/options') return json({ceremony_id:'verify',options:{}});
    if (url === '/api/auth/login/verify') {recent=true;return json(signedIn);}
    return json({});
  });
  vi.mocked(startAuthentication).mockResolvedValue({id:'primary'} as Awaited<ReturnType<typeof startAuthentication>>);
  mount(); fireEvent.click(await screen.findByRole('button', {name:'Security / passkeys'}));
  fireEvent.click(await screen.findByRole('button', {name:'Remove Primary'}));
  expect(transport.mock.calls.some(c => c[1]?.method==='DELETE')).toBe(false);
  fireEvent.click(screen.getByRole('button', {name:'Confirm removal'}));
  expect(await screen.findByRole('status')).toHaveTextContent('Verify a passkey again');
  fireEvent.click(screen.getByRole('button', {name:'Verify passkey again'}));
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('sign-in tested'));
  expect(transport.mock.calls.filter(c => c[1]?.method==='DELETE')).toHaveLength(1);
  fireEvent.click(screen.getByRole('button', {name:'Remove Primary'}));
  fireEvent.click(screen.getByRole('button', {name:'Confirm removal'}));
  await waitFor(() => expect(screen.queryByText('Primary')).not.toBeInTheDocument());
  expect(screen.getByRole('button', {name:'Remove Backup'})).toBeDisabled();
  expect(screen.getByText(/last passkey cannot be removed/)).toBeInTheDocument();
});
it('confirms logout-all and clears the authenticated app and caches', async () => {
  transport.mockImplementation(async (url:string) => {
    if (url === '/api/auth/session') return json(signedIn);
    if (url === '/api/auth/credentials') return json({credentials:[]});
    return json({ok:true});
  });
  const client = mount(); fireEvent.click(await screen.findByRole('button', {name:'Security / passkeys'}));
  await screen.findByText('No passkeys registered.');
  fireEvent.click(screen.getByRole('button', {name:'Log out all sessions'}));
  expect(transport.mock.calls.some(c => c[0]==='/api/auth/logout-all')).toBe(false);
  fireEvent.click(screen.getByRole('button', {name:'Confirm logout all'}));
  expect(await screen.findByRole('button', {name:'Sign in with a passkey'})).toBeInTheDocument();
  expect(client.getQueryCache().getAll()).toHaveLength(0);
  expect(transport.mock.calls.some(c => c[0]==='/api/auth/logout-all')).toBe(true);
});
it('does not claim logout-all succeeded or lock the session on a rejected revocation', async () => {
  transport.mockImplementation(async (url:string) => {
    if (url === '/api/auth/session') return json(signedIn);
    if (url === '/api/auth/credentials') return json({credentials:[]});
    if (url === '/api/auth/logout-all') return json({detail:'recent verification required'},403);
    return json({});
  });
  mount(); fireEvent.click(await screen.findByRole('button', {name:'Security / passkeys'}));
  await screen.findByText('No passkeys registered.');
  fireEvent.click(screen.getByRole('button', {name:'Log out all sessions'}));
  fireEvent.click(screen.getByRole('button', {name:'Confirm logout all'}));
  expect(await screen.findByRole('status')).toHaveTextContent('Verify a passkey again');
  expect(screen.getByRole('button', {name:'Log out'})).toBeInTheDocument();
  expect(screen.queryByRole('button', {name:'Sign in with a passkey'})).not.toBeInTheDocument();
});
it('keeps the portfolio locked with a retry warning when server logout fails', async () => {
  transport.mockImplementation(async (url:string) => {
    if (url === '/api/auth/session') return json(signedIn);
    if (url === '/api/auth/logout') throw new Error('offline');
    return json({});
  });
  mount(); fireEvent.click(await screen.findByRole('button', {name:'Log out'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('server logout could not be confirmed');
  expect(screen.getByRole('button', {name:'Retry logout'})).toBeInTheDocument();
  expect(screen.queryByText('Private portfolio')).not.toBeInTheDocument();
});
it('recovers only through an explicit memory-only token form and clears the token on failure and completion', async () => {
  transport.mockResolvedValueOnce(json(signedOut));
  mount(); fireEvent.click(await screen.findByRole('button', {name:'Recover access'}));
  expect(screen.getByText(/one-time recovery file from the local administrator/)).toBeInTheDocument();
  expect(screen.getByText(/no email password reset/)).toBeInTheDocument();
  const token = screen.getByLabelText('One-time recovery token');
  fireEvent.change(token, {target:{value:'synthetic-token'}});
  fireEvent.change(screen.getByLabelText('New passkey name'), {target:{value:'Replacement'}});
  transport.mockResolvedValueOnce(json({detail:'invalid'},403));
  fireEvent.click(screen.getByRole('button', {name:'Register recovery passkey'}));
  await screen.findByRole('status');
  expect(token).toHaveValue('');
  expect(transport.mock.calls[1]).toEqual(['/api/auth/recovery/options',expect.objectContaining({body:JSON.stringify({token:'synthetic-token',label:'Replacement'})})]);
  fireEvent.change(token, {target:{value:'synthetic-retry-token'}});
  transport.mockResolvedValueOnce(json({ceremony_id:'recover',options:{challenge:'recovery'}})).mockResolvedValueOnce(json(signedIn)).mockResolvedValue(json({}));
  vi.mocked(startRegistration).mockResolvedValueOnce({id:'replacement'} as Awaited<ReturnType<typeof startRegistration>>);
  fireEvent.click(screen.getByRole('button', {name:'Register recovery passkey'}));
  expect(await screen.findByText('Private portfolio')).toBeInTheDocument();
  expect(startRegistration).toHaveBeenCalledWith({optionsJSON:{challenge:'recovery'}});
  expect(transport.mock.calls.some(c => c[0]==='/api/auth/register/verify' && c[1]?.body===JSON.stringify({ceremony_id:'recover',credential:{id:'replacement'}}))).toBe(true);
  expect(window.location.href).not.toContain('synthetic-');
  expect(JSON.stringify(window.localStorage)).not.toContain('synthetic-');
});
it('clears recovery input when leaving the form', async () => {
  transport.mockResolvedValueOnce(json(signedOut)); mount();
  fireEvent.click(await screen.findByRole('button', {name:'Recover access'}));
  fireEvent.change(screen.getByLabelText('One-time recovery token'), {target:{value:'synthetic-token'}});
  fireEvent.click(screen.getByRole('button', {name:'Back to sign in'}));
  fireEvent.click(screen.getByRole('button', {name:'Recover access'}));
  expect(screen.getByLabelText('One-time recovery token')).toHaveValue('');
});
it('never restores a late enrollment session after logout', async () => {
  let resolve!: (value:Response) => void;
  transport.mockImplementation(async (url:string) => {
    if (url === '/api/auth/session') return json(signedIn);
    if (url === '/api/auth/credentials') return json({credentials:[]});
    if (url === '/api/auth/register/options') return json({ceremony_id:'reg',options:{}});
    if (url === '/api/auth/register/verify') return new Promise<Response>(r => {resolve=r;});
    return json({ok:true});
  });
  vi.mocked(startRegistration).mockResolvedValue({id:'new'} as Awaited<ReturnType<typeof startRegistration>>);
  mount(); fireEvent.click(await screen.findByRole('button', {name:'Security / passkeys'}));
  await screen.findByText('No passkeys registered.');
  fireEvent.change(screen.getByLabelText('Passkey name'), {target:{value:'Backup'}});
  fireEvent.click(screen.getByRole('button', {name:'Add passkey'}));
  await waitFor(() => expect(resolve).toBeDefined());
  fireEvent.click(screen.getByRole('button', {name:'Log out'}));
  await screen.findByRole('button', {name:'Sign in with a passkey'});
  await act(async () => resolve(json(signedIn)));
  expect(screen.getByRole('button', {name:'Sign in with a passkey'})).toBeInTheDocument();
  expect(screen.queryByText('Private portfolio')).not.toBeInTheDocument();
});
const signedOut = { mode: 'passkey', authenticated: false, passkey_authenticated: false, can_register: false, expires_at: null };
const signedIn = { ...signedOut, authenticated: true, passkey_authenticated: true, can_register: true };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), {status});
function Portfolio() {
  useQuery({ queryKey: ['private'], queryFn: () => requestJson('/api/portfolio') });
  return <p>Private portfolio</p>;
}
function mount() {
  const client = new QueryClient({defaultOptions: {queries: {retry: false}}});
  render(<QueryClientProvider client={client}><AuthProvider><AuthGate><Portfolio /></AuthGate></AuthProvider></QueryClientProvider>);
  return client;
}
beforeEach(() => { transport.mockReset(); vi.stubGlobal('fetch', transport); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
it('does not mount portfolio or issue portfolio queries until the session is authenticated', async () => {
  let resolve!: (value: Response) => void;
  transport.mockReturnValueOnce(new Promise<Response>(r => {resolve = r;}));
  mount();
  expect(screen.getByRole('status')).toHaveTextContent('Checking session');
  expect(transport).toHaveBeenCalledTimes(1);
  expect(screen.queryByText('Private portfolio')).not.toBeInTheDocument();
  await act(async () => resolve(json(signedIn)));
  expect(await screen.findByText('Private portfolio')).toBeInTheDocument();
  expect(transport.mock.calls.map(c => c[0])).toEqual(['/api/auth/session', '/api/portfolio']);
});
it('fails closed with a retry when session loading fails', async () => {
  transport.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(json(signedOut));
  mount();
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not check');
  expect(screen.queryByText('Private portfolio')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', {name: 'Retry session'}));
  expect(await screen.findByRole('button', {name: 'Sign in with a passkey'})).toBeInTheDocument();
  expect(transport).toHaveBeenCalledTimes(2);
});

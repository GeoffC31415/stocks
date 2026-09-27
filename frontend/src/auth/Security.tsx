import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { browserSupportsWebAuthn } from '@simplewebauthn/browser';
import { authApi } from './api';
import { useAuth } from './AuthProvider';
import { authMessage } from './SignIn';
import type { PasskeyCredential } from './types';

export function Security() {
  const navigate = useNavigate();
  const {session, ceremony, cancelCeremony, lock} = useAuth();
  useEffect(() => () => cancelCeremony(), [cancelCeremony]);
  const [supported] = useState(browserSupportsWebAuthn);
  const [keys, setKeys] = useState<PasskeyCredential[] | null>(null);
  const [listError, setListError] = useState(false);
  const [label, setLabel] = useState('');
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const [message, setMessage] = useState('');
  const [confirmation, setConfirmation] = useState<PasskeyCredential | 'logout-all' | null>(null);
  const load = useCallback(async () => {
    setListError(false);
    // Basic bootstrap may enroll, but credential management requires a passkey session.
    if (!session?.passkey_authenticated) { setKeys([]); setConfirmation(null); return; }
    try { setKeys((await authApi.credentials()).credentials); }
    catch { setKeys(null); setListError(true); }
  }, [session]);
  useEffect(() => { void load(); }, [load]);
  async function run(action: () => Promise<void>) {
    if (locked.current) return;
    locked.current = true; setBusy(true); setMessage('');
    try { await action(); }
    catch (error) { setMessage(authMessage(error)); }
    finally { locked.current = false; setBusy(false); setConfirmation(null); }
  }
  async function add() {
    if (!label.trim()) return;
    await ceremony(signal => authApi.register(label.trim(), signal));
    setLabel(''); setMessage('Passkey registered. Test sign-in with this passkey before relying on it.');
  }
  async function verify() {
    await ceremony(authApi.login);
    setMessage('Passkey sign-in tested. Retry your intended action; no changes have been retried automatically.');
  }
  async function confirm() {
    if (confirmation === 'logout-all') { await authApi.logoutAll(); lock(); }
    else if (confirmation && keys && keys.length > 1) {
      await authApi.remove(confirmation.id);
      setMessage('Passkey removed.');
      await load();
    }
  }
  return <main className="auth-page"><div className="flex items-center justify-between gap-3"><h1>Security / passkeys</h1><button type="button" onClick={() => navigate('/portfolio')}>Back to portfolio</button></div>
    <p>Name each credential so you can recognise it. Add an independent backup passkey on another device or security key before relying on passwordless access.</p>
    <p>Additional enrollment, removal and logout-all require a passkey verified within the last five minutes. Verify again, then retry the intended action.</p>
    {!supported && <p role="alert">This browser does not support passkeys. Use a current browser on HTTPS.</p>}
    {message && <p role="status">{message}</p>}
    <button disabled={busy || !supported} onClick={() => void run(verify)}>Verify passkey again</button>
    {listError ? <p role="alert">Could not load passkeys. <button disabled={busy} onClick={() => void run(load)}>Refresh passkeys</button></p>
      : keys === null ? <p role="status">Loading passkeys…</p>
      : keys.length === 0 ? <p>No passkeys registered.</p>
      : <ul>{keys.map(key => <li key={key.id}><strong>{key.label}</strong><p>Created {new Date(key.created_at * 1000).toLocaleString()}; last used {key.last_used_at === null ? 'Never' : new Date(key.last_used_at * 1000).toLocaleString()}</p>
        <button disabled={busy || keys.length <= 1} onClick={() => setConfirmation(key)} aria-label={`Remove ${key.label}`}>Remove</button>
      </li>)}</ul>}
    {keys?.length === 1 && <p>The last passkey cannot be removed. Register a backup first.</p>}
    <form onSubmit={event => {event.preventDefault(); void run(add);}}>
      <label htmlFor="passkey-name">Passkey name</label>
      <input id="passkey-name" value={label} onChange={event => setLabel(event.target.value)} maxLength={80} required disabled={busy} autoComplete="off" />
      <button disabled={busy || !supported || !session?.can_register || !label.trim()}>Add passkey</button>
    </form>
    {!session?.can_register && <p>Registration is not currently authorised. Verify an existing passkey, or ask the local administrator for recovery.</p>}
    <button disabled={busy} onClick={() => setConfirmation('logout-all')}>Log out all sessions</button>
    {confirmation && <section role="group" aria-label="Confirm security change">
      <p>{confirmation === 'logout-all' ? 'End every passkey session, including this one?' : `Remove ${confirmation.label}? Only proceed if your other passkey works.`}</p>
      <button disabled={busy} onClick={() => void run(confirm)}>{confirmation === 'logout-all' ? 'Confirm logout all' : 'Confirm removal'}</button>
      <button disabled={busy} onClick={() => setConfirmation(null)}>Cancel</button>
    </section>}
  </main>;
}

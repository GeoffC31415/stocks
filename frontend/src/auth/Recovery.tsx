import { useEffect, useRef, useState } from 'react';
import { browserSupportsWebAuthn } from '@simplewebauthn/browser';
import { authApi } from './api';
import { useAuth } from './AuthProvider';
import { authMessage } from './SignIn';
import { ApiError } from '../lib/api';

export function Recovery({back}: {back: () => void}) {
  const {ceremony, cancelCeremony} = useAuth();
  const tokenInput = useRef<HTMLInputElement>(null);
  const [label, setLabel] = useState('');
  useEffect(() => () => cancelCeremony(), [cancelCeremony]);
  const [supported] = useState(browserSupportsWebAuthn);
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const [message, setMessage] = useState('');
  useEffect(() => { const input = tokenInput.current; return () => { if (input) input.value = ''; }; }, []);
  async function recover() {
    if (locked.current || !tokenInput.current?.value || !label.trim()) return;
    locked.current = true; setBusy(true); setMessage('');
    // Not React state, storage, a URL, or a query-cache key. Clear the DOM before any await.
    let token = tokenInput.current.value;
    const pending = ceremony(signal => authApi.recover(token, label.trim(), signal));
    token = '';
    tokenInput.current.value = '';
    try { await pending; }
    catch (error) {
      setMessage(error instanceof ApiError && [401,403].includes(error.status)
        ? 'Recovery was not accepted. Obtain a valid one-time file from the local administrator and try again.' : authMessage(error));
    } finally { locked.current = false; setBusy(false); }
  }
  return <main className="auth-page"><h1>Recover access</h1>
    <p>Obtain the one-time recovery file from the local administrator. There is no email password reset. Paste its token here to register a replacement passkey.</p>
    <p>The token is kept only for this request and cleared after submission. If a request fails, ask the administrator whether a new recovery file is needed.</p>
    {!supported && <p role="alert">This browser does not support passkeys. Use a current browser on HTTPS.</p>}
    {message && <p role="status">{message}</p>}
    <form onSubmit={event => {event.preventDefault(); void recover();}} autoComplete="off">
      <label htmlFor="recovery-token">One-time recovery token</label>
      <input id="recovery-token" ref={tokenInput} type="password" required disabled={busy} autoComplete="off" spellCheck={false} />
      <label htmlFor="recovery-name">New passkey name</label>
      <input id="recovery-name" value={label} onChange={event => setLabel(event.target.value)} required maxLength={80} disabled={busy} autoComplete="off" />
      <button disabled={busy || !supported || !label.trim()}>Register recovery passkey</button>
    </form>
    <button disabled={busy} onClick={back}>Back to sign in</button>
  </main>;
}

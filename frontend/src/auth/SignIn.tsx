import { useEffect, useRef, useState } from 'react';
import { browserSupportsWebAuthn } from '@simplewebauthn/browser';
import { authApi } from './api';
import { useAuth } from './AuthProvider';
import { ApiError } from '../lib/api';
import { Recovery } from './Recovery';

export function authMessage(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'name' in error && ['NotAllowedError', 'AbortError'].includes(String(error.name))) return 'Passkey request cancelled or timed out. You can try again.';
  if (error instanceof ApiError) {
    if (error.status === 401) return 'Your session ended or verification failed. Please sign in again.';
    if (error.status === 403) return 'Verify a passkey again before continuing.';
    if (error.status === 409) return 'This change conflicts with the current passkeys. Refresh the list; the last passkey cannot be removed.';
  }
  return 'Could not complete the passkey request. Please try again.';
}
export function SignIn() {
  const [recovery, setRecovery] = useState(false);
  const {ceremony, cancelCeremony} = useAuth();
  useEffect(() => () => cancelCeremony(), [cancelCeremony]);
  const [supported] = useState(browserSupportsWebAuthn);
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const [message, setMessage] = useState('');
  async function login() {
    if (locked.current) return;
    locked.current = true; setBusy(true); setMessage('');
    try { await ceremony(authApi.login); }
    catch (error) { setMessage(authMessage(error)); }
    finally { locked.current = false; setBusy(false); }
  }
  if (recovery) return <Recovery back={() => setRecovery(false)} />;
  return <main className="auth-page"><h1>Sign in</h1>
    <p>Your portfolio stays locked until your session is verified.</p>
    {!supported && <p role="alert">This browser does not support passkeys. Use a current browser on HTTPS.</p>}
    {message && <p role="status">{message}</p>}
    <button disabled={busy || !supported} onClick={() => void login()}>Sign in with a passkey</button>
    <button disabled={busy} onClick={() => setRecovery(true)}>Recover access</button>
  </main>;
}

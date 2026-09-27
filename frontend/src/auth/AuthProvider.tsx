import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { WebAuthnAbortService } from '@simplewebauthn/browser';
import { useQueryClient } from '@tanstack/react-query';
import { AUTH_REQUIRED_EVENT, cancelPendingRequests } from '../lib/api';
import { authApi } from './api';
import type { AuthSession } from './types';

type AuthState = {
  session: AuthSession | null; loading: boolean; error: string;
  refresh: () => Promise<void>; acceptSession: (session: AuthSession) => void;
  ceremony: (operation: (signal: AbortSignal) => Promise<AuthSession>) => Promise<void>; cancelCeremony: () => void;
  lock: () => void; logout: () => Promise<void>; loggingOut: boolean; logoutError: string;
};
const Context = createContext<AuthState | null>(null);
export function AuthProvider({children}: {children: ReactNode}) {
  const client = useQueryClient();
  const [session, setSession] = useState<AuthSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState('');
  const generation = useRef(0);
  const logoutLock = useRef(false);
  const activeCeremony = useRef<AbortController | null>(null);
  const cancelCeremony = useCallback(() => {
    activeCeremony.current?.abort();
    activeCeremony.current = null;
    WebAuthnAbortService.cancelCeremony();
  }, []);
  const lock = useCallback(() => {
    cancelCeremony();
    cancelPendingRequests();
    generation.current++;
    setSession(previous => previous ? {...previous, authenticated:false, passkey_authenticated:false, can_register:false, expires_at:null} : null);
    setLoading(false); setError('');
    // clear() cancels outstanding queries and removes both query and mutation caches.
    client.clear();
  }, [client, cancelCeremony]);
  const acceptSession = useCallback((next: AuthSession) => {
    generation.current++;
    setSession(next); setLoading(false); setError('');
    if (!next.authenticated) client.clear();
  }, [client]);
  const ceremony = useCallback(async (operation: (signal: AbortSignal) => Promise<AuthSession>) => {
    cancelCeremony();
    const controller = new AbortController();
    activeCeremony.current = controller;
    const current = generation.current;
    try {
      const next = await operation(controller.signal);
      controller.signal.throwIfAborted();
      if (current !== generation.current) throw new DOMException('Session changed', 'AbortError');
      acceptSession(next);
    } finally { if (activeCeremony.current === controller) activeCeremony.current = null; }
  }, [acceptSession, cancelCeremony]);
  const refresh = useCallback(async () => {
    const current = ++generation.current;
    setLoading(true); setError('');
    try {
      const next = await authApi.session();
      if (current === generation.current) acceptSession(next);
    } catch {
      if (current === generation.current) { setSession(null); client.clear(); setError('Could not check your session. Please retry.'); setLoading(false); }
    }
  }, [acceptSession, client]);
  const logout = useCallback(async () => {
    if (logoutLock.current) return;
    logoutLock.current = true; setLoggingOut(true); setLogoutError(''); lock();
    try { await authApi.logout(); }
    catch { setLogoutError('Portfolio locked, but server logout could not be confirmed. Retry logout before leaving a shared device.'); }
    finally { logoutLock.current = false; setLoggingOut(false); }
  }, [lock]);
  useEffect(() => {
    window.addEventListener(AUTH_REQUIRED_EVENT, lock);
    void refresh();
    return () => { cancelCeremony(); generation.current++; window.removeEventListener(AUTH_REQUIRED_EVENT, lock); };
  }, [refresh, lock, cancelCeremony]);
  useEffect(() => {
    if (!session?.authenticated || session.expires_at === null) return;
    const deadline = session.expires_at * 1000;
    let timer: ReturnType<typeof setTimeout>;
    const check = () => {
      clearTimeout(timer);
      const remaining = deadline - Date.now();
      if (remaining <= 0) lock();
      else timer = setTimeout(check, Math.min(remaining, 2147483647));
    };
    check();
    window.addEventListener('focus', check);
    document.addEventListener('visibilitychange', check);
    return () => { clearTimeout(timer); window.removeEventListener('focus', check); document.removeEventListener('visibilitychange', check); };
  }, [session, lock]);
  return <Context.Provider value={{session, loading, error, refresh, acceptSession, ceremony, cancelCeremony, lock, logout, loggingOut, logoutError}}>{children}</Context.Provider>;
}
export function useAuth() {
  const value = useContext(Context);
  if (!value) throw new Error('AuthProvider is required');
  return value;
}

import { startAuthentication, startRegistration } from '@simplewebauthn/browser';
import type { PublicKeyCredentialRequestOptionsJSON, PublicKeyCredentialCreationOptionsJSON } from '@simplewebauthn/browser';
import { requestJson } from '../lib/api';
import type { AuthSession, PasskeyCredential } from './types';
const post = <T,>(path: string, body: unknown = {}, signal?: AbortSignal) => requestJson<T>(`/api/auth/${path}`, {
  method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body), cache: 'no-store', signal,
});
export const authApi = {
  remove: (id: string) => requestJson<{ok:true}>(`/api/auth/credentials/${encodeURIComponent(id)}`, {method:'DELETE'}),
  logoutAll: () => post<{ok:true}>('logout-all'),
  credentials: () => requestJson<{credentials: PasskeyCredential[]}>('/api/auth/credentials', {cache: 'no-store'}),
  recover: async (token: string, label: string, signal?: AbortSignal) => {
    const pending = post<{ceremony_id: string; options: PublicKeyCredentialCreationOptionsJSON}>('recovery/options', {token, label}, signal);
    token = '';
    const {ceremony_id, options} = await pending;
    signal?.throwIfAborted();
    const credential = await startRegistration({optionsJSON: options});
    signal?.throwIfAborted();
    return post<AuthSession>('register/verify', {ceremony_id, credential}, signal);
  },
  register: async (label: string, signal?: AbortSignal) => {
    const {ceremony_id, options} = await post<{ceremony_id: string; options: PublicKeyCredentialCreationOptionsJSON}>('register/options', {label}, signal);
    signal?.throwIfAborted();
    const credential = await startRegistration({optionsJSON: options});
    signal?.throwIfAborted();
    return post<AuthSession>('register/verify', {ceremony_id, credential}, signal);
  },
  logout: () => post<{ok: true}>('logout'),
  session: () => requestJson<AuthSession>('/api/auth/session', {cache: 'no-store'}),
  login: async (signal?: AbortSignal) => {
    const {ceremony_id, options} = await post<{ceremony_id: string; options: PublicKeyCredentialRequestOptionsJSON}>('login/options', {}, signal);
    signal?.throwIfAborted();
    const credential = await startAuthentication({optionsJSON: options});
    signal?.throwIfAborted();
    return post<AuthSession>('login/verify', {ceremony_id, credential}, signal);
  },
};

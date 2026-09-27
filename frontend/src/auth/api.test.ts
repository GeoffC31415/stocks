import { afterEach, expect, it, vi } from "vitest";
import { api, requestJson, cancelPendingRequests } from "../lib/api";

afterEach(() => vi.unstubAllGlobals());
it('aborts outstanding API requests and rejects late responses after a lock', async () => {
  let resolve!: (value: Response) => void;
  const transport = vi.fn().mockReturnValue(new Promise<Response>(r => {resolve=r;}));
  vi.stubGlobal('fetch', transport);
  const pending = requestJson('/api/private');
  cancelPendingRequests();
  expect(transport.mock.calls[0][1].signal.aborted).toBe(true);
  resolve(new Response('{"private":true}'));
  await expect(pending).rejects.toMatchObject({name:'AbortError'});
});
it.each([
  () => requestJson('/api/portfolio'),
  () => api.deleteGroup(1),
  () => api.deleteAccountAlias(1),
  () => api.deleteInstrumentAlias(1),
])('notifies the auth gate on every private API 401', async (request) => {
  const expired = vi.fn();
  window.addEventListener('stocks:auth-required', expired);
  const transport = vi.fn().mockResolvedValue(new Response('{"detail":"Sign in"}', {status:401}));
  vi.stubGlobal('fetch', transport);
  await expect(request()).rejects.toThrow('Sign in');
  expect(expired).toHaveBeenCalledTimes(1);
  expect(transport.mock.calls[0][1]).toMatchObject({credentials:'same-origin'});
  window.removeEventListener('stocks:auth-required', expired);
});

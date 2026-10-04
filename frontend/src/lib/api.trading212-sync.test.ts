import { afterEach, expect, it, vi } from "vitest";
import { api } from "./api";

afterEach(() => vi.unstubAllGlobals());

it.each([
  ["requestTrading212Sync", "POST"],
  ["getRequestedTrading212SyncStatus", "GET"],
] as const)("%s uses only the isolated service endpoint without arguments", async (method, verb) => {
  const status = { state: "accepted", request_id: "t212-run" };
  const transport = vi.fn().mockResolvedValue(new Response(JSON.stringify(status)));
  vi.stubGlobal("fetch", transport);
  expect(await api[method]()).toEqual(status);
  expect(transport).toHaveBeenCalledOnce();
  const [url, options] = transport.mock.calls[0];
  expect(url).toBe("/api/sync/trading212/request");
  expect(options.method ?? "GET").toBe(verb);
  expect(options.credentials).toBe("same-origin");
  expect(options.body).toBeUndefined();
  expect(options.signal).toBeInstanceOf(AbortSignal);
});

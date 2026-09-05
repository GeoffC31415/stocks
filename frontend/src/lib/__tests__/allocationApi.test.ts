import { afterEach, expect, it, vi } from "vitest";
import { api } from "../api";

afterEach(() => vi.unstubAllGlobals());

it("requests the selected allocation dimension and URL-encodes the account", async () => {
  const payload = { dimension: "currency", totalValue: 104 };
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => payload });
  vi.stubGlobal("fetch", fetcher);
  expect(await api.getAllocation("currency", "ISA & SIPP")).toEqual(payload);
  expect(fetcher).toHaveBeenCalledWith(
    "/api/portfolio/allocation?dimension=currency&group_by=security&account_name=ISA+%26+SIPP", undefined,
  );
});

it("surfaces allocation endpoint errors", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: false, json: async () => ({ detail: "Allocation unavailable" }),
  }));
  await expect(api.getAllocation()).rejects.toThrow("Allocation unavailable");
});

it("sends explicit position grouping without changing account scope", async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
  vi.stubGlobal("fetch", fetcher);
  await api.getAllocation("account", "ISA", "position");
  expect(fetcher).toHaveBeenCalledWith(
    "/api/portfolio/allocation?dimension=account&group_by=position&account_name=ISA", undefined,
  );
});

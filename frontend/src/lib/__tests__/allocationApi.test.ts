import { afterEach, expect, it, vi } from "vitest";
import { api } from "../api";

afterEach(() => vi.unstubAllGlobals());

it("requests the selected allocation dimension and URL-encodes the account", async () => {
  const payload = { dimension: "currency", totalValue: 104 };
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => payload });
  vi.stubGlobal("fetch", fetcher);
  expect(await api.getAllocation("currency", "ISA & SIPP")).toEqual(payload);
  expect(fetcher).toHaveBeenCalledWith(
    "/api/portfolio/allocation?dimension=currency&account_name=ISA+%26+SIPP", undefined,
  );
});

it("surfaces allocation endpoint errors", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: false, json: async () => ({ detail: "Allocation unavailable" }),
  }));
  await expect(api.getAllocation()).rejects.toThrow("Allocation unavailable");
});

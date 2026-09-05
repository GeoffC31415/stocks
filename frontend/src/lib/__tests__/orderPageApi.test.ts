import { expect, it } from "vitest";
import { orderPageParams } from "../orderPageApi";

it("preserves repeated instrument/group filters and exact account without leaking performance scope", () => {
  const query = orderPageParams(new URLSearchParams("offset=100&instrument_ids=2&instrument_ids=3&group_ids=7&from_date=2026-01-01&period=1Y&tab=orders"), "ISA & pension");
  expect(query.getAll("instrument_ids")).toEqual(["2", "3"]);
  expect(query.getAll("group_ids")).toEqual(["7"]);
  expect(query.get("account_name")).toBe("ISA & pension");
  expect(query.get("offset")).toBe("100");
  expect(query.get("from_date")).toBe("2026-01-01");
  expect(query.has("period")).toBe(false);
  expect(query.has("tab")).toBe(false);
});

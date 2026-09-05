import { describe, expect, it } from "vitest";
import golden from "../../../../backend/tests/fixtures/allocation_golden.json";
import type { Instrument } from "../api";
import { calculateAllocation, type AllocationDimension } from "./allocationOracle";

// Keep this legacy oracle until the endpoint migration is complete. Both
// languages consume the same fixtures; do not regenerate expected values from Python.
describe("shared backend allocation golden parity", () => {
  for (const testCase of golden) {
    it(`${testCase.dimension} / ${testCase.account_name ?? "all"}`, () => {
      const rows = testCase.instruments.filter(
        (row) => testCase.account_name === null || row.account_name === testCase.account_name,
      );
      expect(calculateAllocation(rows as unknown as Instrument[], testCase.dimension as AllocationDimension))
        .toEqual(testCase.expected);
    });
  }
});

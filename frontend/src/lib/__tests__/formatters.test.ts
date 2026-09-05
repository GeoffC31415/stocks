import { describe, expect, it } from "vitest";
import { compactGbp, formatOrderDate, pct, signedGbp, toGbp, toGbpExact } from "../formatters";

describe("financial display formats (never calculation inputs)", () => {
  it("distinguishes missing values from real zero", () => {
    expect(toGbp(null)).toBe("—");
    expect(pct(undefined)).toBe("—");
    expect(toGbp(0)).toBe("£0");
    expect(toGbp(Infinity)).toBe("—");
  });
  it("keeps legacy whole-pound rounding and offers exact detail", () => {
    expect(toGbp(1234.56)).toBe("£1,235");
    expect(toGbpExact(1234.56)).toBe("£1,234.56");
    expect(toGbp(-0.1)).toBe("£0");
    expect(toGbpExact(-0.001)).toBe("£0.00");
    expect(pct(-0.001)).toBe("0.00%");
  });
  it("uses compact axes including millions and explicit signed outcomes", () => {
    expect(compactGbp(250000)).toBe("£250k");
    expect(compactGbp(1000000)).toBe("£1m");
    expect(signedGbp(1234.5)).toBe("+£1,235");
    expect(signedGbp(-1234.5)).toBe("−£1,235");
    expect(signedGbp(-0.1)).toBe("£0");
    expect(signedGbp(null)).toBe("—");
  });
  it("formats dates consistently in UTC and handles invalid dates", () => {
    expect(formatOrderDate("2026-01-01T00:30:00Z")).toBe("1 Jan 2026");
    expect(formatOrderDate("not a date")).toBe("—");
  });
});

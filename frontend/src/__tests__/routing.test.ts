import { describe, expect, it } from "vitest";
import { legacyRedirectUrl } from "../routing";

describe("legacyRedirectUrl", () => {
  it("preserves deep-link parameters while selecting the new workspace tab", () => {
    expect(legacyRedirectUrl("/portfolio", "holdings", "?inst=42")).toBe(
      "/portfolio?inst=42&tab=holdings",
    );
    expect(legacyRedirectUrl("/activity", "changes", "?from=2&to=3")).toBe(
      "/activity?from=2&to=3&tab=changes",
    );
  });
});

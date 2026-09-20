/**
 * S11 units test (Kanna 20-Sep directive rule 5).
 *
 * Allocation lives on the wire as a 0..1 fraction. The UI renders it as a
 * percent — one canonical unit on the wire, ×100 at render. This test pins
 * that behaviour so a full-time line never renders as "1.0000%" again.
 */
import { describe, expect, it } from "vitest";

import { formatAllocationPct } from "../../pages/v2/sow-studio/confirmation/StaffingGmSection";

describe("formatAllocationPct", () => {
  it("renders a 0..1 fraction as a percent (100, not 1.0000)", () => {
    expect(formatAllocationPct("1.0000")).toBe("100");
    expect(formatAllocationPct(1)).toBe("100");
  });

  it("renders 0.5 as 50", () => {
    expect(formatAllocationPct("0.5")).toBe("50");
  });

  it("renders 0.125 with one decimal (12.5)", () => {
    expect(formatAllocationPct("0.125")).toBe("12.5");
  });

  it("leaves non-numeric input unchanged so bad data is visible", () => {
    expect(formatAllocationPct("n/a")).toBe("n/a");
  });
});

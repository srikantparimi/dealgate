/**
 * S21 item 4 format rules — unit tests on the term-range formatter.
 *
 * The pre-S21 header path produced "10/12/2026 to April 12th" because
 * two different formatters stitched a start (ISO slice) to an end
 * (toLocaleDateString with no year). formatTermRange ensures both ends
 * use the same `MMM d, yyyy` shape with explicit year, and that the
 * open/open and open/closed cases don't degrade silently.
 */
import { describe, expect, it } from "vitest";
import { formatTermRange } from "../../pages/v2/sow-workspace/format";

describe("S21 item 4 · formatTermRange", () => {
  it("renders both ends in Oct 12, 2026 – Apr 12, 2027 form", () => {
    expect(formatTermRange("2026-10-12", "2027-04-12")).toBe("Oct 12, 2026 – Apr 12, 2027");
  });

  it("never emits the hybrid 10/12/2026 to April 12th shape", () => {
    const out = formatTermRange("2026-10-12", "2027-04-12")!;
    expect(out).not.toMatch(/\d{1,2}\/\d{1,2}\/\d{4}/);
    expect(out).not.toMatch(/\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b/);
  });

  it("open end renders as `(open)` not a dangling start", () => {
    expect(formatTermRange("2026-10-12", null)).toBe("Oct 12, 2026 – (open)");
  });

  it("open start renders as `(open) – end`", () => {
    expect(formatTermRange(null, "2027-04-12")).toBe("(open) – Apr 12, 2027");
  });

  it("returns null when both ends are missing (never a bare string)", () => {
    expect(formatTermRange(null, null)).toBeNull();
    expect(formatTermRange(undefined, undefined)).toBeNull();
  });
});

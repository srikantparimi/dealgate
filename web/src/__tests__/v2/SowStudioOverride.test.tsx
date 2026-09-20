/**
 * Field edits must reach the server (S10-11).
 *
 * Reported as "not able to edit this 5 fields". The pencil opened, the value
 * changed, the provenance chip flipped to `manual` — and none of it was ever
 * sent anywhere. `handleOverride` was `setState` and nothing else, with a
 * comment saying a follow-up story would persist it. A reload re-read the
 * untouched row and every edit was gone.
 */
import { describe, expect, it } from "vitest";
import { splitList } from "../../pages/v2/SowStudio";

describe("splitList", () => {
  it("turns an edited display string back into a list", () => {
    // Deliverables render joined; writing the joined string back would
    // replace a list of four with one sentence, and `FieldPatch.value` is
    // typed Any server-side so nothing would reject it.
    expect(
      splitList("Executive briefing; Use case inventory; Roadmap sketch"),
    ).toEqual(["Executive briefing", "Use case inventory", "Roadmap sketch"]);
  });

  it("handles the separators these fields actually use", () => {
    expect(splitList("A | B | C")).toEqual(["A", "B", "C"]);
    expect(splitList("Jane Doe, John Roe")).toEqual(["Jane Doe", "John Roe"]);
  });

  it("does not invent entries from blanks or trailing separators", () => {
    expect(splitList("")).toEqual([]);
    expect(splitList("   ")).toEqual([]);
    expect(splitList("A; B;")).toEqual(["A", "B"]);
  });

  it("keeps a single value as a one-item list, not a character split", () => {
    expect(splitList("Discovery report")).toEqual(["Discovery report"]);
  });
});

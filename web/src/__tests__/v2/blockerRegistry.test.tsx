/**
 * Rule 13 completeness test. A blocker key with no inline editor is
 * itself a bug — adding a blocker to the server without adding an entry
 * here must fail the build.
 *
 * The canonical list below mirrors every `needs_you.field` value the
 * server can emit today (see `api/app/services/sow_confirmation.py::_needs_you`
 * plus the sibling `SowFieldName` union in `web/src/api/client.ts`).
 * When a new blocker key ships, add it to CANONICAL_BLOCKER_KEYS AND to
 * the BLOCKER_REGISTRY in one PR.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as client from "../../api/client";
import {
  BLOCKER_REGISTRY,
  assertRegistered,
  lookupBlocker,
} from "../../pages/v2/sow-studio/confirmation/blockerRegistry";

const CANONICAL_BLOCKER_KEYS = [
  "scope_summary",
  "price",
  "currency",
  "billing_basis",
  "term_start",
  "term_end",
  "notice_date",
  "deliverables",
  "signatories",
  "engagement_type",
  "gm_model",
  "rate_card",
  "client_legal_name",
  "client_domain",
] as const;

describe("Rule 13 · blocker registry completeness", () => {
  it("has an editor for every canonical blocker key", () => {
    expect(() => assertRegistered(CANONICAL_BLOCKER_KEYS)).not.toThrow();
  });

  it("names the missing keys in the error message when one is dropped", () => {
    // Simulate an accidental deletion by looking up an unregistered key.
    const missing = "totally_not_a_field";
    expect(lookupBlocker(missing)).toBeNull();
    expect(() => assertRegistered([missing])).toThrow(/totally_not_a_field/);
    expect(() => assertRegistered([missing])).toThrow(/Rule 13/);
  });

  it("resolves subscripted keys back to their base entry", () => {
    // The server sometimes emits blockers like `signatories[0].email` or
    // `staffing[0].hourly_bill_rate` — the registry lookup folds those
    // to the base key so the row still resolves to a real editor.
    expect(lookupBlocker("signatories[0].email")?.label).toBe("Signatories");
    expect(lookupBlocker("gm_model.us_gm")?.label).toBe("Staffing & GM");
  });

  it("exports one entry per canonical key", () => {
    for (const key of CANONICAL_BLOCKER_KEYS) {
      expect(BLOCKER_REGISTRY[key], `missing registry entry for ${key}`).toBeDefined();
      expect(typeof BLOCKER_REGISTRY[key].Editor).toBe("function");
      expect(BLOCKER_REGISTRY[key].label.length).toBeGreaterThan(0);
    }
  });
});

/** S22 click-through fix · duration-aware term assist on the Confirm
 * page: "seven weeks from kickoff" SOWs get a derived end date as a
 * labeled, click-to-apply suggestion — never a silent guess. */
describe("Term assist in the date blockers", () => {
  function payload(fields: Record<string, unknown>) {
    return {
      sow_version: { id: "version-a", extracted_fields: fields },
    } as never;
  }
  const assist = {
    available: true,
    weeks: 7,
    source_field: "milestones",
    quote: "Week 7 — Roadmap & Executive Readout",
  };
  beforeEach(() => vi.restoreAllMocks());

  it("term start explains the kickoff role when the SOW states only a duration", async () => {
    vi.spyOn(client, "getTermAssist").mockResolvedValue(assist);
    const Editor = BLOCKER_REGISTRY.term_start.Editor;
    render(<Editor payload={payload({})} onChanged={() => {}} />);
    const hint = await screen.findByTestId("term-assist-hint");
    expect(hint).toHaveTextContent("7 weeks");
    expect(hint).toHaveTextContent("kickoff");
  });

  it("term end offers the derived date and saves it on one explicit click", async () => {
    vi.spyOn(client, "getTermAssist").mockResolvedValue({
      ...assist,
      start: "2026-10-01",
      suggested_end: "2026-11-18",
    });
    const confirm = vi
      .spyOn(client, "confirmSowField")
      .mockResolvedValue({} as never);
    const onChanged = vi.fn();
    const Editor = BLOCKER_REGISTRY.term_end.Editor;
    render(
      <Editor
        payload={payload({
          term_start: { value: "2026-10-01", status: "confirmed" },
        })}
        onChanged={onChanged}
      />,
    );
    const apply = await screen.findByTestId("term-assist-apply");
    expect(apply).toHaveTextContent("Use 2026-11-18 (kickoff + 7 weeks)");
    expect(confirm).not.toHaveBeenCalled(); // nothing until the click
    fireEvent.click(apply);
    await waitFor(() =>
      expect(confirm).toHaveBeenCalledWith("version-a", "term_end", "2026-11-18"),
    );
    expect(onChanged).toHaveBeenCalled();
  });

  it("term end without a kickoff points at term start instead of guessing", async () => {
    vi.spyOn(client, "getTermAssist").mockResolvedValue(assist);
    const Editor = BLOCKER_REGISTRY.term_end.Editor;
    render(<Editor payload={payload({})} onChanged={() => {}} />);
    const hint = await screen.findByTestId("term-assist-hint");
    expect(hint).toHaveTextContent("Set Term start");
    expect(screen.queryByTestId("term-assist-apply")).not.toBeInTheDocument();
  });
});

describe("Term assist from the staffing draft (round 3)", () => {
  it("one click fills BOTH term dates from the user's own plan", async () => {
    vi.spyOn(client, "getTermAssist").mockResolvedValue({
      available: true,
      source: "staffing_draft",
      suggested_start: "2026-10-01",
      suggested_end: "2026-12-01",
      quote: "dates from your Staffing & GM plan",
    });
    const confirm = vi
      .spyOn(client, "confirmSowField")
      .mockResolvedValue({} as never);
    const onChanged = vi.fn();
    const Editor = BLOCKER_REGISTRY.term_start.Editor;
    render(
      <Editor
        payload={{ sow_version: { id: "version-a", extracted_fields: {} } } as never}
        onChanged={onChanged}
      />,
    );
    const button = await screen.findByTestId("term-assist-from-plan");
    expect(button).toHaveTextContent("Use 2026-10-01 – 2026-12-01 from your staffing plan");
    fireEvent.click(button);
    await waitFor(() => expect(confirm).toHaveBeenCalledTimes(2));
    expect(confirm).toHaveBeenNthCalledWith(1, "version-a", "term_start", "2026-10-01");
    expect(confirm).toHaveBeenNthCalledWith(2, "version-a", "term_end", "2026-12-01");
    expect(onChanged).toHaveBeenCalled();
  });
});

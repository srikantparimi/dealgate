import { describe, expect, it } from "vitest";
import { buildRail, buildReadiness, nextValidStep, workspaceTitle, type WorkspaceSnapshot } from "../../pages/v2/sow-workspace/readiness";

const snap = (overrides = {}) => ({
  deal: { client_name: "Peppermill", engagement_type: "fixed_price" },
  sow: { id: "sow", confirmed_at: "2026-09-21", extracted_fields: {} },
  gmModel: { computed: { complete: true }, completeness_issues: [] },
  approvalPackage: null, agreements: [], signedSow: null,
  ...overrides,
}) as unknown as WorkspaceSnapshot;

describe("S14b workspace state", () => {
  it("never checks Scope & GM while scope is draft", () => {
    const draft = snap({ sow: { confirmed_at: null } });
    expect(nextValidStep(draft).label).toBe("Complete scope");
    expect(buildRail(draft).find(s => s.key === "scope_gm")?.state).toBe("current");
    expect(buildReadiness(draft).find(s => s.id === "scope")?.statusLabel).toBe("Draft");
  });
  it("offers submission without NDA or MSA", () => {
    expect(nextValidStep(snap())).toMatchObject({ label: "Submit for approval", action: "submit", disabled: false });
    expect(buildReadiness(snap()).find(s => s.id === "nda")?.hint).toContain("blocks signature, not review");
  });
  it("names incomplete financial inputs", () => {
    const incomplete = snap({ gmModel: { computed: { complete: false }, completeness_issues: ["Engineer hourly cost missing"] } });
    expect(nextValidStep(incomplete)).toMatchObject({ label: "Open Staffing & GM", reason: "Engineer hourly cost missing" });
  });
  it.each([
    ["pending_delivery_hr", "View review status"], ["pending_finance_legal", "View review status"],
    ["pending_ceo_exception", "Awaiting CEO decision"], ["ready_to_sign", "Prepare signature"],
    ["rejected", "Resolve review"], ["voided", "Submit for approval"], ["released", "View handoff"],
  ])("offers the next action for %s", (status, label) => {
    expect(nextValidStep(snap({ approvalPackage: { status, approvals: [] } })).label).toBe(label);
  });
  it("names conditions and the owner instead of offering signature", () => {
    const condition = snap({ approvalPackage: { status: "ready_to_sign", owner: { name: "Alex" }, ceo_exception: { conditions_unmet: true, conditions_text: "Client deposit received" } } });
    expect(nextValidStep(condition)).toMatchObject({ label: "Blocked: Client deposit received", href: "approvals" });
    expect(nextValidStep(condition).reason).toContain("Alex");
  });
  it("uses a human title, never a version hash", () => {
    expect(workspaceTitle(snap())).toBe("Peppermill · fixed price");
    expect(workspaceTitle(snap({ sow: { extracted_fields: { sow_title: { value: "Data platform modernization" } } } }))).toBe("Data platform modernization");
  });
});

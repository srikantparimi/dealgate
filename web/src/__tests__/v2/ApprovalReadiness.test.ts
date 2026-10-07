import { describe, expect, it } from "vitest";
import {
  buildRail,
  buildReadiness,
  nextValidStep,
  workspaceTitle,
  type WorkspaceSnapshot,
} from "../../pages/v2/sow-workspace/readiness";

const snap = (overrides = {}) =>
  ({
    deal: { client_name: "Peppermill", engagement_type: "fixed_price" },
    sow: { id: "sow", confirmed_at: "2026-09-21", extracted_fields: {} },
    gmModel: { computed: { complete: true }, completeness_issues: [] },
    approvalPackage: null,
    agreements: [],
    signedSow: null,
    ...overrides,
  }) as unknown as WorkspaceSnapshot;

describe("S14b workspace state", () => {
  it("names scope and GM owners and concrete missing inputs without inventing people", () => {
    const draft = snap({
      deal: { owner: { name: "Mira" } },
      sow: { confirmed_at: null },
      gmModel: {
        computed: { complete: false },
        completeness_issues: ["Cost version missing"],
      },
    });
    expect(
      buildReadiness(draft).find((row) => row.id === "scope"),
    ).toMatchObject({
      owner: "Mira",
      hint: expect.stringContaining("confirm"),
    });
    expect(buildReadiness(draft).find((row) => row.id === "gm")).toMatchObject({
      owner: "Mira",
      hint: expect.stringContaining("Cost version missing"),
    });
    expect(
      buildReadiness(snap()).find((row) => row.id === "scope")?.owner,
    ).toBe("Account owner (name unavailable)");
  });
  it("keeps reviewer identity, decision reason and actionable correction together", () => {
    const review = snap({
      approvalPackage: {
        status: "rejected",
        owner: { name: "Mira" },
        required_functions: ["delivery"],
        assignments: [
          {
            function: "delivery",
            approver_name: "Dev",
            active: true,
            blocked: false,
          },
        ],
        approvals: [
          {
            function: "delivery",
            decision: "request_changes",
            reason: "Clarify staffing dates",
          },
        ],
      },
    });
    expect(
      buildReadiness(review).find((row) => row.id === "fn-delivery"),
    ).toMatchObject({
      owner: "Mira",
      hint: expect.stringContaining("Clarify staffing dates"),
    });
    expect(
      buildReadiness(review).find((row) => row.id === "fn-delivery")?.hint,
    ).toContain("Dev");
  });
  it("identifies pending verification instead of claiming an upload is absent", () => {
    const uploaded = snap({
      approvalPackage: {
        id: "pkg",
        status: "ready_to_sign",
        owner: { name: "Mira" },
        approvals: [],
      },
      signedSow: { package_id: "pkg", verify_status: "pending" },
    });
    expect(
      buildReadiness(uploaded).find((row) => row.id === "signature"),
    ).toMatchObject({
      statusLabel: "Awaiting verification",
      owner: "Mira",
      hint: expect.stringContaining("Verify"),
    });
  });
  it("preserves the server signature blocker and does not accept another package's upload", () => {
    const blocked = snap({
      approvalPackage: { id: "pkg", status: "ready_to_sign", approvals: [] },
      signedSow: {
        package_id: "pkg",
        verify_status: "blocked",
        verify_reason: "Approved amount changed",
      },
    });
    expect(
      buildReadiness(blocked).find((row) => row.id === "signature")?.hint,
    ).toContain("Approved amount changed");
    const stale = {
      ...blocked,
      signedSow: {
        ...blocked.signedSow,
        package_id: "old",
        verify_status: "verified",
      },
    } as WorkspaceSnapshot;
    expect(
      buildReadiness(stale).find((row) => row.id === "signature")?.status,
    ).not.toBe("ok");
  });
  it("does not infer Delivery acceptance from release or a missing endpoint", () => {
    const released = snap({
      approvalPackage: { id: "pkg", status: "released", approvals: [] },
      signedSow: {
        package_id: "pkg",
        verify_status: "verified",
        released_at: "2026-10-03",
      },
    });
    expect(
      buildReadiness(released).find((row) => row.id === "delivery-acceptance"),
    ).toMatchObject({
      statusLabel: "Unavailable",
      owner: "Delivery",
      hint: expect.stringContaining("Handoff"),
    });
    expect(
      buildReadiness(released).find((row) => row.id === "handoff"),
    ).toMatchObject({
      statusLabel: "Released",
      hint: expect.stringContaining("release receipt"),
    });
  });
  it("uses real acceptance and gate checks to explain the next handoff step", () => {
    const waiting = snap({
      approvalPackage: {
        id: "pkg",
        status: "ready_to_sign",
        owner: { name: "Mira" },
        approvals: [],
      },
      signedSow: { package_id: "pkg", verify_status: "verified" },
      handoffGate: {
        ok: false,
        checks: { delivery_acceptance: false },
        reasons: ["Delivery acceptance missing"],
      },
      deliveryAcceptance: null,
    });
    expect(
      buildReadiness(waiting).find((row) => row.id === "delivery-acceptance"),
    ).toMatchObject({
      statusLabel: "Not recorded",
      hint: expect.stringContaining("staffing"),
    });
    expect(nextValidStep(waiting)).toMatchObject({
      label: "Review handoff",
      href: "handoff",
      reason: expect.stringContaining("Delivery acceptance missing"),
    });
    const accepted = {
      ...waiting,
      deliveryAcceptance: {
        package_id: "pkg",
        staffing_confirmed: true,
        billing_setup_confirmed: true,
        po_confirmed: true,
      },
    } as WorkspaceSnapshot;
    expect(
      buildReadiness(accepted).find((row) => row.id === "delivery-acceptance")
        ?.statusLabel,
    ).toBe("Recorded");
  });
  it("shows mandatory Sales alongside HR for a versioned S21 package", () => {
    const current = snap({
      approvalPackage: {
        status: "pending_delivery_hr",
        approvals: [],
        required_functions: ["delivery", "hr", "sales", "finance", "legal"],
      },
    });
    expect(
      buildReadiness(current).find((s) => s.id === "fn-sales")?.statusLabel,
    ).toBe("Pending");
    expect(
      buildReadiness(current).find((s) => s.id === "fn-hr")?.statusLabel,
    ).toBe("Pending");
  });
  it("never checks Scope & GM while scope is draft", () => {
    const draft = snap({ sow: { confirmed_at: null } });
    expect(nextValidStep(draft).label).toBe("Complete scope");
    expect(buildRail(draft).find((s) => s.key === "scope_gm")?.state).toBe(
      "current",
    );
    expect(
      buildReadiness(draft).find((s) => s.id === "scope")?.statusLabel,
    ).toBe("Draft");
  });
  it("offers submission and shows the S17 NDA/MSA note only", () => {
    expect(nextValidStep(snap())).toMatchObject({
      label: "Submit for approval",
      action: "submit",
      disabled: false,
    });
    const note = buildReadiness(snap()).find((s) => s.id === "nda-msa");
    expect(note?.statusLabel).toBe("Not marked");
  });
  it("names incomplete financial inputs", () => {
    const incomplete = snap({
      gmModel: {
        computed: { complete: false },
        completeness_issues: ["Engineer hourly cost missing"],
      },
    });
    expect(nextValidStep(incomplete)).toMatchObject({
      label: "Open Staffing & GM",
      reason: "Engineer hourly cost missing",
    });
    expect(
      nextValidStep(incomplete, {
        activeTab: "staffing",
        commercial: {
          state: "blocked",
          blocker: "Row 1 · Architect: add a working calendar",
          blockerLabel: "row 1 calendar",
        },
      }),
    ).toMatchObject({
      label: "Fix row 1 calendar",
      action: "commercial",
      reason: "Row 1 · Architect: add a working calendar",
    });
  });
  it("offers save for a valid draft and approval after the saved version reloads", () => {
    const incomplete = snap({ gmModel: null });
    expect(
      nextValidStep(incomplete, {
        activeTab: "staffing",
        commercial: { state: "ready_to_save" },
      }),
    ).toMatchObject({
      label: "Save",
      action: "commercial",
    });
    const belowFloor = snap({
      gmModel: {
        computed: {
          complete: true,
          policy: { requires_ceo: true },
        },
      },
    });
    expect(nextValidStep(belowFloor)).toMatchObject({
      label: "Submit with CEO exception",
      action: "submit",
    });
  });
  it.each([
    ["pending_delivery_hr", "View review status"],
    ["pending_finance_legal", "View review status"],
    ["pending_ceo_exception", "Awaiting CEO decision"],
    ["ready_to_sign", "Prepare signature"],
    ["rejected", "Resolve review"],
    ["voided", "Submit for approval"],
    ["released", "View handoff"],
  ])("offers the next action for %s", (status, label) => {
    expect(
      nextValidStep(snap({ approvalPackage: { status, approvals: [] } })).label,
    ).toBe(label);
  });
  it("names conditions and the owner instead of offering signature", () => {
    const condition = snap({
      approvalPackage: {
        status: "ready_to_sign",
        owner: { name: "Alex" },
        ceo_exception: {
          conditions_unmet: true,
          conditions_text: "Client deposit received",
        },
      },
    });
    expect(nextValidStep(condition)).toMatchObject({
      label: "Blocked: Client deposit received",
      href: "approvals",
    });
    expect(nextValidStep(condition).reason).toContain("Alex");
  });
  it("uses a human title, never a version hash", () => {
    expect(workspaceTitle(snap())).toBe("Peppermill · fixed price");
    expect(
      workspaceTitle(
        snap({
          sow: {
            extracted_fields: {
              sow_title: { value: "Data platform modernization" },
            },
          },
        }),
      ),
    ).toBe("Data platform modernization");
  });
});

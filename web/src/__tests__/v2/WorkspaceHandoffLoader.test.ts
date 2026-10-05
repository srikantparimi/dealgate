import { beforeEach, expect, it, vi } from "vitest";
import * as api from "../../api/client";
import { loadWorkspace } from "../../pages/v2/sow-workspace/dataLoader";

vi.mock("../../api/client", async (original) => ({
  ...await original<typeof import("../../api/client")>(),
  getDeal: vi.fn(), getCurrentSowVersion: vi.fn(), getLatestDeliveryModel: vi.fn(),
  listAgreements: vi.fn(), listApprovalPackages: vi.fn(), getApprovalPackage: vi.fn(),
  getSignedSowUpload: vi.fn(), getHandoffGate: vi.fn(), getDeliveryAcceptance: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getDeal).mockResolvedValue(null as never);
  vi.mocked(api.getCurrentSowVersion).mockResolvedValue(null as never);
  vi.mocked(api.getLatestDeliveryModel).mockResolvedValue({ gm_model: null });
  vi.mocked(api.listApprovalPackages).mockResolvedValue({ items: [{ id: "pkg-a" }], total: 1, page: 1, size: 200 } as never);
  vi.mocked(api.getApprovalPackage).mockImplementation(async id => ({ id }) as never);
  vi.mocked(api.getSignedSowUpload).mockResolvedValue(null);
});

it("loads actual handoff checks and distinguishes no acceptance from unavailable", async () => {
  const gate = { ok: false, checks: { internal_signoff: true, client_execution: true,
    delivery_acceptance: false, approvals_current: true, not_superseded: true }, reasons: ["Delivery acceptance missing"] };
  vi.mocked(api.getHandoffGate).mockResolvedValue(gate);
  vi.mocked(api.getDeliveryAcceptance).mockResolvedValue(null);
  const result = await loadWorkspace("deal-a");
  expect(api.getHandoffGate).toHaveBeenCalledWith("pkg-a");
  expect(api.getDeliveryAcceptance).toHaveBeenCalledWith("pkg-a");
  expect(result.snap.handoffGate).toEqual(gate);
  expect(result.snap.deliveryAcceptance).toBeNull();
});

it("does not carry acceptance or gate from another package after an endpoint fails", async () => {
  vi.mocked(api.getHandoffGate).mockResolvedValue({ ok: true, checks: {}, reasons: [] } as never);
  vi.mocked(api.getDeliveryAcceptance).mockResolvedValue({ package_id: "pkg-a" } as never);
  expect((await loadWorkspace("deal-a")).snap.deliveryAcceptance?.package_id).toBe("pkg-a");
  vi.mocked(api.listApprovalPackages).mockResolvedValue({ items: [{ id: "pkg-b" }], total: 1, page: 1, size: 200 } as never);
  vi.mocked(api.getHandoffGate).mockRejectedValue(new Error("offline"));
  vi.mocked(api.getDeliveryAcceptance).mockRejectedValue(new Error("offline"));
  const next = await loadWorkspace("deal-b");
  expect(api.getHandoffGate).toHaveBeenLastCalledWith("pkg-b");
  expect(api.getDeliveryAcceptance).toHaveBeenLastCalledWith("pkg-b");
  expect(next.snap.handoffGate).toBeUndefined();
  expect(next.snap.deliveryAcceptance).toBeUndefined();
});

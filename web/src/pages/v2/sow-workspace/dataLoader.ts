import {
  ApiError,
  getApprovalPackage,
  getDeal,
  getLatestDeliveryModel,
  getSignedSowUpload,
  getSowVersion,
  listAgreements,
  listApprovalPackages,
  getCurrentSowVersion,
  type ApprovalPackage,
  type UUID,
} from "../../../api/client";
import type { WorkspaceSnapshot } from "./readiness";

/**
 * Load everything the SOW workspace needs in parallel. Every branch
 * degrades to `null`/`[]` if the endpoint is missing so a single 404
 * cannot blank out the whole page (spec §4).
 */
export async function loadWorkspace(id: UUID): Promise<{
  snap: WorkspaceSnapshot;
  degradedEndpoints: string[];
}> {
  const degraded: string[] = [];
  const swallow = async <T>(
    label: string,
    p: () => Promise<T>,
    fallback: T,
  ): Promise<T> => {
    try {
      return await p();
    } catch (err) {
      if (err instanceof ApiError) degraded.push(label);
      return fallback;
    }
  };

  const deal = await swallow("getDeal", () => getDeal(id), null);
  const sow = await swallow(
    "getCurrentSowVersion",
    () => getCurrentSowVersion(id),
    null,
  );
  const gmLatest = await swallow(
    "getLatestDeliveryModel",
    () => getLatestDeliveryModel(id),
    { gm_model: null },
  );
  const agreements = await swallow(
    "listAgreements",
    async () => (await listAgreements()).items,
    [],
  );
  const pkgList = await swallow(
    "listApprovalPackages",
    () => listApprovalPackages({ opportunity_id: id, size: 1 }),
    { items: [], page: 1, size: 1, total: 0 },
  );
  const packageSummary = pkgList.items[0] ?? null;
  let approvalPackage: ApprovalPackage | null = null;
  if (packageSummary) {
    approvalPackage = await swallow(
      "getApprovalPackage",
      () => getApprovalPackage(packageSummary.id),
      null,
    );
  }
  let signedSow = null;
  if (approvalPackage) {
    signedSow = await swallow(
      "getSignedSowUpload",
      () => getSignedSowUpload(approvalPackage.id),
      null,
    );
  }

  // Fetch an authoritative SowVersion once we know one — the `current`
  // helper returns a shallow projection.
  let sowFull = sow;
  if (sow && sow.id) {
    sowFull = await swallow(
      "getSowVersion",
      () => getSowVersion(sow.id),
      sow,
    );
  }

  return {
    snap: {
      deal,
      sow: sowFull,
      gmModel: gmLatest.gm_model,
      approvalPackage,
      agreements,
      signedSow,
    },
    degradedEndpoints: degraded,
  };
}

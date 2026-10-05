import { listApprovalPackages, type ApprovalPackage, type ApprovalPackageListResponse, type ListApprovalPackagesQuery } from "./client";

/** Keep cards and boards on one authorized population, including later pages. */
export async function loadApprovalPopulation(
  query: Omit<ListApprovalPackagesQuery, "page" | "size">,
): Promise<ApprovalPackageListResponse> {
  const items: ApprovalPackage[] = [];
  const identities = new Set<string>();
  let expected: number | null = null;
  let revision = query.population_revision;
  for (let page = 1; ; page++) {
    const response = await listApprovalPackages({ ...query, population_revision: revision, page, size: 100 });
    if (query.status === "in_review") {
      revision ??= response.population_revision ?? undefined;
      if (!revision || response.population_revision !== revision) {
        throw new Error("Approval packages changed while loading. Refresh to load the current list.");
      }
    }
    expected ??= response.total;
    if (response.total !== expected || (response.items.length === 0 && items.length < expected)) {
      throw new Error("Approval packages changed while loading. Refresh to load the current list.");
    }
    for (const item of response.items) {
      if (identities.has(item.id)) throw new Error("Approval packages changed while loading. Refresh to load the current list.");
      identities.add(item.id);
      items.push(item);
    }
    if (items.length === expected) return { ...response, items, page: 1, size: items.length };
    if (items.length > expected) throw new Error("Approval package count does not match the list. Refresh to reload.");
  }
}

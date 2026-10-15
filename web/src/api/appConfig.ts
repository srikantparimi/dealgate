// S23-PL2 B14/F19 · web-visible configuration from GET /api/config. The
// HubSpot portal id comes from the configuration Terraform already provides
// (HUBSPOT_PORTAL_ID); the web app no longer hard-codes it.
import { useEffect, useState } from "react";

import { request } from "./client";

export interface AppConfig {
  hubspot_portal_id: string | null;
}

let cached: Promise<AppConfig> | null = null;

/** Fetched once per page load; a failure is not cached, so the next caller retries. */
export function getAppConfig(): Promise<AppConfig> {
  if (!cached) {
    cached = request<AppConfig>(`/config`).catch((err: unknown) => {
      cached = null;
      throw err;
    });
  }
  return cached;
}

/** Test seam: forget the cached configuration. */
export function resetAppConfigCache(): void {
  cached = null;
}

/** `hubspotPortalId` is null while loading and when the deployment has none (links to HubSpot are then hidden). */
export function useAppConfig(): { hubspotPortalId: string | null; loading: boolean } {
  const [state, setState] = useState<{ hubspotPortalId: string | null; loading: boolean }>({
    hubspotPortalId: null,
    loading: true,
  });
  useEffect(() => {
    let live = true;
    getAppConfig()
      .then((cfg) => live && setState({ hubspotPortalId: cfg.hubspot_portal_id ?? null, loading: false }))
      .catch(() => live && setState({ hubspotPortalId: null, loading: false }));
    return () => {
      live = false;
    };
  }, []);
  return state;
}

export function hubspotDealUrl(portalId: string, hubspotDealId: string): string {
  return `https://app.hubspot.com/contacts/${encodeURIComponent(portalId)}/record/0-3/${encodeURIComponent(hubspotDealId)}`;
}

export function hubspotCompanyUrl(portalId: string, hubspotCompanyId: string): string {
  return `https://app.hubspot.com/contacts/${encodeURIComponent(portalId)}/record/0-2/${encodeURIComponent(hubspotCompanyId)}`;
}

export function hubspotNewDealUrl(portalId: string): string {
  return `https://app.hubspot.com/contacts/${encodeURIComponent(portalId)}/deal/new`;
}

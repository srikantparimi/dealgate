// S23-PL2 F1 / F14 / F19 · the page header: eyebrow, title, subtitle and the
// two actions. "↓ Export view" downloads every filtered row of the active tab
// (roles that may export); "＋ Create in HubSpot ↗" opens the portal's
// new-deal page with the portal id from /api/config (hidden without one).
import { hubspotNewDealUrl } from "../../../api/appConfig";
import { Button } from "../../../ui-v2/primitives/button";

/** Roles the export endpoint serves (the reports read roles; Presales excluded by policy, D20). */
export const EXPORT_ROLES: readonly string[] = [
  "Finance",
  "Legal",
  "CEO",
  "SystemAdmin",
  "Delivery",
  "HR",
  "SalesLeader",
  "Sales",
];

export function canExport(groups: readonly string[] | null | undefined): boolean {
  return (groups ?? []).some((group) => EXPORT_ROLES.includes(group));
}

export interface PipelineHeaderProps {
  showExport: boolean;
  exporting: boolean;
  onExport: () => void;
  hubspotPortalId: string | null;
}

export function PipelineHeader({ showExport, exporting, onExport, hubspotPortalId }: PipelineHeaderProps) {
  return (
    <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <p className="flex items-center gap-2 font-mono text-label uppercase text-primary-text">
          <span aria-hidden className="inline-block h-1.5 w-1.5 rounded-avatar bg-primary" />
          Commercial workspace
        </p>
        <h1 className="mt-1 text-page-mobile text-text sm:text-page">
          Pipeline
          <span aria-hidden className="text-primary">
            .
          </span>
        </h1>
        <p className="mt-1 text-body text-text-secondary">Every relationship. Every opportunity. One clear next step.</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {showExport ? (
          <Button variant="secondary" onClick={onExport} disabled={exporting} aria-busy={exporting}>
            <span aria-hidden>↓</span>
            Export view
          </Button>
        ) : null}
        {hubspotPortalId ? (
          <Button asChild>
            <a href={hubspotNewDealUrl(hubspotPortalId)} target="_blank" rel="noopener noreferrer">
              <span aria-hidden>＋</span>
              Create in HubSpot
              <span aria-hidden>↗</span>
            </a>
          </Button>
        ) : null}
      </div>
    </header>
  );
}

// S24-AG1 F1/F10 · the page header: eyebrow, title, subtitle and the four
// actions in the prototype's order. A write action the caller may not use stays
// visible, locked with its reason (LockedButton); until the caller's rights are
// known the write actions wait (disabled) instead of guessing.
import { LockedButton } from "../../../ui-v2/LockedButton";
import { Button } from "../../../ui-v2/primitives/button";
import type { AgreementRoles } from "./useAgreementsWorkspace";

/** The prototype's toast for "Attach standard copies…" pressed by anyone but SystemAdmin. */
export const BULK_LOCK_MESSAGE = "Only SystemAdmin can attach standard copies in bulk.";

export interface AgreementsHeaderProps {
  roles: AgreementRoles | null;
  exporting: boolean;
  onExport: () => void;
  onHubspotHints: () => void;
  onAttachStandard: () => void;
  onUpload: () => void;
}

export function AgreementsHeader({
  roles,
  exporting,
  onExport,
  onHubspotHints,
  onAttachStandard,
  onUpload,
}: AgreementsHeaderProps) {
  return (
    <header className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
      <div className="min-w-0 xl:flex-1">
        <p className="flex items-center gap-2 font-mono text-label uppercase text-primary-text">
          <span aria-hidden className="inline-block h-1.5 w-1.5 rounded-avatar bg-primary" />
          Commercial governance
        </p>
        <h1 className="mt-1 text-page-mobile text-text sm:text-page">
          NDA &amp; MSA
          <span aria-hidden className="text-primary">
            .
          </span>
        </h1>
        <p className="mt-1 text-body text-text-secondary">
          Standard copies cover existing clients and any pipeline clients you choose. Any client can have its own
          updated copy.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2 xl:shrink-0 xl:flex-nowrap">
        <Button variant="secondary" onClick={onExport} disabled={exporting} aria-busy={exporting}>
          <span aria-hidden>↓</span>
          Export view
        </Button>
        <Button variant="secondary" aria-haspopup="dialog" onClick={onHubspotHints}>
          HubSpot hints
        </Button>
        <LockedButton
          variant="secondary"
          aria-haspopup="dialog"
          lock={roles && !roles.isAdmin ? "admin" : null}
          lockMessage={BULK_LOCK_MESSAGE}
          disabled={roles === null}
          onClick={onAttachStandard}
        >
          Attach standard copies…
        </LockedButton>
        <LockedButton
          aria-haspopup="dialog"
          lock={roles && !roles.canWrite ? "writer" : null}
          disabled={roles === null}
          onClick={onUpload}
        >
          <span aria-hidden>↑</span>
          Upload document
        </LockedButton>
      </div>
    </header>
  );
}

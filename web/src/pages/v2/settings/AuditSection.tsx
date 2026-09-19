/**
 * Settings → Audit log (spec §18).
 *
 * Reuses the legacy `AuditPage` (S1). That page already renders the
 * filters, table + chain-verify action per spec. Wrapping instead of
 * duplicating keeps a single source of truth for the audit UI.
 *
 * Routine users see relevant activity inside record tabs (My work,
 * Client detail, etc.) and never need this admin surface — the nav in
 * `nav.ts` gates the entry.
 */

import { AuditPage } from "../../Audit";

export function AuditSection() {
  return (
    <div className="flex flex-col gap-4">
      <AuditPage />
    </div>
  );
}

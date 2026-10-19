// S24-AG1 F1/B4 · the two standard-document panels. Not uploaded: the
// prototype's sentence and "↑ Upload standard {kind}". Uploaded: the current
// version, file and size, who uploaded it and when (Pacific date), how many
// clients hold this version, Download (every role; audited) and "Upload new
// version" (Legal and SystemAdmin; locked with the reason for everyone else).
import { useId } from "react";

import { AGREEMENT_KINDS, type AgreementKind, type StandardDocuments, type StandardVersion } from "../../../api/agreements";
import { AgreementTag } from "../../../ui-v2/AgreementStateTag";
import { LockedButton } from "../../../ui-v2/LockedButton";
import { Button } from "../../../ui-v2/primitives/button";
import { plural } from "../pipeline/format";
import { fileSizeText, pacificDate } from "./agreementsFormat";
import type { AgreementRoles } from "./useAgreementsWorkspace";

export interface StandardPanelsProps {
  standard: StandardDocuments;
  roles: AgreementRoles | null;
  onUpload: (kind: AgreementKind) => void;
  onDownload: (kind: AgreementKind) => void;
}

export function StandardPanels({ standard, roles, onUpload, onDownload }: StandardPanelsProps) {
  return (
    <section aria-label="Standard documents" className="grid gap-3 md:grid-cols-2">
      {AGREEMENT_KINDS.map((kind) => (
        <StandardPanel
          key={kind}
          kind={kind}
          version={standard[kind]}
          roles={roles}
          onUpload={() => onUpload(kind)}
          onDownload={() => onDownload(kind)}
        />
      ))}
    </section>
  );
}

function StandardPanel({
  kind,
  version,
  roles,
  onUpload,
  onDownload,
}: {
  kind: AgreementKind;
  version: StandardVersion | null;
  roles: AgreementRoles | null;
  onUpload: () => void;
  onDownload: () => void;
}) {
  const titleId = useId();
  const lock = roles && !roles.canWrite ? "writer" : null;
  const size = version ? fileSizeText(version.file_size) : null;
  return (
    <article
      aria-labelledby={titleId}
      className="flex min-w-0 flex-col gap-2 rounded-card border border-border bg-surface p-4"
    >
      <h3 id={titleId} className="flex flex-wrap items-center gap-2 text-section text-text">
        {`Standard ${kind}`}
        {version ? (
          <AgreementTag tone="progress" wrap={false}>
            {`v${version.version}`}
          </AgreementTag>
        ) : null}
      </h3>
      {version ? (
        <>
          <p className="text-body text-text [overflow-wrap:anywhere]">
            {size ? `${version.file_name} · ${size}` : version.file_name}
          </p>
          <p className="text-secondary text-text-secondary">
            {`Uploaded by ${version.uploaded_by} · ${pacificDate(version.uploaded_at)} · attached to ${version.attached_clients} ${plural(version.attached_clients, "client", "clients")}`}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={onDownload} aria-label={`Download the standard ${kind}`}>
              <span aria-hidden>↓</span>
              Download
            </Button>
            <LockedButton
              variant="secondary"
              aria-haspopup="dialog"
              aria-label={`Upload new version of the standard ${kind}`}
              lock={lock}
              disabled={roles === null}
              onClick={onUpload}
            >
              Upload new version
            </LockedButton>
          </div>
          <p className="text-secondary text-text-secondary">A new version does not change copies already attached.</p>
        </>
      ) : (
        <>
          <p className="text-secondary text-text-secondary">
            Not uploaded yet. Upload it once, then attach it to every existing client in one step.
          </p>
          <div className="flex flex-wrap gap-2">
            <LockedButton aria-haspopup="dialog" lock={lock} disabled={roles === null} onClick={onUpload}>
              <span aria-hidden>↑</span>
              {`Upload standard ${kind}`}
            </LockedButton>
          </div>
        </>
      )}
    </article>
  );
}

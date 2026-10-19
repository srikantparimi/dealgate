// S24-AG1 FE-A test stand-ins for the shared dialogs and the client panel (lane
// FE-B builds the real ones). The page opens them only through their fixed
// props, so these stand-ins show exactly what the page passed and let a test
// close them or report a change, without depending on their internals.
import type { AttachWizardProps } from "../../pages/v2/agreements/AttachWizard";
import type { ClientAgreementsPanelProps } from "../../pages/v2/agreements/ClientAgreementsPanel";
import type { HubspotHintsDialogProps } from "../../pages/v2/agreements/HubspotHintsDialog";
import type { UndoBatchDialogProps } from "../../pages/v2/agreements/UndoBatchDialog";
import type { UploadDialogProps } from "../../pages/v2/agreements/UploadDialog";

export function UploadDialogStandIn(props: UploadDialogProps) {
  if (!props.open) return null;
  const t = props.target;
  return (
    <div
      role="dialog"
      aria-label="Upload dialog stand-in"
      data-mode={t?.mode ?? ""}
      data-client={t?.clientId ?? ""}
      data-client-name={t?.clientName ?? ""}
      data-kind={t?.kind ?? ""}
      data-lock-target={String(Boolean(t?.lockTarget))}
      data-can-write={String(props.canWrite)}
    >
      <button type="button" onClick={() => props.onOpenChange(false)}>
        Close upload
      </button>
      <button
        type="button"
        onClick={() =>
          props.onUploaded({ mode: t?.mode ?? "client", kind: t?.kind ?? "NDA", clientId: t?.clientId ?? null })
        }
      >
        Finish upload
      </button>
    </div>
  );
}

export function ClientAgreementsPanelStandIn(props: ClientAgreementsPanelProps) {
  if (!props.open) return null;
  return (
    <div role="dialog" aria-label="Client panel stand-in" data-client={props.clientId} data-variant={props.variant}>
      <button type="button" onClick={() => props.onOpenChange?.(false)}>
        Close panel
      </button>
      <button type="button" onClick={() => props.onChanged?.()}>
        Report a change
      </button>
    </div>
  );
}

export function AttachWizardStandIn(props: AttachWizardProps) {
  if (!props.open) return null;
  return (
    <div role="dialog" aria-label="Attach wizard stand-in">
      <button type="button" onClick={() => props.onOpenChange(false)}>
        Close wizard
      </button>
    </div>
  );
}

export function UndoBatchDialogStandIn(props: UndoBatchDialogProps) {
  if (!props.open) return null;
  return (
    <div role="dialog" aria-label="Undo dialog stand-in" data-label={props.label ?? ""}>
      <button type="button" onClick={() => props.onOpenChange(false)}>
        Close undo
      </button>
    </div>
  );
}

export function HubspotHintsDialogStandIn(props: HubspotHintsDialogProps) {
  if (!props.open) return null;
  return (
    <div role="dialog" aria-label="HubSpot hints stand-in" data-admin={String(props.isAdmin)}>
      <button type="button" onClick={() => props.onOpenChange(false)}>
        Close hints
      </button>
    </div>
  );
}

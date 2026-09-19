/**
 * Agreement state → display copy + StatusBadge tone.
 *
 * Spec §7 lists the ten lifecycle states the pipeline surfaces. The API
 * enum in `web/src/api/client.ts` is the source of truth; this helper
 * only picks a label and a tone so a Missing NDA never accidentally
 * looks Executed. The "sent" state is displayed as "Awaiting signature"
 * per spec §7 — an envelope out to the client is not the same thing as
 * legal execution.
 */

import type { AgreementState } from "../../../api/client";
import type { StatusTone } from "../../../ui-v2/StatusBadge";

export interface AgreementDisplay {
  label: string;
  tone: StatusTone;
}

export function agreementDisplay(
  state: AgreementState | null | undefined,
): AgreementDisplay {
  switch (state) {
    case "missing":
      return { label: "Missing", tone: "warn" };
    case "requested":
      return { label: "Requested", tone: "neutral" };
    case "drafting":
      return { label: "Drafting", tone: "neutral" };
    case "under_review":
      return { label: "Under review", tone: "warn" };
    case "sent":
      // Spec §7: display "sent for signature" as "Awaiting signature".
      return { label: "Awaiting signature", tone: "warn" };
    case "partially_signed":
      return { label: "Partially signed", tone: "warn" };
    case "executed":
      return { label: "Executed", tone: "ok" };
    case "expired":
      return { label: "Expired", tone: "danger" };
    case "terminated":
      return { label: "Terminated", tone: "danger" };
    case "superseded":
      return { label: "Superseded", tone: "neutral" };
    default:
      // No agreement record at all → treated as Missing per spec §7:
      // "New entities start with Missing NDA/MSA until verified evidence
      // is associated."
      return { label: "Missing", tone: "warn" };
  }
}

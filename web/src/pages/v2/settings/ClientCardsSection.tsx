/**
 * Settings → Client rate cards (S9 wave 1).
 *
 * Per-client bill-rate cards, versioned + effective-dated, sourced from
 * the MSA rate schedule or manual entry. This section is deliberately a
 * "pick a client to open the editor" surface — a blank landing without a
 * client is a legitimate empty state (the list of clients is huge and
 * lives under the Clients navigation, not here).
 *
 * Per docs/directives/sow-first.md: client cards, cost bands and margin
 * policy are three different tables. This page never displays or edits
 * HR cost bands or margin floors — they have their own subsections.
 */

import { PageHeader } from "../../../ui-v2/PageHeader";
import { EmptyState } from "../../../ui-v2/EmptyState";

export function ClientCardsSection() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Client rate cards"
        subtitle={
          "Bill-rate cards per client legal entity. Import from the MSA " +
          "rate schedule or enter manually — cost bands and margin floors " +
          "live in their own sections."
        }
      />
      <EmptyState
        title="Pick a client to view its rate card"
        description={
          "Open a client from the Clients list to see the active version, " +
          "publish a new one, or import from an MSA. Clients with no card " +
          "trigger a loud fallback warning on every SOW."
        }
      />
    </div>
  );
}

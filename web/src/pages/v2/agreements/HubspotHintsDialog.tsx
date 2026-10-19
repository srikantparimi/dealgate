// S24-AG1 F5 · HubSpot msa_type hints. GET /agreements/hubspot-values lists the raw values the sync
// stored, with client counts, the saved mapping and, per value, how many clients holding nothing for the
// MSA would be marked (would_mark). SystemAdmin chooses values; nothing is saved until "Apply mapping",
// which saves the mapping and applies it. A saved mapping is then applied again after every successful
// nightly sync, so choosing is never a commitment on its own. The server marks only clients that hold
// nothing for the MSA, so DealGate's record always wins. Everyone else reads.
import { useEffect, useId, useState } from "react";

import {
  applyHubspotMapping,
  getHubspotValues,
  saveHubspotMapping,
  type HubspotValues,
} from "../../../api/agreements";
import { LockedButton } from "../../../ui-v2/LockedButton";
import { Button } from "../../../ui-v2/primitives/button";
import { AgreementsDrawer, useOpenSession } from "./UploadDialog";
import { AgreementNote, SELECT_CLASS, errorText, plural, useSafeToast } from "./UploadForm";

export interface HubspotHintsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** SystemAdmin edits and applies; everyone else reads. */
  isAdmin: boolean;
  onChanged: () => void;
}

type Action = "covered" | "ignore";

export function HubspotHintsDialog(props: HubspotHintsDialogProps) {
  const session = useOpenSession(props.open);
  return <HintsSession key={session} {...props} />;
}

/** Clients the chosen mapping would mark: the server's per-value count, summed over values mapped to Covered. */
function wouldMarkOf(values: HubspotValues | null): number | null {
  if (!values) return null;
  let total = 0;
  for (const item of values.items) {
    if (item.action !== "covered") continue;
    if (typeof item.would_mark !== "number") return null;
    total += item.would_mark;
  }
  return total;
}

function HintsSession({ open, onOpenChange, isAdmin, onChanged }: HubspotHintsDialogProps) {
  const toast = useSafeToast();
  const ids = useId();
  const [values, setValues] = useState<HubspotValues | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!open) return;
    let live = true;
    setLoadError(null);
    getHubspotValues()
      .then((next) => {
        if (live) setValues(next);
      })
      .catch((err: unknown) => {
        if (live) setLoadError(errorText(err, "The msa_type values could not load."));
      });
    return () => {
      live = false;
    };
  }, [open, reload]);

  function choose(value: string, action: Action) {
    if (!values || !isAdmin) return;
    setError(null);
    setValues({ ...values, items: values.items.map((item) => (item.value === value ? { ...item, action } : item)) });
  }

  async function apply() {
    if (applying || !values) return;
    setApplying(true);
    setError(null);
    try {
      await saveHubspotMapping(values.items.map((item) => ({ value: item.value, action: item.action })));
      const answer = await applyHubspotMapping(false);
      toast(`MSA marked covered for ${answer.marked} ${plural(answer.marked, "client", "clients")}.`);
      onChanged();
      onOpenChange(false);
    } catch (err) {
      setError(errorText(err, "The mapping could not be applied."));
    } finally {
      setApplying(false);
    }
  }

  const wouldMark = wouldMarkOf(values);

  let body;
  if (loadError) {
    body = (
      <div role="alert" className="flex flex-col items-start gap-2">
        <AgreementNote tone="warning">{loadError}</AgreementNote>
        <Button variant="secondary" onClick={() => setReload((n) => n + 1)}>
          Try again
        </Button>
      </div>
    );
  } else if (!values) {
    body = (
      <p role="status" className="text-body text-text-secondary">
        Loading the msa_type values…
      </p>
    );
  } else if (!values.stored) {
    body = (
      <>
        <p className="text-body text-text">
          HubSpot&apos;s deal record has a property called <code className="font-mono">msa_type</code>. The nightly sync
          stores its raw value, and the values it finds appear here for you to map. No value has been stored yet.
        </p>
        <p className="text-body text-text">
          Nothing is marked automatically until you map a value to “Covered”. DealGate&apos;s own record always wins,
          and marks made here stay even if HubSpot is switched off one day.
        </p>
        <div>
          <Button variant="secondary" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </div>
      </>
    );
  } else {
    body = (
      <>
        <p className="text-body text-text">
          Values found in <code className="font-mono">msa_type</code>. Map a value to Covered and the MSA is marked for
          clients that have no record yet. Clients that already have a file or mark are never changed.
        </p>
        {isAdmin ? (
          <p className="text-secondary text-text-secondary">
            Nothing is saved until you apply. After that, the nightly sync applies the saved mapping after each
            successful sync.
          </p>
        ) : null}
        {values.items.length ? (
          <ul className="flex flex-col rounded-card border border-border" aria-label="msa_type values">
            {values.items.map((item, i) => {
              const selectId = `${ids}-value-${i}`;
              return (
                <li
                  key={item.value}
                  className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-2 last:border-b-0"
                >
                  <label htmlFor={selectId} className="min-w-0 break-words text-body text-text [overflow-wrap:anywhere]">
                    {`“${item.value}”`}{" "}
                    <small className="text-secondary text-text-secondary">
                      {`${item.clients} ${plural(item.clients, "client", "clients")}`}
                    </small>
                  </label>
                  <select
                    id={selectId}
                    className={`${SELECT_CLASS} sm:w-auto`}
                    value={item.action}
                    disabled={!isAdmin}
                    onChange={(event) => choose(item.value, event.target.value as Action)}
                  >
                    <option value="ignore">Ignore</option>
                    <option value="covered">Mark MSA covered</option>
                  </select>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-body text-text-secondary">No msa_type value has been found on a synced deal yet.</p>
        )}
        {isAdmin && values.items.length ? (
          <p role="status" className="text-secondary text-text-secondary">
            {wouldMark !== null ? `${wouldMark} ${plural(wouldMark, "client", "clients")} would be marked.` : null}
          </p>
        ) : null}
        {error ? (
          <p role="alert" className="text-secondary text-danger">
            {error}
          </p>
        ) : null}
        <div className="flex flex-wrap gap-2">
          <LockedButton
            lock={isAdmin ? null : "admin"}
            onClick={() => void apply()}
            disabled={isAdmin && (applying || !values.items.length)}
            aria-busy={applying || undefined}
          >
            Apply mapping
          </LockedButton>
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={applying}>
            Close
          </Button>
        </div>
      </>
    );
  }

  return (
    <AgreementsDrawer
      open={open}
      onOpenChange={onOpenChange}
      kicker="Source: HubSpot"
      title="HubSpot hints"
      busy={applying}
    >
      {body}
    </AgreementsDrawer>
  );
}

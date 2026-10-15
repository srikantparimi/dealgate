/**
 * Settings → Users: each user's link to a HubSpot owner (S23-PL2 F18, API B4).
 *
 * The link decides "My opportunities" on the Pipeline. Sign-in and the nightly
 * owner sync match it automatically by email; an admin can pick another owner
 * (former HubSpot users included) or record that the user has none, and that
 * choice is never replaced automatically. Only names are shown, never ids.
 */

import { useEffect, useState } from "react";
import {
  listHubspotOwners,
  setUserHubspotOwner,
  type AdminUserRow,
  type HubspotOwnerOption,
} from "../../../api/client";
import { StatusBadge } from "../../../ui-v2/StatusBadge";
import { Button } from "../../../ui-v2/primitives/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../../../ui-v2/primitives/dialog";

const FORMER = "Former HubSpot user";

/** The linked owner as the Users table shows it. */
export function linkedOwnerText(user: AdminUserRow): string {
  if (!user.hubspot_owner_id) {
    return user.hubspot_owner_link === "admin" ? "No HubSpot owner" : "Not linked";
  }
  if (user.hubspot_owner_state === "archived") {
    return user.hubspot_owner_name ? `${user.hubspot_owner_name} · ${FORMER}` : FORMER;
  }
  return user.hubspot_owner_name ?? "HubSpot owner without a name";
}

function optionText(owner: HubspotOwnerOption, forUserId: string): string {
  const base = owner.name ?? owner.email ?? "HubSpot owner without a name";
  const name = owner.archived ? `${base} · ${FORMER}` : base;
  return owner.linked_user_id && owner.linked_user_id !== forUserId
    ? `${name} (linked to ${owner.linked_user_name ?? "another user"})`
    : name;
}

export function HubspotOwnerCell({ user, onChange }: { user: AdminUserRow; onChange: () => void }) {
  return (
    <span className="flex flex-col items-start gap-1">
      <span className={user.hubspot_owner_id ? "text-text" : "text-text-secondary"}>{linkedOwnerText(user)}</span>
      {user.hubspot_owner_link === "email" && <StatusBadge tone="success" label="Auto-matched by email" />}
      {user.hubspot_owner_link === "admin" && <StatusBadge tone="neutral" label="Set by an admin" />}
      <Button
        type="button"
        variant="tertiary"
        size="sm"
        aria-label={`Change HubSpot owner for ${user.name}`}
        onClick={onChange}
      >
        Change
      </Button>
    </span>
  );
}

export function HubspotOwnerDialog({
  user,
  onClose,
  onSaved,
}: {
  user: AdminUserRow | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [owners, setOwners] = useState<HubspotOwnerOption[] | null>(null);
  const [choice, setChoice] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!user) return;
    let live = true;
    setOwners(null);
    setError(null);
    setChoice(user.hubspot_owner_id ?? "");
    listHubspotOwners()
      .then((list) => live && setOwners(list))
      .catch((err: unknown) => live && setError(err instanceof Error ? err.message : "The HubSpot owners could not be loaded."));
    return () => {
      live = false;
    };
  }, [user]);

  async function save() {
    if (!user) return;
    setSaving(true);
    setError(null);
    try {
      await setUserHubspotOwner(user.id, choice || null);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The link could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  const active = (owners ?? []).filter((o) => !o.archived);
  const former = (owners ?? []).filter((o) => o.archived);
  const takenByOther = (o: HubspotOwnerOption) => Boolean(o.linked_user_id && user && o.linked_user_id !== user.id);

  return (
    <Dialog open={user !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        {user && (
          <>
            <DialogHeader>
              <DialogTitle>{`HubSpot owner for ${user.name}`}</DialogTitle>
              <DialogDescription>
                Deals owned by this HubSpot owner are this person&apos;s “My opportunities” on the Pipeline. Your
                choice replaces an automatic email match and is never changed automatically.
              </DialogDescription>
            </DialogHeader>
            <form
              className="flex flex-col gap-4"
              onSubmit={(event) => {
                event.preventDefault();
                void save();
              }}
            >
              <label className="flex flex-col gap-1 text-secondary text-text-secondary" htmlFor="hubspot-owner-choice">
                HubSpot owner
                <select
                  id="hubspot-owner-choice"
                  className="h-10 rounded-control border border-input-border bg-surface px-2 text-body text-text focus-visible:outline-focus"
                  value={choice}
                  disabled={owners === null || saving}
                  onChange={(event) => setChoice(event.target.value)}
                >
                  <option value="">No HubSpot owner</option>
                  {active.length > 0 && (
                    <optgroup label="Active HubSpot owners">
                      {active.map((o) => (
                        <option key={o.id} value={o.id} disabled={takenByOther(o)}>
                          {optionText(o, user.id)}
                        </option>
                      ))}
                    </optgroup>
                  )}
                  {former.length > 0 && (
                    <optgroup label="Former HubSpot users">
                      {former.map((o) => (
                        <option key={o.id} value={o.id} disabled={takenByOther(o)}>
                          {optionText(o, user.id)}
                        </option>
                      ))}
                    </optgroup>
                  )}
                </select>
              </label>
              {owners === null && !error && (
                <p className="text-secondary text-text-secondary">Loading the HubSpot owners…</p>
              )}
              {error && (
                <p role="alert" className="text-secondary text-danger">
                  {error}
                </p>
              )}
              <div className="flex justify-end gap-2">
                <Button type="button" variant="secondary" onClick={onClose} disabled={saving}>
                  Cancel
                </Button>
                <Button type="submit" disabled={owners === null || saving}>
                  {saving ? "Saving…" : "Save"}
                </Button>
              </div>
            </form>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

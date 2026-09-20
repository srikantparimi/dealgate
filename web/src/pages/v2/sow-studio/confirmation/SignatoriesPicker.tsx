/**
 * Signatories picker (docs/directives/one-staffing-model.md rule 6 +
 * docs/directives/gm-correctness.md root cause 4).
 *
 * The picker is a searchable combobox on both sides:
 *
 *   - Internal (People & access) — users in a governance group. Loaded
 *     from ``GET /signatories/internal``.
 *   - Client contact — signatories previously entered for the client on
 *     the SOW, plus an inline "+ Add contact" form that persists via
 *     ``POST /clients/{client_id}/contacts`` (idempotent on email).
 *
 * On pick the row is appended to the local list and the field is patched
 * via ``PATCH /sow/versions/{sow_version_id}/fields/signatories``. That
 * PATCH also clears the ``signatories`` blocker on the next confirmation
 * refresh — one write path per field, per docs/directives/sow-first.md.
 *
 * Every visible control is a real focusable input / button. "Jump to
 * field" that lands on a label with no editable target is the class of
 * defect gm-correctness §4 was written to stop.
 */
import { useEffect, useMemo, useState } from "react";
import { Trash2, UserPlus, X } from "lucide-react";
import {
  createClientContact,
  confirmSowField,
  listClientContacts,
  listInternalSignatories,
  type ClientContactRow,
  type InternalSignatoryRow,
  type PickedSignatory,
  type UUID,
} from "../../../../api/client";
import { Button } from "../../../../ui-v2/primitives/button";
import { Input } from "../../../../ui-v2/primitives/input";
import { Label } from "../../../../ui-v2/primitives/label";
import { cn } from "../../../../lib/cn";

export interface SignatoriesPickerProps {
  sowVersionId: UUID;
  clientId: UUID | null;
  /** Current value of the ``signatories`` field. May be null / string / array. */
  value: unknown;
  /**
   * Fires with the newly persisted list every time the picker mutates it.
   * Parents use this to update their optimistic copy of the confirmation
   * payload so the "What's still needed" blocker clears immediately.
   */
  onChange?: (next: PickedSignatory[]) => void;
  /** Optional dom id — overridden when the picker is embedded twice. */
  id?: string;
  className?: string;
}

/**
 * Turn whatever shape the ``signatories`` field is currently in on the
 * SOW into a list of normalised picker rows. Handles four legacy shapes:
 *
 *   - ``null`` / ``undefined``
 *   - ``string`` (a joined display value from an earlier free-text edit)
 *   - ``string[]`` (`splitList` output before the picker existed)
 *   - ``{name, role}[]`` (the extractor's output)
 *
 * Anything with a recognisable ``source`` key is passed through untouched.
 */
export function normaliseSignatories(raw: unknown): PickedSignatory[] {
  if (raw == null) return [];
  if (typeof raw === "string") {
    // A single free-text string from a legacy edit — split on the same
    // separators SowStudio.splitList uses so we do not fabricate one name
    // out of "J. Doe, A. Smith".
    return splitLegacyString(raw).map((name) => ({
      source: "client",
      name,
      email: "",
    }));
  }
  if (!Array.isArray(raw)) return [];
  const out: PickedSignatory[] = [];
  for (const item of raw) {
    if (item == null) continue;
    if (typeof item === "string") {
      const s = item.trim();
      if (!s) continue;
      out.push({ source: "client", name: s, email: "" });
      continue;
    }
    if (typeof item !== "object") continue;
    const rec = item as Record<string, unknown>;
    const name = typeof rec.name === "string" ? rec.name : "";
    if (!name) continue;
    const source =
      rec.source === "internal" || rec.source === "client"
        ? (rec.source as "internal" | "client")
        : "client";
    out.push({
      source,
      user_id: typeof rec.user_id === "string" ? rec.user_id : null,
      contact_id: typeof rec.contact_id === "string" ? rec.contact_id : null,
      name,
      email: typeof rec.email === "string" ? rec.email : "",
      title: typeof rec.title === "string" ? rec.title : null,
      role: typeof rec.role === "string" ? rec.role : null,
    });
  }
  return out;
}

function splitLegacyString(raw: string): string[] {
  const text = raw.trim();
  if (!text) return [];
  const sep = [";", "|"].find((c) => text.includes(c)) ?? ",";
  return text
    .split(sep)
    .map((part) => part.trim())
    .filter(Boolean);
}

function signatureKey(s: PickedSignatory): string {
  if (s.source === "internal" && s.user_id) return `internal:${s.user_id}`;
  if (s.source === "client" && s.contact_id) return `client:${s.contact_id}`;
  return `${s.source}:${(s.email || "").toLowerCase()}|${s.name.toLowerCase()}`;
}

/**
 * The picker component itself.
 *
 * It is rendered in two places — inside the NeedsYouSection blocker row
 * and inside the ScopeSection field row — so the parent owns nothing but
 * the load-refresh callback. The picker itself does the PATCH.
 */
export function SignatoriesPicker({
  sowVersionId,
  clientId,
  value,
  onChange,
  id,
  className,
}: SignatoriesPickerProps) {
  const [current, setCurrent] = useState<PickedSignatory[]>(() =>
    normaliseSignatories(value),
  );
  const [internal, setInternal] = useState<InternalSignatoryRow[]>([]);
  const [contacts, setContacts] = useState<ClientContactRow[]>([]);
  const [internalQuery, setInternalQuery] = useState("");
  const [contactQuery, setContactQuery] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [addName, setAddName] = useState("");
  const [addEmail, setAddEmail] = useState("");
  const [addTitle, setAddTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Keep the local list in sync when the parent re-renders with a fresh
  // payload (e.g. after a full reload from the server). Comparing on
  // signature so a re-render with an equivalent list doesn't clobber
  // an in-flight edit.
  useEffect(() => {
    const next = normaliseSignatories(value);
    const nextKey = next.map(signatureKey).join("");
    const curKey = current.map(signatureKey).join("");
    if (nextKey !== curKey) setCurrent(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  useEffect(() => {
    let cancelled = false;
    listInternalSignatories()
      .then((rows) => {
        if (!cancelled) setInternal(rows);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(
            e instanceof Error
              ? e.message
              : "could not load internal signatories",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!clientId) return;
    let cancelled = false;
    listClientContacts(clientId)
      .then((rows) => {
        if (!cancelled) setContacts(rows);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(
            e instanceof Error ? e.message : "could not load client contacts",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [clientId]);

  const pickedKeys = useMemo(
    () => new Set(current.map(signatureKey)),
    [current],
  );

  const internalFiltered = useMemo(() => {
    const q = internalQuery.trim().toLowerCase();
    return internal.filter((u) => {
      if (pickedKeys.has(`internal:${u.id}`)) return false;
      if (!q) return true;
      return (
        u.name.toLowerCase().includes(q) ||
        u.email.toLowerCase().includes(q)
      );
    });
  }, [internal, internalQuery, pickedKeys]);

  const contactsFiltered = useMemo(() => {
    const q = contactQuery.trim().toLowerCase();
    return contacts.filter((c) => {
      if (pickedKeys.has(`client:${c.id}`)) return false;
      if (!q) return true;
      return (
        c.name.toLowerCase().includes(q) ||
        c.email.toLowerCase().includes(q) ||
        (c.title ?? "").toLowerCase().includes(q)
      );
    });
  }, [contacts, contactQuery, pickedKeys]);

  async function persist(next: PickedSignatory[]) {
    setSaving(true);
    setError(null);
    // Optimistic — the parent needs the update straight away so the
    // blocker clears without waiting on the network.
    setCurrent(next);
    onChange?.(next);
    try {
      await confirmSowField(sowVersionId, "signatories", next);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "could not save the signatories list",
      );
    } finally {
      setSaving(false);
    }
  }

  async function pickInternal(u: InternalSignatoryRow) {
    const row: PickedSignatory = {
      source: "internal",
      user_id: u.id,
      name: u.name,
      email: u.email,
    };
    await persist([...current, row]);
    setInternalQuery("");
  }

  async function pickContact(c: ClientContactRow) {
    const row: PickedSignatory = {
      source: "client",
      contact_id: c.id,
      name: c.name,
      email: c.email,
      title: c.title,
    };
    await persist([...current, row]);
    setContactQuery("");
  }

  async function removeAt(index: number) {
    const next = current.slice();
    next.splice(index, 1);
    await persist(next);
  }

  async function submitAddContact() {
    if (!clientId) {
      setError("no client yet — pick one on the source row first");
      return;
    }
    const name = addName.trim();
    const email = addEmail.trim();
    if (!name || !email) {
      setError("name and email are required");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const created = await createClientContact(clientId, {
        name,
        email,
        title: addTitle.trim() || null,
      });
      setContacts((prev) => {
        // Idempotent server-side — dedupe on id when the same contact
        // comes back from a repeat call.
        const filtered = prev.filter((c) => c.id !== created.id);
        return [...filtered, created].sort((a, b) =>
          a.name.localeCompare(b.name),
        );
      });
      await pickContact(created);
      setAddName("");
      setAddEmail("");
      setAddTitle("");
      setShowAdd(false);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "could not create client contact",
      );
    } finally {
      setSaving(false);
    }
  }

  const rootId = id ?? "signatories-picker";

  return (
    <div
      id={rootId}
      data-testid="signatories-picker"
      className={cn("flex flex-col gap-3", className)}
    >
      {/* Current list */}
      <div className="flex flex-col gap-2" data-testid="signatories-current">
        {current.length === 0 ? (
          <p className="text-secondary text-text-secondary italic">
            No signatories yet — pick from the two lists below.
          </p>
        ) : (
          current.map((s, i) => (
            <div
              key={`${signatureKey(s)}-${i}`}
              className="flex items-center justify-between gap-2 rounded-panel border border-divider bg-surface-sunken px-3 py-2"
              data-testid={`signatory-row-${i}`}
            >
              <div className="min-w-0">
                <p className="text-body text-text font-medium">{s.name}</p>
                <p className="text-secondary text-text-secondary">
                  {[
                    s.source === "internal" ? "Internal" : "Client",
                    s.email || null,
                    s.title || s.role || null,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
              <Button
                type="button"
                variant="tertiary"
                size="sm"
                onClick={() => void removeAt(i)}
                disabled={saving}
                aria-label={`Remove ${s.name}`}
                data-testid={`signatory-remove-${i}`}
              >
                <Trash2 className="h-4 w-4" aria-hidden />
              </Button>
            </div>
          ))
        )}
      </div>

      {/* Two-panel add UI */}
      <div className="grid gap-3 md:grid-cols-2">
        {/* Internal */}
        <div className="flex flex-col gap-2 rounded-panel border border-divider bg-surface p-3">
          <Label htmlFor={`${rootId}-internal-input`}>
            Internal (People &amp; access)
          </Label>
          <Input
            id={`${rootId}-internal-input`}
            value={internalQuery}
            onChange={(e) => setInternalQuery(e.target.value)}
            placeholder="Search authorised signatories"
            data-testid="signatories-internal-input"
            autoComplete="off"
          />
          <ul
            role="listbox"
            aria-label="Internal signatories"
            className="max-h-48 overflow-y-auto rounded-control border border-divider bg-surface-sunken"
            data-testid="signatories-internal-list"
          >
            {internalFiltered.length === 0 ? (
              <li
                className="px-3 py-2 text-secondary text-text-secondary"
                data-testid="signatories-internal-empty"
              >
                {internal.length === 0
                  ? "No authorised signatories in People & access."
                  : "No matches."}
              </li>
            ) : (
              internalFiltered.map((u) => (
                <li key={u.id} role="option" aria-selected="false">
                  <button
                    type="button"
                    onClick={() => void pickInternal(u)}
                    disabled={saving}
                    data-testid={`signatories-internal-pick-${u.id}`}
                    className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-body text-text hover:bg-primary-subtle focus-visible:outline-focus"
                  >
                    <span className="min-w-0">
                      <span className="block font-medium">{u.name}</span>
                      <span className="block text-secondary text-text-secondary">
                        {u.email}
                      </span>
                    </span>
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>

        {/* Client */}
        <div className="flex flex-col gap-2 rounded-panel border border-divider bg-surface p-3">
          <div className="flex items-center justify-between gap-2">
            <Label htmlFor={`${rootId}-client-input`}>Client contact</Label>
            <Button
              type="button"
              variant="tertiary"
              size="sm"
              onClick={() => setShowAdd((v) => !v)}
              disabled={!clientId || saving}
              data-testid="signatories-add-toggle"
              aria-expanded={showAdd}
              aria-controls={`${rootId}-add-form`}
            >
              {showAdd ? (
                <>
                  <X className="h-4 w-4" aria-hidden /> Cancel
                </>
              ) : (
                <>
                  <UserPlus className="h-4 w-4" aria-hidden /> Add contact
                </>
              )}
            </Button>
          </div>
          <Input
            id={`${rootId}-client-input`}
            value={contactQuery}
            onChange={(e) => setContactQuery(e.target.value)}
            placeholder={
              clientId
                ? "Search client contacts"
                : "Pick a client on the source row first"
            }
            disabled={!clientId}
            data-testid="signatories-client-input"
            autoComplete="off"
          />
          <ul
            role="listbox"
            aria-label="Client contacts"
            className="max-h-48 overflow-y-auto rounded-control border border-divider bg-surface-sunken"
            data-testid="signatories-client-list"
          >
            {!clientId ? (
              <li className="px-3 py-2 text-secondary text-text-secondary">
                Client not resolved yet.
              </li>
            ) : contactsFiltered.length === 0 ? (
              <li
                className="px-3 py-2 text-secondary text-text-secondary"
                data-testid="signatories-client-empty"
              >
                {contacts.length === 0
                  ? "No contacts on file for this client."
                  : "No matches."}
              </li>
            ) : (
              contactsFiltered.map((c) => (
                <li key={c.id} role="option" aria-selected="false">
                  <button
                    type="button"
                    onClick={() => void pickContact(c)}
                    disabled={saving}
                    data-testid={`signatories-client-pick-${c.id}`}
                    className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-body text-text hover:bg-primary-subtle focus-visible:outline-focus"
                  >
                    <span className="min-w-0">
                      <span className="block font-medium">{c.name}</span>
                      <span className="block text-secondary text-text-secondary">
                        {[c.email, c.title].filter(Boolean).join(" · ")}
                      </span>
                    </span>
                  </button>
                </li>
              ))
            )}
          </ul>

          {showAdd ? (
            <form
              id={`${rootId}-add-form`}
              className="flex flex-col gap-2 rounded-control border border-divider bg-surface p-3"
              data-testid="signatories-add-form"
              onSubmit={(e) => {
                e.preventDefault();
                void submitAddContact();
              }}
            >
              <div className="flex flex-col gap-1">
                <Label htmlFor={`${rootId}-add-name`}>Name</Label>
                <Input
                  id={`${rootId}-add-name`}
                  value={addName}
                  onChange={(e) => setAddName(e.target.value)}
                  required
                  data-testid="signatories-add-name"
                  autoComplete="off"
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor={`${rootId}-add-email`}>Email</Label>
                <Input
                  id={`${rootId}-add-email`}
                  type="email"
                  value={addEmail}
                  onChange={(e) => setAddEmail(e.target.value)}
                  required
                  data-testid="signatories-add-email"
                  autoComplete="off"
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor={`${rootId}-add-title`}>Title (optional)</Label>
                <Input
                  id={`${rootId}-add-title`}
                  value={addTitle}
                  onChange={(e) => setAddTitle(e.target.value)}
                  data-testid="signatories-add-title"
                  autoComplete="off"
                />
              </div>
              <div className="flex items-center justify-end gap-2">
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  disabled={saving}
                  data-testid="signatories-add-submit"
                >
                  Add and pick
                </Button>
              </div>
            </form>
          ) : null}
        </div>
      </div>

      {error ? (
        <p
          role="alert"
          className="text-secondary text-danger"
          data-testid="signatories-error"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}

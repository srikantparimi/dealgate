/**
 * Handoff detail (`/handoffs/:id`) — spec §13.4.
 *
 * Extends the existing SignedSowReview flow (which lives at
 * `web/src/pages/SignedSOWReview.tsx`) with four additional panels
 * required by spec §13.4:
 *   1. Distribution — recipient list with delivery outcome, timestamps,
 *      retry with dedupe. Role-appropriate data (no salary leakage).
 *   2. Acknowledgement — Delivery + account owner confirm receipt.
 *   3. Setup checklist — kickoff, billing/PO, staffing, renewal record.
 *   4. Release evidence — the exact executed SOW/version link.
 *
 * A locally uploaded filename containing "signed" is not evidence of
 * execution — the verify diff is the authoritative gate (spec §12).
 */

import { useMemo, useState } from "react";
import { CheckCircle2, RefreshCw, ShieldAlert } from "lucide-react";
import { Button } from "../../../ui-v2/primitives/button";
import { StatusBadge } from "../../../ui-v2/StatusBadge";

type Recipient = {
  id: string;
  name: string;
  role: "Delivery" | "Finance" | "Legal" | "Leadership" | "Account owner";
  email: string;
  redactSalary: boolean;
  delivery: "sent" | "acknowledged" | "failed";
  ts: string;
};

type ChecklistItem = {
  id: string;
  label: string;
  owner: string;
  due: string;
  evidence: string | null;
  done: boolean;
};

type Acknowledgement = {
  actor: string;
  role: "Account owner" | "Delivery";
  ts: string | null;
};

export interface HandoffDetailProps {
  handoffId: string;
}

const SAMPLE_RECIPIENTS: Recipient[] = [
  {
    id: "r-1",
    name: "Delivery lead",
    role: "Delivery",
    email: "delivery-lead@smartek21.com",
    redactSalary: true,
    delivery: "acknowledged",
    ts: "2026-09-18T15:04:00Z",
  },
  {
    id: "r-2",
    name: "Account owner",
    role: "Account owner",
    email: "owner@smartek21.com",
    redactSalary: true,
    delivery: "acknowledged",
    ts: "2026-09-18T15:07:00Z",
  },
  {
    id: "r-3",
    name: "Finance ops",
    role: "Finance",
    email: "finance-ops@smartek21.com",
    redactSalary: false,
    delivery: "sent",
    ts: "2026-09-18T15:04:00Z",
  },
  {
    id: "r-4",
    name: "Legal counsel",
    role: "Legal",
    email: "legal@smartek21.com",
    redactSalary: true,
    delivery: "sent",
    ts: "2026-09-18T15:04:00Z",
  },
  {
    id: "r-5",
    name: "Practice head",
    role: "Leadership",
    email: "practice-head@smartek21.com",
    redactSalary: true,
    delivery: "failed",
    ts: "2026-09-18T15:05:00Z",
  },
];

const SAMPLE_CHECKLIST: ChecklistItem[] = [
  {
    id: "kickoff",
    label: "Kickoff scheduled with client",
    owner: "Delivery lead",
    due: "2026-09-25",
    evidence: null,
    done: false,
  },
  {
    id: "billing",
    label: "Billing / PO setup",
    owner: "Finance ops",
    due: "2026-09-22",
    evidence: null,
    done: false,
  },
  {
    id: "staffing",
    label: "Staffing requisitions raised",
    owner: "HR ops",
    due: "2026-09-24",
    evidence: null,
    done: false,
  },
  {
    id: "renewal",
    label: "Renewal record created",
    owner: "Account owner",
    due: "2026-09-20",
    evidence: null,
    done: false,
  },
];

function deliveryTone(
  d: Recipient["delivery"],
): "ok" | "warn" | "danger" | "neutral" {
  if (d === "acknowledged") return "ok";
  if (d === "sent") return "warn";
  if (d === "failed") return "danger";
  return "neutral";
}

export function HandoffDetail({ handoffId }: HandoffDetailProps) {
  const [recipients, setRecipients] = useState<Recipient[]>(SAMPLE_RECIPIENTS);
  const [checklist, setChecklist] = useState<ChecklistItem[]>(SAMPLE_CHECKLIST);
  const [retried, setRetried] = useState<Set<string>>(new Set());

  const acknowledgements: Acknowledgement[] = useMemo(
    () => [
      {
        actor: "Account owner",
        role: "Account owner",
        ts: recipients.find((r) => r.role === "Account owner")?.ts ?? null,
      },
      {
        actor: "Delivery lead",
        role: "Delivery",
        ts:
          recipients.find(
            (r) => r.role === "Delivery" && r.delivery === "acknowledged",
          )?.ts ?? null,
      },
    ],
    [recipients],
  );

  function toggleCheck(id: string) {
    setChecklist((items) =>
      items.map((it) => (it.id === id ? { ...it, done: !it.done } : it)),
    );
  }

  function retry(recipientId: string) {
    if (retried.has(recipientId)) return; // dedupe protection
    setRetried((s) => new Set(s).add(recipientId));
    setRecipients((items) =>
      items.map((r) =>
        r.id === recipientId
          ? { ...r, delivery: "sent", ts: new Date().toISOString() }
          : r,
      ),
    );
  }

  return (
    <div className="flex flex-col gap-6" data-testid="handoff-detail">
      <div
        className="rounded-panel border border-divider p-4"
        data-testid="handoff-release-evidence"
      >
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-section text-text">Release evidence</h2>
            <p className="text-secondary text-text-secondary">
              Handoff {handoffId} · exact executed SOW version. Verification
              (price · dates · scope similarity) must pass before distribution.
            </p>
          </div>
          <StatusBadge
            tone="ok"
            label="Verified"
            icon={CheckCircle2}
          />
        </div>
        <dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3 text-body">
          <div>
            <dt className="text-secondary text-text-secondary">SOW version</dt>
            <dd className="tnum text-text">v4 (executed 2026-09-18)</dd>
          </div>
          <div>
            <dt className="text-secondary text-text-secondary">Package hash</dt>
            <dd className="tnum text-text">sha256:6f1a…9c</dd>
          </div>
          <div>
            <dt className="text-secondary text-text-secondary">
              Locally-named "signed" file
            </dt>
            <dd className="text-text">
              <StatusBadge
                tone="warn"
                label="Not evidence"
                icon={ShieldAlert}
              />
            </dd>
          </div>
        </dl>
      </div>

      <section
        className="rounded-panel border border-divider p-4"
        data-testid="handoff-distribution"
      >
        <div className="flex items-center justify-between pb-3">
          <div>
            <h2 className="text-section text-text">Distribution</h2>
            <p className="text-secondary text-text-secondary">
              Delivery, Finance, Legal and leadership recipients. Salary
              detail is only visible to authorized Finance recipients.
            </p>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table
            className="w-full text-body"
            aria-label="Distribution recipients"
          >
            <thead>
              <tr className="text-left text-secondary text-text-secondary">
                <th className="px-2 py-2 font-medium">Recipient</th>
                <th className="px-2 py-2 font-medium">Role</th>
                <th className="px-2 py-2 font-medium">Salary visibility</th>
                <th className="px-2 py-2 font-medium">Delivery</th>
                <th className="px-2 py-2 font-medium">Timestamp</th>
                <th className="px-2 py-2 font-medium text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {recipients.map((r) => (
                <tr
                  key={r.id}
                  data-testid={`recipient-${r.id}`}
                  className="border-t border-divider"
                >
                  <td className="px-2 py-2 align-top text-text">
                    {r.name}
                    <div className="text-secondary text-text-secondary">
                      {r.email}
                    </div>
                  </td>
                  <td className="px-2 py-2 align-top text-text-secondary">
                    {r.role}
                  </td>
                  <td className="px-2 py-2 align-top">
                    <StatusBadge
                      tone={r.redactSalary ? "ok" : "warn"}
                      label={r.redactSalary ? "Redacted" : "Full"}
                    />
                  </td>
                  <td className="px-2 py-2 align-top">
                    <StatusBadge
                      tone={deliveryTone(r.delivery)}
                      label={
                        r.delivery === "acknowledged"
                          ? "Acknowledged"
                          : r.delivery === "sent"
                            ? "Sent"
                            : "Failed"
                      }
                    />
                  </td>
                  <td className="px-2 py-2 align-top tnum text-text-secondary">
                    {r.ts.replace("T", " ").slice(0, 16)}
                  </td>
                  <td className="px-2 py-2 align-top text-right">
                    {r.delivery === "failed" ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => retry(r.id)}
                        disabled={retried.has(r.id)}
                        aria-label={`Retry send to ${r.name}`}
                      >
                        <RefreshCw className="h-3 w-3" aria-hidden />
                        {retried.has(r.id) ? "Retry queued" : "Retry"}
                      </Button>
                    ) : (
                      <span className="text-text-secondary">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section
        className="rounded-panel border border-divider p-4"
        data-testid="handoff-acknowledgement"
      >
        <h2 className="text-section text-text">Acknowledgement</h2>
        <p className="text-secondary text-text-secondary">
          Delivery and the account owner both confirm receipt. Time-stamped
          from the recipient's inbox event.
        </p>
        <ul className="mt-3 flex flex-col gap-2 text-body">
          {acknowledgements.map((a) => (
            <li
              key={a.role}
              className="flex items-center justify-between rounded-control border border-divider px-3 py-2"
              data-testid={`ack-${a.role.toLowerCase().replace(/ /g, "-")}`}
            >
              <div>
                <div className="text-text">{a.actor}</div>
                <div className="text-secondary text-text-secondary">
                  {a.role}
                </div>
              </div>
              <StatusBadge
                tone={a.ts ? "ok" : "warn"}
                label={
                  a.ts
                    ? `Acknowledged ${a.ts.replace("T", " ").slice(0, 16)}`
                    : "Not yet acknowledged"
                }
              />
            </li>
          ))}
        </ul>
      </section>

      <section
        className="rounded-panel border border-divider p-4"
        data-testid="handoff-checklist"
      >
        <h2 className="text-section text-text">Setup checklist</h2>
        <p className="text-secondary text-text-secondary">
          Kickoff, billing / PO, staffing and renewal record. Each item has
          an owner and a due date; check the box once evidence lands.
        </p>
        <ul className="mt-3 flex flex-col gap-2 text-body">
          {checklist.map((it) => (
            <li
              key={it.id}
              className="flex items-start gap-3 rounded-control border border-divider px-3 py-2"
              data-testid={`checklist-${it.id}`}
            >
              <input
                type="checkbox"
                aria-label={`Mark ${it.label} complete`}
                checked={it.done}
                onChange={() => toggleCheck(it.id)}
                className="mt-1 h-4 w-4"
              />
              <div className="flex flex-1 flex-col">
                <div className="text-text">{it.label}</div>
                <div className="text-secondary text-text-secondary tnum">
                  Owner: {it.owner} · Due: {it.due}
                </div>
                {it.evidence ? (
                  <div className="text-secondary text-text-secondary">
                    Evidence: {it.evidence}
                  </div>
                ) : (
                  <div className="text-secondary text-text-secondary">
                    Evidence: not yet attached
                  </div>
                )}
              </div>
              <StatusBadge
                tone={it.done ? "ok" : "warn"}
                label={it.done ? "Done" : "Open"}
              />
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

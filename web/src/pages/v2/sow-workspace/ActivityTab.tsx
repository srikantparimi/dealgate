import { EmptyState } from "../../../ui-v2/EmptyState";
import type { WorkspaceSnapshot } from "./readiness";

export function ActivityTab({ snap }: { snap: WorkspaceSnapshot }) {
  const events = snap.deal?.audit ?? [];
  if (events.length === 0) {
    return (
      <EmptyState
        title="No activity recorded"
        description="Audit events land here as the SOW progresses — decisions, file uploads, sync events."
      />
    );
  }
  return (
    <section
      aria-label="Activity"
      className="rounded-panel border border-divider bg-surface p-4"
      style={{ maxWidth: "960px" }}
    >
      <h2 className="text-section text-text mb-3">Activity</h2>
      <ol className="space-y-3">
        {events.map((e) => (
          <li
            key={e.id}
            className="border-l-2 border-divider pl-3 text-body text-text"
          >
            <p className="text-text">{e.action}</p>
            <p className="text-secondary text-text-secondary">
              {e.ts} · Actor {e.actor_id ?? "system"}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}

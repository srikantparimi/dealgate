/**
 * S20 W6 Session 4 · WatchStar — toggles a per-user star on a deal or
 * a client. Fetches the initial state from `/watchlist` (via the parent
 * that already has it) and posts/deletes to `/watchlist` on click.
 */

import { useEffect, useState } from "react";
import { Star } from "lucide-react";
import {
  addWatch,
  removeWatch,
  listWatchlist,
  type UUID,
} from "../api/client";
import { cn } from "../lib/cn";

export function WatchStar({
  kind,
  itemId,
  onChange,
}: {
  kind: "opportunity" | "client";
  itemId: UUID;
  onChange?: (watching: boolean) => void;
}) {
  const [on, setOn] = useState<boolean>(false);
  const [busy, setBusy] = useState<boolean>(false);

  useEffect(() => {
    let cancelled = false;
    listWatchlist()
      .then((r) => {
        if (cancelled) return;
        const found = r.items.some((it) => it.kind === kind && it.item_id === itemId);
        setOn(found);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [kind, itemId]);

  async function toggle() {
    if (busy) return;
    setBusy(true);
    try {
      if (on) {
        await removeWatch(kind, itemId);
        setOn(false);
        onChange?.(false);
      } else {
        await addWatch(kind, itemId);
        setOn(true);
        onChange?.(true);
      }
    } catch {
      // Silent — the star is a soft signal; a 403/500 does not block work.
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={busy}
      aria-pressed={on}
      aria-label={on ? "Unstar" : "Star"}
      data-testid={`watch-star-${kind}-${itemId}`}
      className={cn(
        "inline-flex items-center justify-center rounded-panel border px-2 py-1 transition-motion",
        on
          ? "border-warn bg-warn-fill/30 text-warn"
          : "border-divider bg-surface text-text-secondary hover:text-text",
      )}
    >
      <Star
        className={cn("h-4 w-4", on ? "fill-current" : "")}
        aria-hidden
      />
    </button>
  );
}

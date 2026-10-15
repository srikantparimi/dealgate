// S23-PL2 F13 · the bulk selection bar (spec §7.6): watch the selected deals,
// add them to a tracking group (the page opens its group dialog), or clear.
import { useState } from "react";

import { Button } from "../../../ui-v2/primitives/button";
import { Glyph } from "./tags";

export interface BulkBarProps {
  count: number;
  onWatchSelected: () => Promise<void>;
  onAddToGroup: () => void;
  onClear: () => void;
}

export function BulkBar({ count, onWatchSelected, onAddToGroup, onClear }: BulkBarProps) {
  const [watching, setWatching] = useState(false);
  const watchAll = async () => {
    setWatching(true);
    try {
      await onWatchSelected();
    } catch {
      // The page reports the outcome (toast); the bar only re-enables itself.
    } finally {
      setWatching(false);
    }
  };
  return (
    <div
      role="group"
      aria-label="Bulk actions"
      className="flex flex-wrap items-center gap-3 rounded-card border border-primary bg-primary-subtle px-4 py-3"
    >
      <strong className="text-body font-semibold text-text">{`${count} selected`}</strong>
      <Button variant="secondary" size="sm" onClick={() => void watchAll()} disabled={watching}>
        <Glyph before>☆</Glyph>
        Watch selected
      </Button>
      <Button variant="secondary" size="sm" onClick={onAddToGroup}>
        <Glyph before>＋</Glyph>
        Add to group
      </Button>
      <button
        type="button"
        onClick={onClear}
        className="rounded-control px-2 text-secondary text-text-secondary hover:text-text focus-visible:outline-focus"
      >
        Clear selection
      </button>
    </div>
  );
}

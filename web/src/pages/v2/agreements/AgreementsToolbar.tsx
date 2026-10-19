// S24-AG1 F1/F8/F9 · the filter toolbar: search (what it searches depends on
// the tab, and the placeholder says so), then, on the Clients tab only,
// relationship, agreement status, deal stage, business unit (always with its
// region) and sort. Every control changes the URL through the page's
// transitions (agreementsState.ts).
import { useEffect, useState } from "react";

import type { AgreementsSort, BusinessUnitName, RelationshipFilter, StageFilter, StatusFilter } from "../../../api/agreements";
import { Input } from "../../../ui-v2/primitives/input";
import {
  BU_OPTIONS,
  RELATIONSHIP_OPTIONS,
  SEARCH_MAX,
  SEARCH_PLACEHOLDER,
  SORT_OPTIONS,
  STAGE_OPTIONS,
  STATUS_OPTIONS,
  type AgreementsUrlState,
} from "./agreementsState";

export const SELECT_CLASS =
  "h-10 max-w-full rounded-control border border-input-border bg-surface px-3 text-body text-text focus-visible:outline-focus disabled:opacity-60";

const ANY_BU = "any";
const SEVERAL_BU = "several";

export interface AgreementsToolbarProps {
  state: AgreementsUrlState;
  onSearch: (q: string) => void;
  onRelationship: (value: RelationshipFilter) => void;
  onStatus: (value: StatusFilter) => void;
  onStage: (value: StageFilter) => void;
  onBusinessUnits: (value: BusinessUnitName[]) => void;
  onSort: (value: AgreementsSort) => void;
}

export function AgreementsToolbar({
  state,
  onSearch,
  onRelationship,
  onStatus,
  onStage,
  onBusinessUnits,
  onSort,
}: AgreementsToolbarProps) {
  // The URL keeps the trimmed search; the box keeps what is typed (a trailing
  // space between words) and follows the URL when it changes elsewhere.
  const [draft, setDraft] = useState(state.q);
  useEffect(() => {
    setDraft((current) => (current.trim() === state.q.trim() ? current : state.q));
  }, [state.q]);

  const placeholder = SEARCH_PLACEHOLDER[state.tab];
  const buValue = state.bu.length === 0 ? ANY_BU : state.bu.length === 1 ? state.bu[0] : SEVERAL_BU;

  return (
    <section
      aria-label="Filters"
      className="flex flex-wrap items-center gap-2 rounded-card border border-border bg-surface p-3"
    >
      <div className="relative min-w-full flex-1 sm:min-w-[240px]">
        <span aria-hidden className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-secondary">
          ⌕
        </span>
        <Input
          type="search"
          value={draft}
          maxLength={SEARCH_MAX}
          onChange={(event) => {
            setDraft(event.target.value);
            onSearch(event.target.value);
          }}
          placeholder={placeholder}
          aria-label={placeholder}
          className="pl-8"
        />
      </div>
      {state.tab === "clients" ? (
        <>
          <select
            aria-label="Relationship"
            value={state.relationship}
            onChange={(e) => onRelationship(e.target.value as RelationshipFilter)}
            className={SELECT_CLASS}
          >
            {RELATIONSHIP_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <select
            aria-label="Agreement status"
            value={state.status}
            onChange={(e) => onStatus(e.target.value as StatusFilter)}
            className={SELECT_CLASS}
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <select
            aria-label="Deal stage"
            value={state.stage}
            onChange={(e) => onStage(e.target.value as StageFilter)}
            className={SELECT_CLASS}
          >
            {STAGE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <select
            aria-label="Business unit"
            value={buValue}
            onChange={(e) => {
              const value = e.target.value;
              if (value === SEVERAL_BU) return;
              onBusinessUnits(value === ANY_BU ? [] : [value as BusinessUnitName]);
            }}
            className={SELECT_CLASS}
          >
            <option value={ANY_BU}>All business units</option>
            {BU_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
            {buValue === SEVERAL_BU ? (
              <option value={SEVERAL_BU} disabled>
                {`${state.bu.length} business units`}
              </option>
            ) : null}
          </select>
          <select
            aria-label="Sort"
            value={state.sort}
            onChange={(e) => onSort(e.target.value as AgreementsSort)}
            className={SELECT_CLASS}
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </>
      ) : null}
    </section>
  );
}

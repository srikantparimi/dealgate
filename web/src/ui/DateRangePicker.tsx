import { type ChangeEvent } from "react";

/**
 * Native `<input type="date">` pair for a since/until filter. Values are the
 * raw YYYY-MM-DD strings the user typed; callers translate to ISO-8601
 * before sending to the API. Empty string means "not set".
 */
export function DateRangePicker({
  since,
  until,
  onChange,
  labelSince = "Since",
  labelUntil = "Until",
}: {
  since: string;
  until: string;
  onChange: (next: { since: string; until: string }) => void;
  labelSince?: string;
  labelUntil?: string;
}) {
  const setSince = (e: ChangeEvent<HTMLInputElement>) =>
    onChange({ since: e.target.value, until });
  const setUntil = (e: ChangeEvent<HTMLInputElement>) =>
    onChange({ since, until: e.target.value });

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
      <label style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 12, color: "#6b7280" }}>
        {labelSince}
        <input
          type="date"
          aria-label={labelSince}
          value={since}
          onChange={setSince}
        />
      </label>
      <label style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 12, color: "#6b7280" }}>
        {labelUntil}
        <input
          type="date"
          aria-label={labelUntil}
          value={until}
          onChange={setUntil}
        />
      </label>
    </span>
  );
}

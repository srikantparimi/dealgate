/**
 * Small shared building blocks for the role dashboards.
 *
 * Zero business math (blueprint §2). Every number rendered here was
 * pre-computed server-side; these components format Decimal strings for
 * display without doing arithmetic.
 */

import type { ReactNode } from "react";

export function DashboardCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <section
      style={{
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        padding: 16,
        marginBottom: 16,
        background: "white",
      }}
    >
      <h2 style={{ margin: 0, marginBottom: 4, fontSize: 16, color: "#111827" }}>
        {title}
      </h2>
      {subtitle ? (
        <div style={{ color: "#6b7280", fontSize: 13, marginBottom: 12 }}>
          {subtitle}
        </div>
      ) : (
        <div style={{ marginBottom: 12 }} />
      )}
      {children}
    </section>
  );
}

export function StatValue({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
}) {
  return (
    <div style={{ display: "inline-block", marginRight: 24, marginBottom: 8 }}>
      <div style={{ color: "#6b7280", fontSize: 12 }}>{label}</div>
      <div style={{ color: "#111827", fontSize: 22, fontWeight: 600 }}>
        {value ?? "—"}
      </div>
      {hint ? (
        <div style={{ color: "#6b7280", fontSize: 12 }}>{hint}</div>
      ) : null}
    </div>
  );
}

/**
 * Render a Decimal string as a percentage — display formatting only, no
 * math on the value. The server sends "0.4523809…" and we surface the
 * first 4 significant digits as "45.24%".
 */
export function pct(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  // Split on the decimal point and pick two digits of the fractional part
  // as a percentage. This is display-only; server did the math.
  const trimmed = value.trim();
  if (!trimmed) return "—";
  const [ipart, fpart = ""] = trimmed.split(".");
  const padded = (fpart + "0000").slice(0, 4);
  const whole = ipart === "0" || ipart === "" ? padded.slice(0, 2) : `${Number(ipart) * 100}`;
  const dec = ipart === "0" || ipart === "" ? padded.slice(2, 4) : "00";
  return `${whole}.${dec}%`;
}

/** Format a decimal string as USD without introducing precision errors. */
export function money(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const t = value.trim();
  if (!t) return "—";
  // Split on decimal, group the integer half by 3, keep the fractional
  // half verbatim so we don't round anything.
  const negative = t.startsWith("-");
  const s = negative ? t.slice(1) : t;
  const [ipart, fpart] = s.split(".");
  const grouped = ipart.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const rendered = fpart !== undefined ? `${grouped}.${fpart}` : grouped;
  return `${negative ? "-" : ""}$${rendered}`;
}

import type { ReactNode } from "react";

type Tone = "ok" | "warn" | "block" | "neutral";

const TONES: Record<Tone, { bg: string; fg: string }> = {
  ok: { bg: "#d1fae5", fg: "#065f46" },
  warn: { bg: "#fef3c7", fg: "#92400e" },
  block: { bg: "#fee2e2", fg: "#991b1b" },
  neutral: { bg: "#e5e7eb", fg: "#374151" },
};

export function StatusChip({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  const { bg, fg } = TONES[tone];
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 10px",
        borderRadius: 999,
        fontSize: 12,
        fontWeight: 600,
        background: bg,
        color: fg,
      }}
    >
      {children}
    </span>
  );
}

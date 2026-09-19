/**
 * Renewal reminder maths — spec §16.
 *
 * These helpers stay pure (no I/O) so the calling components can be
 * tested in isolation. All date maths uses UTC calendar months in the
 * contract's business timezone; the caller is responsible for aligning
 * to the contract's tz — we accept ISO-YYYY-MM-DD strings only.
 *
 * Rules (spec §16, R23/R24):
 *  - First standard alert = expiry − 2 calendar months. Clamp month-end.
 *  - Repeat every seven days while unresolved.
 *  - If contractual notice needs earlier action, surface it separately.
 *  - Two-week assessment does not wait for a 2-month lead window.
 */

const MS_PER_DAY = 86_400_000;

function parseIsoDate(s: string): Date {
  const [y, m, d] = s.split("-").map((n) => Number.parseInt(n, 10));
  return new Date(Date.UTC(y, m - 1, d));
}

function toIsoDate(d: Date): string {
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function daysInMonth(year: number, monthIdx: number): number {
  return new Date(Date.UTC(year, monthIdx + 1, 0)).getUTCDate();
}

/**
 * Shift `date` by `months` calendar months, clamping to the last valid
 * day of the target month (so 31 May − 2 months → 31 March, but
 * 31 Oct − 2 months → 31 Aug; 31 Mar − 1 month → 28/29 Feb).
 */
export function shiftMonths(iso: string, months: number): string {
  const d = parseIsoDate(iso);
  const targetMonthIdx = d.getUTCMonth() + months;
  const targetYear = d.getUTCFullYear() + Math.floor(targetMonthIdx / 12);
  const normalisedMonthIdx = ((targetMonthIdx % 12) + 12) % 12;
  const day = Math.min(
    d.getUTCDate(),
    daysInMonth(targetYear, normalisedMonthIdx),
  );
  return toIsoDate(new Date(Date.UTC(targetYear, normalisedMonthIdx, day)));
}

export function daysBetween(fromIso: string, toIso: string): number {
  const from = parseIsoDate(fromIso).getTime();
  const to = parseIsoDate(toIso).getTime();
  return Math.round((to - from) / MS_PER_DAY);
}

export interface ReminderPlan {
  firstAlertDate: string;
  weeklyOccurrences: string[];
  noticeAlertDate: string | null;
  shortEngagementImmediate: boolean;
}

export interface ComputeReminderInput {
  today: string;
  expiryDate: string;
  contractStart?: string | null;
  contractualNoticeDate?: string | null;
  maxOccurrences?: number;
}

export function computeReminderPlan(
  input: ComputeReminderInput,
): ReminderPlan {
  const {
    today,
    expiryDate,
    contractStart,
    contractualNoticeDate,
    maxOccurrences = 12,
  } = input;

  const firstAlertDate = shiftMonths(expiryDate, -2);

  const shortEngagementImmediate =
    !!contractStart && daysBetween(contractStart, expiryDate) <= 30;

  const startDate =
    daysBetween(today, firstAlertDate) < 0 ? today : firstAlertDate;

  const weeklyOccurrences: string[] = [];
  let cursor = startDate;
  const expiryDays = daysBetween(cursor, expiryDate);
  for (let i = 0; i < maxOccurrences && daysBetween(cursor, expiryDate) >= 0; i++) {
    weeklyOccurrences.push(cursor);
    // step by 7 days
    const d = parseIsoDate(cursor);
    d.setUTCDate(d.getUTCDate() + 7);
    cursor = toIsoDate(d);
  }
  void expiryDays; // linter: kept for readability

  const noticeAlertDate =
    contractualNoticeDate &&
    daysBetween(contractualNoticeDate, firstAlertDate) > 0
      ? contractualNoticeDate
      : null;

  return {
    firstAlertDate,
    weeklyOccurrences,
    noticeAlertDate,
    shortEngagementImmediate,
  };
}

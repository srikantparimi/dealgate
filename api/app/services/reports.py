"""S20 reports service — approval turnaround + portfolio basis.

Owner: W4. Consumed by the /reports/* router. All aggregation happens
here so the router stays a thin permission gate.

Approval turnaround (L18, T42): time-in-status by approval stage. Every
package transition audits with a stable action name in
``app.services.approvals``:

* ``package.submitted``              → enters ``pending_delivery_hr``
* ``package.delivery_hr_passed``     → enters ``pending_finance_legal``
* ``package.escalated_to_ceo``       → enters ``pending_ceo_exception``
* ``package.ready_to_sign``          → enters ``ready_to_sign``
* ``package.released``               → enters ``released``
* ``package.rejected``               → terminal reject
* ``package.voided``                 → terminal void

We derive per-stage elapsed hours from consecutive audit rows on the
same ``approval_package`` entity id and roll up average / median /
sample size within the caller's window.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent


# The stage-transition audit actions the review calls out. Ordering is
# significant: it defines the "next stage" for a given "from stage" so
# we can name the interval on the way out.
STAGE_TRANSITIONS: tuple[tuple[str, str, str], ...] = (
    # (from_status, action_that_leaves_it, to_status)
    ("pending_delivery_hr", "package.delivery_hr_passed", "pending_finance_legal"),
    ("pending_delivery_hr", "package.rejected", "rejected"),
    ("pending_finance_legal", "package.escalated_to_ceo", "pending_ceo_exception"),
    ("pending_finance_legal", "package.ready_to_sign", "ready_to_sign"),
    ("pending_finance_legal", "package.rejected", "rejected"),
    ("pending_ceo_exception", "package.ready_to_sign", "ready_to_sign"),
    ("pending_ceo_exception", "package.rejected", "rejected"),
    ("ready_to_sign", "package.released", "released"),
)


# The action that puts a package into a given status. `package.submitted`
# is special: it is the entrance action for `pending_delivery_hr`.
ENTRY_ACTION_BY_STATUS: dict[str, str] = {
    "pending_delivery_hr": "package.submitted",
    "pending_finance_legal": "package.delivery_hr_passed",
    "pending_ceo_exception": "package.escalated_to_ceo",
    "ready_to_sign": "package.ready_to_sign",
    "released": "package.released",
}


@dataclass(frozen=True)
class StageTurnaround:
    """Per-stage turnaround statistics inside a window."""

    stage: str
    """The `from` status name (e.g. `pending_delivery_hr`)."""

    sample_size: int
    """How many package transitions contributed to this row."""

    avg_hours: float | None
    """Mean hours between the entry audit event and the exit audit
    event. ``None`` when ``sample_size == 0`` — the endpoint contract
    says an empty sample is `Unknown`, never zero (contracts.md §1)."""

    median_hours: float | None
    """Median hours across the sample. ``None`` when empty."""

    p90_hours: float | None
    """90th percentile hours across the sample. ``None`` when empty."""


@dataclass(frozen=True)
class TurnaroundReport:
    """Full response envelope for `/reports/approvals/turnaround`."""

    window: str
    """Echo of the caller's window token, e.g. ``"30d"``."""

    window_from: datetime
    window_to: datetime

    total_transitions: int
    """Sum of `sample_size` across every stage. Sanity check for callers."""

    per_stage: tuple[StageTurnaround, ...]

    overall_median_hours: float | None
    """Median across every stage-transition interval in the window.
    ``None`` when no transitions matched."""

    generated_at: datetime


def _parse_window(window: str) -> timedelta:
    """Parse `"30d"`, `"7d"`, `"90d"`, `"1h"`. Anything else → ValueError."""

    if not window or len(window) < 2:
        raise ValueError("window must look like '30d' / '7d' / '24h'")
    unit = window[-1].lower()
    try:
        n = int(window[:-1])
    except ValueError as exc:
        raise ValueError(f"window magnitude must be an integer, got {window!r}") from exc
    if n <= 0:
        raise ValueError("window magnitude must be positive")
    if unit == "d":
        return timedelta(days=n)
    if unit == "h":
        return timedelta(hours=n)
    if unit == "w":
        return timedelta(weeks=n)
    raise ValueError(f"window unit must be h|d|w, got {unit!r}")


def _percentile(values: list[float], pct: float) -> float | None:
    """Return the ``pct`` percentile (0..100). Linear interpolation.

    Python 3.8+ ships `statistics.quantiles`; we implement the tiny
    variant here so tests don't have to think about method="exclusive"
    vs "inclusive". Empty input → ``None`` (contracts.md §1 — no zero
    stand-in for unknown).
    """

    if not values:
        return None
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    if pct <= 0:
        return ordered[0]
    if pct >= 100:
        return ordered[-1]
    # Position on 0..n-1.
    pos = (pct / 100.0) * (len(ordered) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


async def compute_approval_turnaround(
    session: AsyncSession,
    *,
    window: str = "30d",
    now: datetime | None = None,
) -> TurnaroundReport:
    """Aggregate approval turnaround across ``window`` (default 30 days).

    Reads the audit log for every package-lifecycle action, walks each
    package's timeline in order, and emits one interval per observed
    (from_status → to_status) transition. Intervals that started before
    the window are excluded; intervals whose exit falls inside the
    window count.

    No math on the display side (CLAUDE.md rule 2) — average / median /
    p90 come out of this function, the router marshals, the browser
    only renders.
    """

    delta = _parse_window(window)
    ref = (now or datetime.now(tz=UTC)).astimezone(UTC)
    window_from = ref - delta

    # Pull every package.* audit event ordered by entity + timestamp so
    # we can walk each package in order. Bounded by "any event whose ts
    # falls inside the window OR whose entity_id has an event inside the
    # window" — for correctness we need the event *preceding* the exit
    # even if it is older. So: pull everything, filter after.
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.entity == "approval_package")
        .where(
            and_(
                AuditEvent.action.in_(
                    (
                        "package.submitted",
                        "package.delivery_hr_passed",
                        "package.escalated_to_ceo",
                        "package.ready_to_sign",
                        "package.released",
                        "package.rejected",
                        "package.reverted_to_draft",
                    )
                )
            )
        )
        .order_by(AuditEvent.entity_id.asc(), AuditEvent.ts.asc())
    )
    rows = list((await session.execute(stmt)).scalars().all())

    # Group by entity_id (== package id).
    by_pkg: dict[str, list[AuditEvent]] = {}
    for r in rows:
        by_pkg.setdefault(r.entity_id, []).append(r)

    # For each package, walk consecutive audit events. A (prev, curr)
    # pair implies "the package was in the prev-status for this many
    # hours, and just left it via curr.action". We aggregate the
    # (from_status → curr.action) intervals into stage buckets.
    #
    # from_status = the status the package HAD just before curr fired.
    # That's the ``after.status`` of the previous event when present;
    # else the ``before.status`` of the current event.
    per_stage_intervals: dict[str, list[float]] = {}

    def _status_before(event: AuditEvent) -> str | None:
        if event.before and isinstance(event.before, dict):
            return event.before.get("status")
        return None

    def _status_after(event: AuditEvent) -> str | None:
        if event.after and isinstance(event.after, dict):
            return event.after.get("status")
        return None

    for pkg_id, events in by_pkg.items():
        for i in range(1, len(events)):
            prev = events[i - 1]
            curr = events[i]
            # Only count the exit if the exit itself lies inside the window.
            curr_ts = curr.ts
            if curr_ts.tzinfo is None:
                curr_ts = curr_ts.replace(tzinfo=UTC)
            if curr_ts < window_from or curr_ts > ref:
                continue
            prev_ts = prev.ts
            if prev_ts.tzinfo is None:
                prev_ts = prev_ts.replace(tzinfo=UTC)
            # from_status prefers current.before.status (definitive per
            # audit contract) and falls back to prev.after.status when
            # before is not populated.
            from_status = _status_before(curr) or _status_after(prev)
            if from_status is None:
                continue
            hours = (curr_ts - prev_ts).total_seconds() / 3600.0
            if hours < 0:  # shouldn't happen; guard anyway
                continue
            per_stage_intervals.setdefault(from_status, []).append(hours)

    per_stage: list[StageTurnaround] = []
    # Preserve a stable stage order for the UI.
    STAGE_ORDER = (
        "pending_delivery_hr",
        "pending_finance_legal",
        "pending_ceo_exception",
        "ready_to_sign",
    )
    all_intervals: list[float] = []
    for stage in STAGE_ORDER:
        values = per_stage_intervals.get(stage, [])
        all_intervals.extend(values)
        per_stage.append(
            StageTurnaround(
                stage=stage,
                sample_size=len(values),
                avg_hours=_mean(values),
                median_hours=_percentile(values, 50.0),
                p90_hours=_percentile(values, 90.0),
            )
        )

    return TurnaroundReport(
        window=window,
        window_from=window_from,
        window_to=ref,
        total_transitions=sum(s.sample_size for s in per_stage),
        per_stage=tuple(per_stage),
        overall_median_hours=_percentile(all_intervals, 50.0),
        generated_at=ref,
    )


__all__ = [
    "ENTRY_ACTION_BY_STATUS",
    "STAGE_TRANSITIONS",
    "StageTurnaround",
    "TurnaroundReport",
    "compute_approval_turnaround",
]

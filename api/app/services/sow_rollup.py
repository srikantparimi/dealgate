"""SOW rollup — one headline + a breakdown per deal (D1).

`contracts.md` D1: many SOWs per deal (once the migration relaxes
``sow.opportunity_id`` uniqueness — see
`docs/reports/s20/requests.md#W3-2026-09-30-01`). Each SOW package has
its own versions, gate, value and approval history. The **deal rollup**
counts by package state and picks a single headline label — the
*most-blocked open package* by this order:

    changes requested > CEO exception > in review >
    awaiting signature > approved > draft

Archived/superseded packages are excluded from the headline and counted
separately as ``archived``. A released SOW never hides a pending one:
the rule above escalates any open package above ``approved``.

Package status → rollup bucket mapping:

    pending_delivery_hr, pending_finance_legal   → in_review
    pending_ceo_exception                        → ceo_exception
    rejected                                     → changes_requested
    ready_to_sign                                → awaiting_signature
    released                                     → approved
    voided                                       → archived
    (no package submitted, sow_version exists)   → draft

The service is written to work today (one SOW per deal, single-row
answer) *and* after the D1 uniqueness relax (many rows per deal,
aggregated answer). The migration is not required for the service to
ship.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import ApprovalPackage
from app.models.sow import Sow, SowVersion

__all__ = [
    "RollupBreakdown",
    "RollupHeadline",
    "compute_headline",
]


# The buckets are ordered from most-blocked-open to least. `archived`
# is separate — it is never the headline.
_HEADLINE_ORDER: tuple[str, ...] = (
    "changes_requested",
    "ceo_exception",
    "in_review",
    "awaiting_signature",
    "approved",
    "draft",
)

# Package status → rollup bucket. Anything not in this map is silently
# ignored so a future package_status extension doesn't crash the rollup.
_STATUS_TO_BUCKET: dict[str, str] = {
    "pending_delivery_hr": "in_review",
    "pending_finance_legal": "in_review",
    "pending_ceo_exception": "ceo_exception",
    "rejected": "changes_requested",
    "ready_to_sign": "awaiting_signature",
    "released": "approved",
    "voided": "archived",
}


@dataclass(frozen=True)
class RollupBreakdown:
    """Counts by bucket. Every bucket appears — zero is a real answer.

    ``archived`` is the count of superseded/voided packages, plus any
    ``Sow`` row marked ``archived_at`` (D6 — a SOW archived by an
    authorised delete goes to `archived`).
    """

    draft: int = 0
    in_review: int = 0
    ceo_exception: int = 0
    changes_requested: int = 0
    awaiting_signature: int = 0
    approved: int = 0
    archived: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "draft": self.draft,
            "in_review": self.in_review,
            "ceo_exception": self.ceo_exception,
            "changes_requested": self.changes_requested,
            "awaiting_signature": self.awaiting_signature,
            "approved": self.approved,
            "archived": self.archived,
        }


@dataclass(frozen=True)
class RollupHeadline:
    """Rollup output. `headline` is the single label the deal card
    displays; `breakdown` is what the deal detail page renders as a
    list; `archived_count` is the "archived n" separately shown per D1.
    """

    headline: str
    breakdown: RollupBreakdown
    archived_count: int


async def compute_headline(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> RollupHeadline:
    """Compute the rollup for one deal.

    Today: at most one ``Sow`` per deal, so at most one package chain.
    After the D1 migration: many ``Sow`` per deal, and the query
    aggregates every non-archived SOW's newest package (superseded
    packages inside one SOW never win the headline against a newer one
    on the same SOW).

    The service does not know the archived state of individual packages
    beyond ``voided`` — a SOW whose row is marked ``archived_at`` counts
    as archived even if its packages are not. That matches D6: a SOW
    the owner explicitly archived should never re-appear as a live
    headline.
    """

    # Every non-archived Sow row for the deal. `archived_at IS NULL` is
    # the live set; archived rows are counted separately.
    sows = list(
        (
            await session.execute(
                select(Sow.id, Sow.archived_at).where(
                    Sow.opportunity_id == opportunity_id
                )
            )
        ).all()
    )
    live_sow_ids = [sid for (sid, arch) in sows if arch is None]
    archived_sows = sum(1 for (_sid, arch) in sows if arch is not None)

    # If there are no live SOWs at all, the deal has no headline — the
    # deal card renders "No SOW" and the archived count if any.
    if not live_sow_ids:
        return RollupHeadline(
            headline="no_sow",
            breakdown=RollupBreakdown(archived=archived_sows),
            archived_count=archived_sows,
        )

    # For each live SOW, find its newest non-voided package. Voided
    # packages count as archived, not as the SOW's live state — a SOW
    # whose only package is voided is a `draft` (there is no live gate
    # in flight).
    packages_by_sow: dict[uuid.UUID, list[ApprovalPackage]] = {}
    if live_sow_ids:
        rows = list(
            (
                await session.execute(
                    select(ApprovalPackage)
                    .join(SowVersion, SowVersion.id == ApprovalPackage.sow_version_id)
                    .where(SowVersion.sow_id.in_(live_sow_ids))
                    .order_by(
                        ApprovalPackage.submitted_at.desc(),
                        ApprovalPackage.id.desc(),
                    )
                )
            ).scalars()
        )
        for pkg in rows:
            # Look up SOW id for the package via the loaded SowVersion.
            # We already know it's in live_sow_ids via the join.
            # A single re-fetch is cheaper than eager loading here.
            sow_id = (
                await session.execute(
                    select(SowVersion.sow_id).where(SowVersion.id == pkg.sow_version_id)
                )
            ).scalar_one()
            packages_by_sow.setdefault(sow_id, []).append(pkg)

    counts = RollupBreakdown().as_dict()
    counts["archived"] = archived_sows
    # For each live SOW, pick its "current" bucket. Rules:
    #   - If it has at least one voided package but no live package,
    #     the SOW itself is still a `draft` (someone can resubmit).
    #   - If a package is `released`, later state on the same SOW
    #     supersedes only via a *new* package with different status;
    #     the newest one wins for that SOW.
    #   - No package at all → draft.
    for sow_id in live_sow_ids:
        pkgs = packages_by_sow.get(sow_id, [])
        live = [p for p in pkgs if p.status != "voided"]
        if not live:
            counts["draft"] += 1
            counts["archived"] += sum(1 for p in pkgs if p.status == "voided")
            continue
        newest = live[0]
        bucket = _STATUS_TO_BUCKET.get(newest.status, "draft")
        if bucket == "archived":
            counts["archived"] += 1
        else:
            counts[bucket] = counts.get(bucket, 0) + 1
        # Older voided packages on the same SOW still count in archived.
        counts["archived"] += sum(
            1 for p in pkgs[1:] if p.status == "voided"
        )

    # Headline: first non-zero bucket in order. Archived is never the
    # headline. If every live SOW is `approved`, `approved` wins — but
    # ONLY if no other open package would otherwise escalate.
    headline = "draft"
    for candidate in _HEADLINE_ORDER:
        if counts.get(candidate, 0) > 0:
            headline = candidate
            break

    breakdown = RollupBreakdown(
        draft=counts["draft"],
        in_review=counts["in_review"],
        ceo_exception=counts["ceo_exception"],
        changes_requested=counts["changes_requested"],
        awaiting_signature=counts["awaiting_signature"],
        approved=counts["approved"],
        archived=counts["archived"],
    )
    return RollupHeadline(
        headline=headline,
        breakdown=breakdown,
        archived_count=counts["archived"],
    )


def serialize(headline: RollupHeadline) -> dict[str, Any]:
    """Compact JSON envelope for router / snapshot consumers.

    The shape is stable; the deal detail page and Pipeline both consume
    this — a shape change here is a breaking change and needs a
    requests.md entry.
    """

    return {
        "headline": headline.headline,
        "breakdown": headline.breakdown.as_dict(),
        "archived_count": headline.archived_count,
    }

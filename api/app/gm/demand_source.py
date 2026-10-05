"""Cost-free, source-bound staffing projection for demand publication."""

import hashlib
import json
from datetime import date

from app.gm.commercial import PRICING_PROFILES, HybridPricing, PricingComponent


def line_key(component_id: str, assignment_id: str) -> str:
    """Composite identity intentionally excludes mutable source version IDs."""
    if any(not isinstance(value, str) or not value.strip() for value in (component_id, assignment_id)):
        raise ValueError("component and assignment identity are required")
    identity = json.dumps([component_id, assignment_id], ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _strings(value: object, field: str) -> list[str]:
    if not isinstance(value, (list, tuple)) or any(
        not isinstance(item, str) or not item.strip() or item != item.strip() for item in value
    ):
        raise ValueError(f"enrichment {field} must contain explicit nonblank strings")
    return list(value)


def project_staffing(
    component: PricingComponent, enrichments: dict[str, dict] | None = None,
) -> dict:
    """Project canonical staffing without financial completeness or probability.

    delivery_model is the explicit commercial profile key, not an inferred
    engagement classification. Enrichment cannot replace source-owned fields.
    """
    if enrichments is None:
        enrichments = {}
    if not isinstance(enrichments, dict):
        raise ValueError("enrichments must be keyed by stable line identity")
    lines: list[dict] = []
    missing: list[str] = []
    components: set[str] = set()
    used: set[str] = set()

    def visit(source: PricingComponent, parent: PricingComponent | None = None) -> None:
        if source.component_id in components:
            raise ValueError("duplicate component identity in staffing source")
        components.add(source.component_id)
        profile = PRICING_PROFILES.get(source.profile)
        if profile is None or profile.version != source.profile_version:
            raise ValueError("unsupported component profile/version")
        if (source.profile == "hybrid") != isinstance(source.pricing, HybridPricing):
            raise ValueError("hybrid component requires typed hybrid structure")
        children = source.pricing.components if isinstance(source.pricing, HybridPricing) else ()
        if source.profile == "hybrid" and not children:
            missing.append(f"component:{source.component_id}:components")
        if not source.staffing and not children:
            missing.append(f"component:{source.component_id}:staffing")
        for bound in (source.service_start, source.service_end):
            if bound is not None and type(bound) is not date:
                raise ValueError("invalid component service period")
        if source.service_start and source.service_end and source.service_start > source.service_end:
            raise ValueError("invalid component service period")
        if parent is not None:
            if any(getattr(source, field) != getattr(parent, field) for field in (
                "source_id", "source_version", "policy_version",
            )):
                raise ValueError("hybrid child source/policy binding mismatch")
            if ((source.service_start and parent.service_start and source.service_start < parent.service_start)
                    or (source.service_end and parent.service_end and source.service_end > parent.service_end)):
                raise ValueError("hybrid child service period binding mismatch")
        for field in ("service_start", "service_end"):
            if getattr(source, field) is None:
                missing.append(f"component:{source.component_id}:{field}")
        source_evidence = [item for item in source.source_evidence if isinstance(item, str) and item.strip()]
        evidence_missing = not source_evidence or len(source_evidence) != len(source.source_evidence)
        if evidence_missing:
            missing.append(f"component:{source.component_id}:source_evidence")
        assignments: set[str] = set()
        for assignment in source.staffing:
            if assignment.assignment_id in assignments:
                raise ValueError("duplicate assignment identity in component")
            assignments.add(assignment.assignment_id)
            if any(getattr(source, field) != getattr(assignment, field) for field in (
                "source_id", "source_version", "component_id", "profile_version", "policy_version", "currency", "timezone",
            )):
                raise ValueError("staffing assignment source binding mismatch")
            key = line_key(source.component_id, assignment.assignment_id)
            used.add(key)
            enrichment = enrichments.get(key, {})
            if not isinstance(enrichment, dict) or set(enrichment) - {
                "skills", "level", "retained_person_ids", "evidence",
            }:
                raise ValueError("unsupported staffing enrichment fields")
            skills = _strings(enrichment.get("skills", []), "skills")
            if len(set(skills)) != len(skills):
                raise ValueError("enrichment skills must be distinct")
            retained = _strings(enrichment.get("retained_person_ids", []), "retained_person_ids")
            if len(set(retained)) != len(retained) or len(retained) > assignment.quantity:
                raise ValueError("retained_person_ids must be distinct and within source quantity")
            level = enrichment.get("level", "")
            if not isinstance(level, str) or level != level.strip():
                raise ValueError("enrichment level must be an explicit string")
            evidence = _strings(enrichment.get("evidence", []), "evidence")
            if (skills or level or retained) and not evidence:
                raise ValueError("manual enrichment requires explicit evidence")
            start = assignment.start or source.service_start
            end = assignment.end or source.service_end
            if start and source.service_start:
                start = max(start, source.service_start)
            if end and source.service_end:
                end = min(end, source.service_end)
            gaps = ["source_evidence"] if evidence_missing else []
            if start and end and start > end:
                start = end = None
                gaps.append("service_period")
            row = {
                "line_key": key, "component_id": source.component_id,
                "assignment_id": assignment.assignment_id, "role": assignment.role,
                "skills": skills, "level": level, "location": assignment.location,
                "timezone": assignment.timezone, "quantity": assignment.quantity,
                "allocation": assignment.allocation, "start_date": start, "end_date": end,
                "delivery_model": source.profile, "retained_person_ids": retained,
                "evidence": list(dict.fromkeys((*source_evidence, *evidence))),
                "missing": gaps,
            }
            for field in ("role", "skills", "level", "location", "timezone", "start_date", "end_date"):
                if not row[field]:
                    gaps.append(field)
            if assignment.allocation <= 0:
                gaps.append("allocation")
            lines.append(row)
            missing.extend(f"line:{key}:{field}" for field in gaps)
        for child in children:
            visit(child, source)

    visit(component)
    if set(enrichments) - used:
        raise ValueError("enrichment references an unknown staffing line")
    return {"lines": lines, "missing": missing}

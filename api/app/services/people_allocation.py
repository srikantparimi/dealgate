"""Globally allocate managed capacity before authorized display filtering."""
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.encoders import jsonable_encoder

from app.gm.demand import VERSION, Capacity, Commitment, Demand, allocate_demand
from app.gm.demand_projection import scoped_intervals
from app.services.forecast_plans import _digest
from app.services.people_demand import DEMAND_READ, _source_rows
from app.services.people_planning import _scoped_supply
from app.services.people_coverage import allocation_coverage


async def demand_allocation(session, *, actor, account_id=None):
    population = await _source_rows(session, actor=actor, portfolio=False, named=True)
    supply = await _scoped_supply(session, actor=actor)
    organization = bool(set(actor.groups) & (DEMAND_READ - {"Sales", "SalesLeader"}))
    named = bool(set(actor.groups) & {"HR", "SystemAdmin"})
    visible = {item.get("source_id", item["plan_id"]) for item in population["items"]
        if (organization or item["owner_id"] == str(actor.id))
        and (account_id is None or item["account_id"] == str(account_id))}
    demands, capacities, commitments, metadata = [], [], [], {}
    missing, pending = [], []
    for source in population["items"]:
        source_id = source.get("source_id", source["plan_id"])
        if not source["selected"] or source["lifecycle"] in {"closed_lost", "dismissed", "expired"}:
            continue
        if source["missing"]:
            missing.append("global_demand_incomplete")
            if source_id in visible:
                missing.extend(f"{source_id}:{gap}" for gap in source["missing"])
        if source["state"] != "current":
            if source_id in visible:
                pending.append(source_id)
            continue
        for line in source["lines"]:
            if any(line[field] is None for field in ("quantity", "allocation", "start_date", "end_date")):
                missing.append("global_demand_incomplete")
                continue
            try:
                demand = Demand(id=line["demand_key"], account_id=source["account_id"], role=line["role"],
                    skills=tuple(line["skills"]), level=line["level"], location=line["location"], timezone=line["timezone"],
                    quantity=line["quantity"], allocation=Decimal(line["allocation"]),
                    start=date.fromisoformat(line["start_date"]), end=date.fromisoformat(line["end_date"]),
                    probability=Decimal(source["probability"]) if source["probability"] is not None else None,
                    lifecycle=source["lifecycle"], selected=source["selected"],
                    retained_person_ids=tuple(line["retained_person_ids"]))
            except (ValueError, ArithmeticError):
                missing.append("global_demand_incomplete")
                if source_id in visible:
                    missing.append(f"{source_id}:invalid_staffing_source")
                continue
            demands.append(demand)
            metadata[demand.id] = {"source_id": source_id, "source_kind": source.get("source_kind", "plan"),
                "project_id": source.get("project_id"), "plan_id": source["plan_id"], "title": source["title"],
                "account_name": source["account_name"], "source_url": source["source_url"],
                "role": line["role"], "skills": line["skills"], "level": line["level"],
                "location": line["location"], "timezone": line["timezone"]}
    for person in supply["people"]:
        if not person["skills"] or any(not person[field].strip() for field in ("role", "level", "location", "timezone")):
            missing.append("workforce_capability")
        for interval in person["intervals"]:
            bounds = dict(allocation=Decimal(interval["allocation"]), start=date.fromisoformat(interval["start_date"]),
                end=date.fromisoformat(interval["end_date"]))
            if interval["kind"] == "gross":
                capacities.append(Capacity(person_id=person["person_id"], role=person["role"], skills=tuple(person["skills"]),
                    level=person["level"], location=person["location"], timezone=person["timezone"], **bounds))
            else:
                commitments.append(Commitment(person_id=person["person_id"], source_id=interval["assignment_key"],
                    status=interval["kind"], **bounds))
    identities = {key for key, value in metadata.items() if value["source_id"] in visible}
    policy = "committed-start-stable-identity-proposal-v1"
    coverages, coverage_missing, coverage_versions = await allocation_coverage(session, actor=actor,
        sources=population["items"])
    missing.extend(coverage_missing)
    try:
        allocated = allocate_demand(tuple(demands), tuple(capacities), tuple(commitments), policy_version=policy,
            coverages=coverages)
        intervals, months = scoped_intervals(allocated["intervals"], identities)
    except (ArithmeticError, ValueError) as error:
        missing.append("allocation_precision" if isinstance(error, ArithmeticError) else "allocation_source_invalid")
        allocated = {"calculation_version": VERSION, "policy_version": policy, "excluded": []}
        intervals, months = [], []
    for interval in intervals:
        if not named:
            interval.pop("overcommitted_person_ids", None)
        for row in interval["demands"]:
            row.update(metadata[row["id"]])
            if not named:
                row.pop("matches", None)
                row["missing"] = ["continuity_unresolved" if value.startswith("continuity:") else value
                    for value in row["missing"]]
    if not supply["sources"]:
        missing.append("supply_source")
    observed = datetime.now(UTC)
    sources = [{**source, "age_seconds": max(0, int((observed - datetime.fromisoformat(source["source_as_of"])).total_seconds()))}
        for source in supply["sources"]]
    result = {"schema_version": "people-allocation-v1", "calculation_version": allocated["calculation_version"],
        "policy_version": allocated["policy_version"], "policy_status": "proposal", "is_reservation": False,
        "scope_label": ("Selected account demand" if account_id else "Company demand") if organization else "My portfolio",
        "intervals": intervals, "months": months,
        "pending_sources": pending, "missing": sorted(set(missing)), "complete": not pending and not missing,
        "sources": sources if named else [], "availability_basis": "managed_import",
        "freshness_status": "measured_not_live", "as_of": observed.isoformat(),
        "source_watermark": _digest({"demand": population["items"], "supply": supply["sources"], "coverage": coverage_versions}),
        "excluded": [row for row in allocated["excluded"] if row["id"] in identities]}
    return jsonable_encoder(result, custom_encoder={Decimal: str, date: lambda value: value.isoformat()})

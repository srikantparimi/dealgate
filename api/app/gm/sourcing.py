"""Cost-free sourcing proposals from globally allocated staffing intervals."""

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _text(value, name, *, blank=False):
    if not isinstance(value, str) or value != value.strip() or (not blank and not value):
        raise ValueError(f"{name} must be a normalized string")
    return value


def _integer(value, name, *, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _decimal(value, name):
    if not isinstance(value, (str, Decimal)):
        raise ValueError(f"{name} must be an exact Decimal string")
    if isinstance(value, str):
        _text(value, name)
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{name} must be a finite Decimal") from error
    if not result.is_finite() or result < 0:
        raise ValueError(f"{name} must be a finite nonnegative Decimal")
    return result


def _date(value, name):
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO date")
    try:
        result = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO date") from error
    if result.isoformat() != value:
        raise ValueError(f"{name} must be an ISO date")
    return result


def validate_rules(rules: list[dict]) -> list[dict]:
    if not isinstance(rules, list):
        raise ValueError("rules must be a list")
    result, identities = [], set()
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != {"skill", "location", "lead_days"}:
            raise ValueError("rule requires only skill, location and lead_days")
        skill, location = _text(rule["skill"], "skill"), _text(rule["location"], "location")
        days = _integer(rule["lead_days"], "lead_days")
        if (skill, location) in identities:
            raise ValueError("duplicate skill/location rule")
        identities.add((skill, location))
        result.append({"skill": skill, "location": location, "lead_days": days})
    return result


def _row(source, start, end, rules, *, sourcing_start=None):
    if not isinstance(source, dict):
        raise ValueError("demand must be an object")
    result = {field: _text(source.get(field), field) for field in ("id", "account_id")}
    kind = source.get("source_kind", "plan")
    if kind not in {"plan", "project"}:
        raise ValueError("Invalid demand source kind")
    identity = _text(source.get(f"{kind}_id"), f"{kind}_id")
    if source.get("source_id", identity) != identity:
        raise ValueError("Conflicting demand source identity")
    result.update(source_id=identity, source_kind=kind,
        plan_id=identity if kind == "plan" else None,
        project_id=identity if kind == "project" else None)
    missing = []
    for field in ("role", "level", "location", "timezone"):
        result[field] = _text(source.get(field), field, blank=True)
        if not result[field]:
            missing.append(field)
    if result["timezone"]:
        try:
            ZoneInfo(result["timezone"])
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("timezone must identify a known IANA zone") from error
    for field in ("title", "account_name", "source_url"):
        value = source.get(field)
        result[field] = None if value is None else _text(value, field, blank=True)
    skills = source.get("skills")
    if not isinstance(skills, list):
        raise ValueError("skills must be a list")
    result["skills"] = [_text(skill, "skill") for skill in skills]
    if len(set(skills)) != len(skills):
        raise ValueError("skills must be distinct")
    if not skills:
        missing.append("skills")
    quantity = _integer(source.get("quantity"), "quantity", minimum=1)
    retained = _integer(source.get("retained_quantity"), "retained_quantity")
    incremental = _integer(source.get("incremental_quantity"), "incremental_quantity")
    if retained + incremental != quantity:
        raise ValueError("retained and incremental quantities must equal full headcount")
    required_fte = Fraction(_decimal(source.get("required_fte"), "required_fte"))
    matched_fte = Fraction(_decimal(source.get("matched_fte"), "matched_fte"))
    gap_fte = _decimal(source.get("gap_fte"), "gap_fte")
    allocation = required_fte / quantity
    if not 0 < allocation <= 1 or required_fte != matched_fte + Fraction(gap_fte):
        raise ValueError("inconsistent allocation totals")
    matches = source.get("matches")
    if not isinstance(matches, list):
        raise ValueError("internal named matches are required for continuity classification")
    identities, continuity_matches, match_total = set(), 0, Fraction(0)
    for match in matches:
        if not isinstance(match, dict):
            raise ValueError("match must be an object")
        person = _text(match.get("person_id"), "person_id")
        if person in identities or type(match.get("continuity")) is not bool:
            raise ValueError("matches require distinct people and explicit continuity")
        identities.add(person)
        matched_allocation = Fraction(_decimal(match.get("allocation"), "matched allocation"))
        if matched_allocation != allocation:
            raise ValueError("matched allocation differs from a full staffing slot")
        match_total += matched_allocation
        continuity_matches += int(match["continuity"])
    incremental_matches = len(matches) - continuity_matches
    if match_total != matched_fte or continuity_matches > retained or incremental_matches > incremental:
        raise ValueError("match totals differ from staffing quantities")
    source_missing = source.get("missing")
    if not isinstance(source_missing, list):
        raise ValueError("missing must be a list")
    for reason in source_missing:
        reason = _text(reason, "missing reason")
        if reason.startswith("continuity:") or reason == "continuity_unresolved":
            missing.append("continuity_unresolved")
        elif reason in {"role", "skills", "level", "location", "timezone"}:
            missing.append(reason)
        else:
            raise ValueError("unknown allocation missing reason")
    continuity_gap = retained - continuity_matches
    incremental_gap = incremental - incremental_matches
    if continuity_gap:
        missing.append("continuity_unresolved")
    sourcing_by = None
    if incremental_gap:
        days = []
        for skill in skills:
            value = rules.get((skill, result["location"]), rules.get(("*", result["location"])))
            if value is None:
                missing.append("lead_time")
            else:
                days.append(value)
        if skills and len(days) == len(skills):
            try:
                sourcing_by = ((sourcing_start or start) - timedelta(days=max(days))).isoformat()
            except OverflowError as error:
                raise ValueError("sourcing date exceeds supported calendar bounds") from error
    result.update(quantity=quantity, retained_quantity=retained, incremental_quantity=incremental,
        matched_quantity=len(matches), gap_quantity=quantity - len(matches),
        continuity_gap_quantity=continuity_gap, incremental_gap_quantity=incremental_gap,
        gap_fte=gap_fte, start=start.isoformat(), end_exclusive=end.isoformat(),
        sourcing_by=sourcing_by, missing=list(dict.fromkeys(missing)))
    return result


def prepare_sourcing(intervals: list[dict], rules: list[dict]) -> dict:
    configured = {(rule["skill"], rule["location"]): rule["lead_days"] for rule in validate_rules(rules)}
    if not isinstance(intervals, list):
        raise ValueError("intervals must be a list")
    rows, missing, previous_end = [], [], None
    owners, ongoing_gaps = {}, {}
    for interval in intervals:
        if not isinstance(interval, dict) or not isinstance(interval.get("demands"), list):
            raise ValueError("interval must contain a demand list")
        start, end = _date(interval.get("start"), "start"), _date(interval.get("end_exclusive"), "end_exclusive")
        if start >= end or (previous_end is not None and start < previous_end):
            raise ValueError("intervals must be ordered, nonempty and nonoverlapping")
        if previous_end != start:
            ongoing_gaps = {}
        identities = set()
        matched_allocations, next_gaps = {}, {}
        for source in interval["demands"]:
            gap_start = ongoing_gaps.get(_text(source.get("id"), "id"), start) if isinstance(source, dict) else start
            row = _row(source, start, end, configured, sourcing_start=gap_start)
            if row["id"] in identities:
                raise ValueError("duplicate demand identity in interval")
            identities.add(row["id"])
            owner = (row["account_id"], row["source_kind"], row["source_id"])
            if owners.setdefault(row["id"], owner) != owner:
                raise ValueError("stable demand identity changed owning source")
            for match in source["matches"]:
                person = match["person_id"]
                matched_allocations[person] = matched_allocations.get(person, Fraction(0)) + Fraction(
                    _decimal(match["allocation"], "matched allocation"))
                if matched_allocations[person] > 1:
                    raise ValueError("one person cannot exceed full allocation in an interval")
            if row["incremental_gap_quantity"]:
                next_gaps[row["id"]] = gap_start
            rows.append(row)
            missing.extend(f"{row['id']}:{reason}" for reason in row["missing"])
        previous_end, ongoing_gaps = end, next_gaps
    return {"rows": rows, "missing": list(dict.fromkeys(missing)), "is_reservation": False}

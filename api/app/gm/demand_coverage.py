"""Explicit dated staffing-slot conversion, independent of financial coverage."""

from dataclasses import dataclass, replace
from datetime import date

from app.gm.demand import Demand


def _period(start, end):
    if type(start) is not date or type(end) is not date or start > end:
        raise ValueError("coverage requires valid inclusive dates")


@dataclass(frozen=True)
class DemandCoverage:
    plan_id: str
    project_id: str
    plan_slots: tuple[int, ...]
    project_slots: tuple[int, ...]
    start: date
    end: date

    def __post_init__(self):
        if any(not isinstance(value, str) or not value or value != value.strip()
               for value in (self.plan_id, self.project_id)):
            raise ValueError("coverage requires normalized demand identities")
        if self.plan_id == self.project_id:
            raise ValueError("coverage endpoints must be different demand identities")
        _period(self.start, self.end)
        for field in ("plan_slots", "project_slots"):
            slots = getattr(self, field)
            if not isinstance(slots, (tuple, list)) or not slots or any(type(slot) is not int or slot < 0 for slot in slots):
                raise ValueError("coverage slots must be nonempty nonnegative integers")
            if len(set(slots)) != len(slots):
                raise ValueError("coverage endpoint slots must be distinct")
            object.__setattr__(self, field, tuple(slots))
        if len(self.plan_slots) != len(self.project_slots):
            raise ValueError("coverage must pair equally many plan and project slots")


def validate_coverage(demands: tuple[Demand, ...], coverages: tuple[DemandCoverage, ...]) -> None:
    if not isinstance(demands, (tuple, list)) or not isinstance(coverages, (tuple, list)):
        raise ValueError("demands and coverages must be sequences")
    indexed = {}
    for demand in demands:
        if not isinstance(demand, Demand):
            raise ValueError("coverage requires canonical Demand inputs")
        demand.__post_init__()
        if demand.id in indexed:
            raise ValueError("duplicate demand identity")
        indexed[demand.id] = demand
    occupied: dict[tuple[str, int], list[tuple[date, date]]] = {}
    for coverage in coverages:
        if not isinstance(coverage, DemandCoverage):
            raise ValueError("coverage requires a DemandCoverage input")
        plan, project = indexed.get(coverage.plan_id), indexed.get(coverage.project_id)
        if plan is None or project is None:
            raise ValueError("unknown demand identity in coverage")
        if not plan.selected or plan.lifecycle not in {"needs_review", "tentative", "won_unsigned"}:
            raise ValueError("coverage plan must be active selected noncommitted demand")
        if not project.selected or project.lifecycle != "committed":
            raise ValueError("coverage replacement must be selected committed demand")
        for demand in (plan, project):
            if (not demand.skills or len(set(demand.skills)) != len(demand.skills)
                    or any(not skill or skill != skill.strip() for skill in demand.skills)
                    or any(not getattr(demand, field) or getattr(demand, field) != getattr(demand, field).strip()
                           for field in ("role", "level", "location", "timezone"))):
                raise ValueError("coverage requires complete canonical capability")
            if coverage.start < demand.start or coverage.end > demand.end:
                raise ValueError("coverage dates must be within both source terms")
        if (any(getattr(plan, field) != getattr(project, field) for field in (
                "account_id", "role", "level", "location", "timezone", "allocation"))
                or set(plan.skills) != set(project.skills)):
            raise ValueError("coverage requires matching account, capability and allocation")
        for plan_slot, project_slot in zip(coverage.plan_slots, coverage.project_slots):
            if plan_slot >= plan.quantity or project_slot >= project.quantity:
                raise ValueError("coverage slot is outside source quantity")
            if plan_slot < len(plan.retained_person_ids):
                if (project_slot >= len(project.retained_person_ids)
                        or plan.retained_person_ids[plan_slot] != project.retained_person_ids[project_slot]):
                    raise ValueError("coverage must preserve named continuity identity")
            for key in ((plan.id, plan_slot), (project.id, project_slot)):
                periods = occupied.setdefault(key, [])
                if any(coverage.start <= end and start <= coverage.end for start, end in periods):
                    raise ValueError("coverage endpoint slot overlap")
                periods.append((coverage.start, coverage.end))


def apply_coverage(
    demands: tuple[Demand, ...], coverages: tuple[DemandCoverage, ...], start: date, end: date,
) -> tuple[Demand, ...]:
    """Reduce original plan slots within a caller-split inclusive interval."""
    _period(start, end)
    validate_coverage(demands, coverages)
    removed: dict[str, set[int]] = {}
    for coverage in coverages:
        if coverage.end < start or coverage.start > end:
            continue
        if coverage.start > start or coverage.end < end:
            raise ValueError("application interval must split at every coverage boundary")
        removed.setdefault(coverage.plan_id, set()).update(coverage.plan_slots)
    result = []
    for demand in demands:
        slots = removed.get(demand.id, set())
        if not slots:
            result.append(demand)
        elif len(slots) < demand.quantity:
            result.append(replace(demand, quantity=demand.quantity - len(slots),
                retained_person_ids=tuple(person for index, person in enumerate(demand.retained_person_ids)
                                          if index not in slots)))
    return tuple(result)

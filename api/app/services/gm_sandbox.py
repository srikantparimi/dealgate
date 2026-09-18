"""GM sandbox service — parse inputs, dispatch to the pure library, export xlsx.

This is the M1 sign-off surface: Finance validates the six templates against
their Excel here before Sales sees any GM UI. **All** math flows through
:mod:`app.gm.compute` — the library is read-only for this service (see
CLAUDE.md rule 2). We only translate between HTTP shapes and the library's
dataclasses, and format results.

Money in / money out is Python :class:`~decimal.Decimal`. The JSON layer
serialises Decimal as string; the router turns request bodies into Decimal
via :func:`_to_decimal` before ever touching the library.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any, Callable, Optional
from uuid import UUID

from app.gm import (
    EngagementType,
    compute as gm_compute,
    template_for,
)
from app.gm.core import min_price as gm_min_price
from app.gm.policy import INDIA_FLOOR, US_FLOOR, check_floors
from app.gm.templates.assessment import AssessmentInputs
from app.gm.templates.fixed_price import FixedPriceInputs
from app.gm.templates.managed_service import ManagedServiceInputs
from app.gm.templates.single_resource import SingleResourceInputs
from app.gm.templates.staff_aug import StaffAugInputs
from app.gm.templates.tm import TMInputs
from app.gm.types import CostLine, Money, ResourceLine, TemplateResult

# --- exceptions ------------------------------------------------------------


class SandboxInputError(ValueError):
    """Raised when a request payload can't be parsed into template inputs.

    The router turns this into HTTP 422 with the message as the detail.
    """


# --- decimal / date parsing ------------------------------------------------


def _to_decimal(value: Any, *, field: str) -> Decimal:
    if value is None:
        raise SandboxInputError(f"{field} is required")
    try:
        # Route through str so we never accept a float (blueprint §2).
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise SandboxInputError(f"{field} is not a valid number: {value!r}") from exc


def _to_optional_decimal(value: Any, *, field: str) -> Optional[Decimal]:
    if value is None:
        return None
    return _to_decimal(value, field=field)


def _to_date(value: Any, *, field: str) -> date:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise SandboxInputError(f"{field} must be an ISO date string (YYYY-MM-DD)")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SandboxInputError(f"{field} is not an ISO date: {value!r}") from exc


def _parse_resource(raw: Any, *, field: str) -> ResourceLine:
    if not isinstance(raw, dict):
        raise SandboxInputError(f"{field} must be an object")
    location = raw.get("location")
    if location not in ("US", "India"):
        raise SandboxInputError(f"{field}.location must be 'US' or 'India'")
    return ResourceLine(
        role=str(raw.get("role", "")),
        seniority=str(raw.get("seniority", "")),
        location=location,
        allocation_pct=_to_decimal(raw.get("allocation_pct", "1"), field=f"{field}.allocation_pct"),
        start=_to_date(raw.get("start"), field=f"{field}.start"),
        end=_to_date(raw.get("end"), field=f"{field}.end"),
        hours_billable=_to_decimal(raw.get("hours_billable", 0), field=f"{field}.hours_billable"),
        hourly_bill_rate=_to_decimal(
            raw.get("hourly_bill_rate", 0), field=f"{field}.hourly_bill_rate"
        ),
        hourly_cost=_to_optional_decimal(raw.get("hourly_cost"), field=f"{field}.hourly_cost"),
        validated_by=raw.get("validated_by"),
    )


def _parse_cost(raw: Any, *, field: str) -> CostLine:
    if not isinstance(raw, dict):
        raise SandboxInputError(f"{field} must be an object")
    category = raw.get("category")
    if category not in ("tools", "travel", "subcontractor", "other"):
        raise SandboxInputError(
            f"{field}.category must be one of tools/travel/subcontractor/other"
        )
    location = raw.get("location", "US")
    if location not in ("US", "India"):
        raise SandboxInputError(f"{field}.location must be 'US' or 'India'")
    return CostLine(
        category=category,
        amount=_to_optional_decimal(raw.get("amount"), field=f"{field}.amount"),
        note=str(raw.get("note", "")),
        location=location,
    )


# --- template dispatch: raw dict -> dataclass ------------------------------


def _parse_resources(raw: Any, *, field: str = "resources") -> list[ResourceLine]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise SandboxInputError(f"{field} must be a list")
    return [_parse_resource(r, field=f"{field}[{i}]") for i, r in enumerate(raw)]


def _parse_costs(raw: Any, *, field: str = "costs") -> list[CostLine]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise SandboxInputError(f"{field} must be a list")
    return [_parse_cost(c, field=f"{field}[{i}]") for i, c in enumerate(raw)]


def _parse_staff_aug(inputs: dict) -> StaffAugInputs:
    resources = _parse_resources(inputs.get("resources"))
    pbu_raw = inputs.get("pbu_hours") or []
    if not isinstance(pbu_raw, list):
        raise SandboxInputError("pbu_hours must be a list of decimals aligned with resources")
    pbu_hours = [_to_decimal(v, field=f"pbu_hours[{i}]") for i, v in enumerate(pbu_raw)]
    return StaffAugInputs(
        resources=resources,
        pbu_hours=pbu_hours,
        replacement_obligation=bool(inputs.get("replacement_obligation", False)),
        costs=_parse_costs(inputs.get("costs")),
    )


def _parse_single_resource(inputs: dict) -> SingleResourceInputs:
    raw = inputs.get("resource")
    resource = _parse_resource(raw, field="resource") if raw is not None else None
    return SingleResourceInputs(
        resource=resource,
        costs=_parse_costs(inputs.get("costs")),
    )


def _parse_fixed_price(inputs: dict) -> FixedPriceInputs:
    return FixedPriceInputs(
        total_price=_to_decimal(inputs.get("total_price"), field="total_price"),
        revenue_us=_to_decimal(inputs.get("revenue_us", "0"), field="revenue_us"),
        revenue_india=_to_decimal(inputs.get("revenue_india", "0"), field="revenue_india"),
        resources=_parse_resources(inputs.get("resources")),
        costs=_parse_costs(inputs.get("costs")),
        unallocated_cost_notes=list(inputs.get("unallocated_cost_notes") or []),
    )


def _parse_assessment(inputs: dict) -> AssessmentInputs:
    return AssessmentInputs(
        deliverable=str(inputs.get("deliverable") or ""),
        total_price=_to_decimal(inputs.get("total_price"), field="total_price"),
        revenue_us=_to_decimal(inputs.get("revenue_us", "0"), field="revenue_us"),
        revenue_india=_to_decimal(inputs.get("revenue_india", "0"), field="revenue_india"),
        resources=_parse_resources(inputs.get("resources")),
        costs=_parse_costs(inputs.get("costs")),
    )


def _parse_tm(inputs: dict) -> TMInputs:
    return TMInputs(
        resources=_parse_resources(inputs.get("resources")),
        revenue_cap=_to_optional_decimal(inputs.get("revenue_cap"), field="revenue_cap"),
        costs=_parse_costs(inputs.get("costs")),
    )


def _parse_managed_service(inputs: dict) -> ManagedServiceInputs:
    return ManagedServiceInputs(
        monthly_fee_us=_to_decimal(inputs.get("monthly_fee_us", "0"), field="monthly_fee_us"),
        monthly_fee_india=_to_decimal(
            inputs.get("monthly_fee_india", "0"), field="monthly_fee_india"
        ),
        term_months=_to_decimal(inputs.get("term_months", "0"), field="term_months"),
        resources=_parse_resources(inputs.get("resources")),
        costs=_parse_costs(inputs.get("costs")),
    )


_PARSERS: dict[str, Callable[[dict], Any]] = {
    EngagementType.STAFF_AUG.value: _parse_staff_aug,
    EngagementType.SINGLE_RESOURCE.value: _parse_single_resource,
    EngagementType.FIXED_PRICE.value: _parse_fixed_price,
    EngagementType.ASSESSMENT.value: _parse_assessment,
    EngagementType.TM.value: _parse_tm,
    EngagementType.MANAGED_SERVICE.value: _parse_managed_service,
}


def parse_engagement_type(raw: Any) -> EngagementType:
    if not isinstance(raw, str):
        raise SandboxInputError("engagement_type must be a string")
    try:
        return EngagementType(raw)
    except ValueError as exc:
        allowed = ", ".join(sorted(t.value for t in EngagementType if t.value in _PARSERS))
        raise SandboxInputError(
            f"engagement_type {raw!r} is not one of: {allowed}"
        ) from exc


def parse_inputs(engagement_type: EngagementType, inputs: dict) -> Any:
    parser = _PARSERS.get(engagement_type.value)
    if parser is None:
        raise SandboxInputError(
            f"engagement_type {engagement_type.value!r} not supported in the sandbox"
        )
    if not isinstance(inputs, dict):
        raise SandboxInputError("inputs must be an object")
    return parser(inputs)


# --- schema for the UI form builder ----------------------------------------


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    kind: str  # "money" | "decimal" | "date" | "text" | "bool" | "resources" | "costs" | "list[decimal]" | "resource"
    required: bool = True
    help: str = ""


_SCHEMAS: dict[str, list[FieldSpec]] = {
    EngagementType.STAFF_AUG.value: [
        FieldSpec("resources", "Resources", "resources", True),
        FieldSpec(
            "pbu_hours",
            "Paid-but-unbilled hours (per resource)",
            "list[decimal]",
            False,
            "Aligned index-wise with the resources table. Adds cost only.",
        ),
        FieldSpec("replacement_obligation", "Replacement obligation", "bool", False),
        FieldSpec("costs", "Non-labor costs", "costs", False),
    ],
    EngagementType.SINGLE_RESOURCE.value: [
        FieldSpec("resource", "Resource", "resource", True),
        FieldSpec("costs", "Non-labor costs", "costs", False),
    ],
    EngagementType.FIXED_PRICE.value: [
        FieldSpec("total_price", "Total price", "money", True),
        FieldSpec("revenue_us", "US revenue allocation", "money", True),
        FieldSpec("revenue_india", "India revenue allocation", "money", True),
        FieldSpec("resources", "Delivery plan — resources", "resources", False),
        FieldSpec("costs", "Delivery plan — non-labor", "costs", False),
        FieldSpec(
            "unallocated_cost_notes",
            "Known-but-unquantified costs",
            "list[text]",
            False,
            "Names of cost lines you know exist but haven't estimated yet.",
        ),
    ],
    EngagementType.ASSESSMENT.value: [
        FieldSpec("deliverable", "Deliverable", "text", True),
        FieldSpec("total_price", "Total price", "money", True),
        FieldSpec("revenue_us", "US revenue allocation", "money", True),
        FieldSpec("revenue_india", "India revenue allocation", "money", True),
        FieldSpec("resources", "Team", "resources", True),
        FieldSpec("costs", "Non-labor costs", "costs", False),
    ],
    EngagementType.TM.value: [
        FieldSpec("resources", "Resources (forecast hours)", "resources", True),
        FieldSpec("revenue_cap", "Revenue cap (optional)", "money", False),
        FieldSpec("costs", "Non-labor costs", "costs", False),
    ],
    EngagementType.MANAGED_SERVICE.value: [
        FieldSpec("monthly_fee_us", "Monthly fee — US", "money", True),
        FieldSpec("monthly_fee_india", "Monthly fee — India", "money", True),
        FieldSpec("term_months", "Term (months)", "decimal", True),
        FieldSpec("resources", "Delivery pod — resources", "resources", False),
        FieldSpec("costs", "Non-labor costs", "costs", False),
    ],
}


def schema_for(engagement_type: EngagementType) -> dict:
    fields = _SCHEMAS.get(engagement_type.value)
    if fields is None:
        raise SandboxInputError(
            f"engagement_type {engagement_type.value!r} has no sandbox schema"
        )
    return {
        "engagement_type": engagement_type.value,
        "fields": [
            {
                "name": f.name,
                "label": f.label,
                "kind": f.kind,
                "required": f.required,
                "help": f.help,
            }
            for f in fields
        ],
    }


# --- policy resolution -----------------------------------------------------


@dataclass(frozen=True)
class ResolvedPolicy:
    us_floor: Decimal
    india_floor: Decimal
    policy_version_id: Optional[UUID]
    rate_card_version_id: Optional[UUID]
    source: str  # "active" | "defaults"


async def resolve_policy(
    session: Any,
    policy_version_id: Optional[UUID],
    rate_card_version_id: Optional[UUID],
) -> ResolvedPolicy:
    """Look up floors from Agent L's policy tables, falling back to defaults.

    Agent L is publishing ``services/policy.py::active_policy`` and
    ``services/rate_cards.py::active_rate_card`` in parallel. Import at call
    time so this router keeps working while those modules are still landing.
    Any error (import missing, table missing, query fails) collapses to the
    blueprint defaults — the sandbox is a math tool, not a policy publisher.
    """
    us_floor = US_FLOOR
    india_floor = INDIA_FLOOR
    resolved_policy_id: Optional[UUID] = policy_version_id
    resolved_rate_card_id: Optional[UUID] = rate_card_version_id
    source = "defaults"

    try:
        from app.services.policy import active_policy  # type: ignore
    except ImportError:
        active_policy = None  # type: ignore

    try:
        from app.services.rate_cards import active_rate_card  # type: ignore
    except ImportError:
        active_rate_card = None  # type: ignore

    if active_policy is not None:
        try:
            policy = await active_policy(session)
        except Exception:
            # Table missing, engine misconfigured — treat as "not yet".
            policy = None
        if policy is not None and not getattr(policy, "is_default", False):
            us_floor = getattr(policy, "us_floor", us_floor) or us_floor
            india_floor = getattr(policy, "india_floor", india_floor) or india_floor
            resolved_policy_id = getattr(policy, "id", resolved_policy_id)
            source = "active"

    if active_rate_card is not None:
        try:
            card = await active_rate_card(session)
        except Exception:
            card = None
        if card is not None:
            resolved_rate_card_id = getattr(card, "id", resolved_rate_card_id)

    return ResolvedPolicy(
        us_floor=Decimal(str(us_floor)),
        india_floor=Decimal(str(india_floor)),
        policy_version_id=resolved_policy_id,
        rate_card_version_id=resolved_rate_card_id,
        source=source,
    )


def _custom_check_floors(result: TemplateResult, policy: ResolvedPolicy) -> dict:
    """Same shape as :func:`app.gm.policy.check_floors` but with a resolved
    per-tenant floor. Defaults path just re-uses the library helper."""
    if policy.us_floor == US_FLOOR and policy.india_floor == INDIA_FLOOR:
        return check_floors(result)

    failing: list[str] = []
    us_present = result.revenue_us > 0
    india_present = result.revenue_india > 0
    us_pass = True
    if us_present:
        us_pass = result.gm_us is not None and result.gm_us >= policy.us_floor
        if not us_pass:
            failing.append("US")
    india_pass = True
    if india_present:
        india_pass = result.gm_india is not None and result.gm_india >= policy.india_floor
        if not india_pass:
            failing.append("India")
    requires_ceo = bool(failing) or not result.complete
    return {
        "us_pass": us_pass,
        "india_pass": india_pass,
        "requires_ceo": requires_ceo,
        "failing": failing,
    }


# --- serialisation ---------------------------------------------------------


def _fmt(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return format(value, "f")


def _mask_incomplete_gm(
    result: TemplateResult, raw_inputs: dict
) -> tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
    """Mask component GMs when a cost input on that component is missing.

    The pure library reports GM against *known* cost — an unknown cost line
    can bias a GM upward (revenue banked, cost dropped). Blueprint §2 says
    never show a spurious number; the sandbox surfaces "N/A" until Finance
    supplies the missing cost. Blended follows the same rule.
    """
    us_masked = False
    india_masked = False
    for token in result.missing:
        loc = _location_for_missing(token, raw_inputs)
        if loc == "US":
            us_masked = True
        elif loc == "India":
            india_masked = True
        else:
            # Unattributable missing → mask both to be safe.
            us_masked = True
            india_masked = True

    gm_us = None if us_masked else result.gm_us
    gm_india = None if india_masked else result.gm_india
    gm_blended = result.gm_blended if (not us_masked and not india_masked) else None
    return gm_us, gm_india, gm_blended


def _location_for_missing(token: str, raw_inputs: dict) -> Optional[str]:
    """Best-effort mapping from a ``missing`` token back to its component."""
    # e.g. "resources[0].hourly_cost" or "costs[3].amount".
    import re

    m = re.match(r"^(resources|costs)\[(\d+)\]", token)
    if not m:
        # "resource.hourly_cost" (single-resource template).
        if token.startswith("resource"):
            r = raw_inputs.get("resource")
            if isinstance(r, dict) and r.get("location") in ("US", "India"):
                return r["location"]
        return None
    field, idx_s = m.group(1), int(m.group(2))
    lst = raw_inputs.get(field)
    if not isinstance(lst, list) or idx_s >= len(lst):
        return None
    entry = lst[idx_s]
    if isinstance(entry, dict):
        loc = entry.get("location")
        if loc in ("US", "India"):
            return loc
    return None


def build_response(
    engagement_type: EngagementType,
    result: TemplateResult,
    policy: ResolvedPolicy,
    raw_inputs: Optional[dict] = None,
) -> dict:
    gm_us, gm_india, gm_blended = _mask_incomplete_gm(result, raw_inputs or {})
    # Build a mutable copy of the result for the policy check so masked GMs
    # feed straight into the pass/fail evaluation.
    masked = TemplateResult(
        revenue_us=result.revenue_us,
        cost_us=result.cost_us,
        revenue_india=result.revenue_india,
        cost_india=result.cost_india,
        gm_us=gm_us,
        gm_india=gm_india,
        gm_blended=gm_blended,
        complete=result.complete,
        missing=list(result.missing),
    )
    policy_check = _custom_check_floors(masked, policy)

    # Min prices: only meaningful when we have cost on that component.
    min_price_us: Optional[Decimal] = None
    min_price_india: Optional[Decimal] = None
    if result.cost_us > 0:
        min_price_us = gm_min_price(result.cost_us, policy.us_floor)
    if result.cost_india > 0:
        min_price_india = gm_min_price(result.cost_india, policy.india_floor)

    return {
        "engagement_type": engagement_type.value,
        "revenue_us": _fmt(result.revenue_us),
        "cost_us": _fmt(result.cost_us),
        "gm_us": _fmt(gm_us),
        "revenue_india": _fmt(result.revenue_india),
        "cost_india": _fmt(result.cost_india),
        "gm_india": _fmt(gm_india),
        "gm_blended": _fmt(gm_blended),
        "geography": result.geography,
        "complete": result.complete,
        "missing": list(result.missing),
        "policy": {
            "us_floor": _fmt(policy.us_floor),
            "india_floor": _fmt(policy.india_floor),
            "us_pass": policy_check["us_pass"],
            "india_pass": policy_check["india_pass"],
            "requires_ceo": policy_check["requires_ceo"],
            "failing": policy_check["failing"],
            "source": policy.source,
        },
        "min_price_us": _fmt(min_price_us),
        "min_price_india": _fmt(min_price_india),
        "policy_version_id": str(policy.policy_version_id) if policy.policy_version_id else None,
        "rate_card_version_id": (
            str(policy.rate_card_version_id) if policy.rate_card_version_id else None
        ),
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def run_compute(engagement_type: EngagementType, raw_inputs: dict) -> TemplateResult:
    """Parse inputs and delegate to :func:`app.gm.compute`."""
    # Validate the type is supported by the sandbox even though ``compute``
    # would also raise — we want a clean 422, not a 500.
    if engagement_type.value not in _PARSERS:
        raise SandboxInputError(
            f"engagement_type {engagement_type.value!r} not supported in the sandbox"
        )
    parsed = parse_inputs(engagement_type, raw_inputs)
    # Confirm the template exists (dispatch validates too).
    template_for(engagement_type)
    return gm_compute(engagement_type, parsed)


# --- xlsx export -----------------------------------------------------------


def _echo_resources(inputs: dict) -> list[list[Any]]:
    """Rows for the Inputs sheet's resources table. Empty for templates
    without resource lines."""
    resources = inputs.get("resources")
    if not isinstance(resources, list):
        # Some templates use "resource" (singular).
        r = inputs.get("resource")
        if isinstance(r, dict):
            resources = [r]
        else:
            return []
    rows: list[list[Any]] = [
        ["role", "seniority", "location", "hours_billable", "hourly_bill_rate", "hourly_cost"]
    ]
    for r in resources:
        if not isinstance(r, dict):
            continue
        rows.append(
            [
                r.get("role", ""),
                r.get("seniority", ""),
                r.get("location", ""),
                r.get("hours_billable", ""),
                r.get("hourly_bill_rate", ""),
                r.get("hourly_cost", ""),
            ]
        )
    return rows


def build_xlsx(engagement_type: EngagementType, inputs: dict, response: dict) -> bytes:
    """Two-sheet workbook: Inputs (echo) + Result (per-component + policy).

    The Result sheet's cell values are the **same Decimal strings** that
    :func:`build_response` produced, so a test can compare Decimal-to-Decimal
    without any float round-trip.
    """
    from openpyxl import Workbook

    wb = Workbook()
    inputs_sheet = wb.active
    inputs_sheet.title = "Inputs"
    inputs_sheet.append(["engagement_type", engagement_type.value])
    inputs_sheet.append([])
    # Revenue split echo, when present.
    for key in ("total_price", "revenue_us", "revenue_india", "monthly_fee_us",
                "monthly_fee_india", "term_months", "revenue_cap", "deliverable",
                "replacement_obligation"):
        if key in inputs and inputs[key] not in (None, ""):
            inputs_sheet.append([key, str(inputs[key])])
    inputs_sheet.append([])
    for row in _echo_resources(inputs):
        inputs_sheet.append(row)

    result_sheet = wb.create_sheet("Result")
    # Emit label, value pairs so the test can build a dict trivially.
    for k in (
        "revenue_us",
        "cost_us",
        "gm_us",
        "revenue_india",
        "cost_india",
        "gm_india",
        "gm_blended",
        "min_price_us",
        "min_price_india",
        "complete",
        "geography",
        "computed_at",
    ):
        result_sheet.append([k, response.get(k)])
    result_sheet.append(["us_pass", response["policy"]["us_pass"]])
    result_sheet.append(["india_pass", response["policy"]["india_pass"]])
    result_sheet.append(["requires_ceo", response["policy"]["requires_ceo"]])
    result_sheet.append(["us_floor", response["policy"]["us_floor"]])
    result_sheet.append(["india_floor", response["policy"]["india_floor"]])
    result_sheet.append(["policy_source", response["policy"]["source"]])
    result_sheet.append(["policy_version_id", response.get("policy_version_id") or ""])
    result_sheet.append(["rate_card_version_id", response.get("rate_card_version_id") or ""])
    result_sheet.append(["missing", ", ".join(response.get("missing") or [])])

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


__all__ = [
    "SandboxInputError",
    "ResolvedPolicy",
    "parse_engagement_type",
    "parse_inputs",
    "resolve_policy",
    "run_compute",
    "build_response",
    "build_xlsx",
    "schema_for",
]

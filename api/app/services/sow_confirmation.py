"""SOW confirmation service (Sprint 9 wave 1, story D + E).

Assembles the one confirmation payload the frontend renders: extracted
fields with provenance, auto-classified engagement type, auto-staffed
grid, auto-computed GM sheet, floor pass/fail, proposed approvers,
and the ``needs_you`` gap list.

The service is idempotent: repeated calls for the same
``(sow_version_id, gm_model_id)`` return the same auto-built GM model
without inserting a duplicate row (matched by ``sow_version_id`` +
``engagement_type`` on the ``gm_model`` table).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import append_audit
from app.integrations.bedrock_ceo_brief import draft_brief
from app.integrations.bedrock_classifier import (
    BedrockClassifier,
)
from app.integrations.bedrock_embeddings import Embedder
from app.models.ceo_exception import CeoException
from app.models.gm_model import GmModel
from app.models.opportunity import Opportunity
from app.models.sow import SowVersion
from app.services.auto_staffing import (
    AutoStaffingResult,
    StaffingLine,
    lines_to_payload_dicts,
    staff as auto_staff,
)
from app.services.approvers import ResolvedApprover, resolve_all
from app.services.delivery_model import (
    GmModelPayload,
    create_gm_model_version,
    parse_resource_line,
)
from app.services.embeddings import search_capabilities, search_sow
from app.services.engagement_classifier import ClassifierResult, classify
from app.services.provenance import read as read_provenance, wrap as wrap_provenance
from app.services.sow_extract import SowNotFound

# Rate-card resolver import is deferred to survive Agent WW's rename
# (services/rate_cards.py → services/cost_bands.py).
try:  # pragma: no cover — import branch, exercised in prod once renamed.
    from app.services.cost_bands import lookup_cost  # type: ignore
except ImportError:
    from app.services.rate_cards import lookup_cost  # noqa: F401 — kept for parity


@dataclass
class NeedsYou:
    field: str
    reason: str


@dataclass
class ConfirmationPayload:
    sow_version: SowVersion
    engagement: ClassifierResult
    staffing: AutoStaffingResult
    gm_model: GmModel | None
    floors: dict[str, Any]
    approvers: dict[str, ResolvedApprover]
    projected_tasks: list[dict[str, Any]]
    needs_you: list[NeedsYou] = field(default_factory=list)
    ceo_exception: CeoException | None = None
    source: dict[str, Any] = field(default_factory=dict)


# --- classifier + staffing wiring -----------------------------------------


def _make_past_sow_search(
    session: AsyncSession, embedder: Embedder | None
) -> Any:
    if embedder is None:
        return None

    async def _search(q: str) -> list[dict[str, Any]]:
        return await search_sow(session, embedder=embedder, query_text=q, top_k=5)

    return _search


def _make_capability_search(
    session: AsyncSession, embedder: Embedder | None
) -> Any:
    if embedder is None:
        return None

    async def _search(q: str) -> list[dict[str, Any]]:
        return await search_capabilities(
            session, embedder=embedder, query_text=q, top_k=5
        )

    return _search


# --- GM wiring ------------------------------------------------------------


def _extracted_price(version: SowVersion) -> Decimal | None:
    """The fixed price from the SOW extraction, or None if not present."""

    fields = version.extracted_fields or {}
    raw = read_provenance(fields.get("price")).get("value")
    if raw in (None, "", []):
        return None
    try:
        # The extractor writes prices as strings like "50000" / "50000.00";
        # strip currency symbols and thousands separators defensively.
        s = str(raw).replace(",", "").replace("$", "").strip()
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _build_gm_payload(
    engagement_type: str,
    staffing: AutoStaffingResult,
    sow_version_id: uuid.UUID,
    total_price: Decimal | None = None,
) -> GmModelPayload | None:
    """Translate proposed staffing lines into the GM model payload.

    ``permanent_placement`` produces no lines — we return ``None`` and
    the caller skips the create step. Empty lines for other types also
    return ``None`` (the confirm screen surfaces the gap in needs_you).

    ``total_price`` (when provided, for fixed-fee engagements) is the
    revenue the SOW extraction saw. Without it the GM engine treats a
    fixed-price SOW as zero-revenue and every margin comes out
    "Unavailable" — the exact defect in the 5th report.
    """

    payload_rows = lines_to_payload_dicts(staffing.lines)
    if not payload_rows:
        return None
    parsed = [
        parse_resource_line(r, field=f"resource_lines[{i}]")
        for i, r in enumerate(payload_rows)
    ]
    return GmModelPayload(
        engagement_type=engagement_type,
        sow_version_id=sow_version_id,
        delivery_pattern=None,
        contingency_pct=None,
        warranty_days=None,
        resource_lines=parsed,
        cost_lines=[],
        phases=[],
        total_price=total_price,
    )


async def _existing_gm_for_sow(
    session: AsyncSession,
    *,
    sow_id: uuid.UUID,
) -> GmModel | None:
    """The latest GM model for a specific ``sow``.

    Keying by ``sow_id`` (not ``opportunity_id``) is what makes "one query,
    one answer" true even if a future codepath ever puts two ``Sow`` rows
    under one opportunity. Today the invariant is one Sow per opportunity
    (`sow_extract._load_or_create_sow`), but the invariant lives in a
    ``scalar_one_or_none()`` call, not in the schema. Scoping the read by
    ``sow_id`` moves that invariant into the query so it can't drift.

    Approved packages pin their exact ``gm_model_id`` (immutable, CLAUDE.md
    rule 4), so a later edit that creates a new ``GmModel`` here does not
    displace what the frozen ``approval_package`` still reads.
    """

    stmt = (
        select(GmModel)
        .options(
            selectinload(GmModel.resource_lines),
            selectinload(GmModel.cost_lines),
        )
        .where(GmModel.sow_id == sow_id)
        .order_by(GmModel.created_at.desc(), GmModel.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# --- floors ---------------------------------------------------------------


def _compute_floors(model: GmModel | None) -> dict[str, Any]:
    if model is None:
        # "Not computed" is not "passed". This previously returned
        # us_pass/india_pass = True, so a SOW with no GM model at all
        # rendered green floor bars on the confirm screen — the exact
        # opposite of what the reader should conclude. `has_gm` lets the
        # caller distinguish "no model" from "model that failed".
        return {
            "has_gm": False,
            "gm_model_id": None,
            "us_pass": False,
            "india_pass": False,
            "requires_ceo": True,
            "failing": [],
            "reason": "no gm model yet — cannot compute floors",
        }
    # Reuse the ratified compute path.
    from app.services.delivery_model import (
        DeliveryModelInputError,
        _extra_inputs_for_model,
        _model_to_payload,
        build_compute_response,
        compute_live,
    )
    from app.services.gm_sandbox import SandboxInputError

    try:
        result = compute_live(
            _model_to_payload(model), extra_inputs=_extra_inputs_for_model(model)
        )
    except (DeliveryModelInputError, SandboxInputError) as exc:
        # A computation that FAILED is not a computation that passed. This
        # returned us_pass/india_pass = True, so a GM sheet the engine could
        # not evaluate rendered green floor bars.
        return {
            "has_gm": True,
            "gm_model_id": str(model.id),
            "us_pass": False,
            "india_pass": False,
            "requires_ceo": True,
            "failing": [],
            "error": str(exc),
            "reason": f"gross margin could not be computed: {exc}",
        }
    response = build_compute_response(result)
    policy = response.get("policy") or {}

    # A margin needs revenue to exist at all. With revenue of zero the ratio
    # is undefined, and the policy check passes vacuously — which is how a
    # sheet reading "Revenue 0.00, GM Unavailable" still showed "Passes both
    # floors". Nothing green should appear next to a number nobody computed.
    blended = response.get("gm_blended")
    us_gm = response.get("gm_us")
    india_gm = response.get("gm_india")
    if blended is None and us_gm is None and india_gm is None:
        return {
            "has_gm": True,
            "gm_model_id": str(model.id),
            "us_pass": False,
            "india_pass": False,
            "requires_ceo": True,
            "failing": [],
            "gm_us": None,
            "gm_india": None,
            "gm_blended": None,
            "reason": (
                "no gross margin could be calculated from this plan — it has "
                "no revenue, or no costed lines"
            ),
        }

    return {
        "has_gm": True,
        "gm_model_id": str(model.id),
        "us_pass": policy.get("us_pass", True),
        "india_pass": policy.get("india_pass", True),
        "requires_ceo": policy.get("requires_ceo", False),
        "failing": policy.get("failing", []),
        "gm_us": response.get("gm_us"),
        "gm_india": response.get("gm_india"),
        "gm_blended": response.get("gm_blended"),
    }


def _staffing_from_gm(model: GmModel) -> AutoStaffingResult:
    """Read the committed plan back off the saved GM model.

    Provenance is ``manual``: these lines were entered or uploaded by a
    person, not derived from the document, and the confirm screen should say
    so rather than implying the system worked them out.
    """

    lines: list[StaffingLine] = []
    warnings: list[str] = []
    for r in getattr(model, "resource_lines", []) or []:
        # ORM columns are `hourly_loaded_cost` / `billable_hours`; the GM
        # payload shape calls them `hourly_cost` / `hours_billable`. Read
        # the ORM names here.
        cost = getattr(r, "hourly_loaded_cost", None)
        lines.append(
            StaffingLine(
                role=r.role,
                seniority=r.seniority,
                location=r.location,
                allocation_pct=r.allocation_pct,
                hours_billable=r.billable_hours,
                hourly_bill_rate=r.hourly_bill_rate,
                hourly_cost=cost,
                provenance="manual",
                start_date=r.start_date,
                end_date=r.end_date,
                source_id=str(model.id),
                warning=None if cost is not None else "no cost rate resolved",
            )
        )
        if cost is None:
            # Without a cost rate there is no margin, only a revenue figure.
            # Say it here so it becomes a submit blocker rather than a silent
            # "unavailable" on the screen.
            warnings.append(
                f"{r.role} ({r.seniority}, {r.location}): no cost rate — "
                "publish a cost band or enter the loaded cost on the line"
            )
    return AutoStaffingResult(
        lines=lines,
        notes=[f"staffing read from saved GM model {model.id}"],
        warnings=warnings,
        sources=[str(model.id)],
    )


def _is_fixed_fee(engagement_type: str) -> bool:
    """Engagements whose revenue is settled rather than billed by the hour."""

    return engagement_type in ("fixed_price", "assessment")


# --- needs_you ------------------------------------------------------------


# Fields a human must resolve before submit.
#
# `currency` is deliberately absent. SmarTek21 contracts in USD, so a SOW
# that shows "$50,000.00" without naming a currency is not ambiguous — it is
# normal. Blocking submit on it made every SOW carry a gap that the reviewer
# could only ever close one way, which trains people to click through the
# gaps rather than read them. The extractor is asked to answer USD for $
# amounts, and `_default_currency` fills it when the document truly is silent.
_ESSENTIAL_FIELDS: tuple[str, ...] = (
    "scope_summary",
    "price",
    "term_start",
    "term_end",
    "deliverables",
    "signatories",
)

# The house currency. Everything SmarTek21 signs is in USD.
DEFAULT_CURRENCY = "USD"


def _needs_you_for(
    sow_version: SowVersion,
    engagement: ClassifierResult,
    staffing: AutoStaffingResult,
    floors: dict[str, Any],
) -> list[NeedsYou]:
    """Enumerate every gap a human must resolve before submit."""

    gaps: list[NeedsYou] = []
    fields = sow_version.extracted_fields or {}

    # 1. Essential extracted fields with no value.
    for name in _ESSENTIAL_FIELDS:
        entry = read_provenance(fields.get(name))
        if entry.get("value") in (None, "", [], {}):
            gaps.append(NeedsYou(field=name, reason="extracted value missing"))

    # 2. Ambiguous classifier — needs a pick.
    if not engagement.auto_confirm:
        gaps.append(
            NeedsYou(
                field="engagement_type",
                reason=(
                    "classifier confidence below threshold — pick between "
                    f"{engagement.primary.type} and "
                    f"{engagement.secondary.type if engagement.secondary else 'unknown'}"
                ),
            )
        )

    # 3. Staffing warnings surface directly.
    for w in staffing.warnings:
        gaps.append(NeedsYou(field="staffing", reason=w))

    # 4. A costed staffing plan is the whole basis of the gross margin.
    #
    # Without these checks the screen offered "Submit for approval" on a SOW
    # with no staffing at all. The backend refuses it (`submit_package`
    # 404s with "no gm_model for opportunity"), so nothing ungoverned ever
    # reached Finance — but the user got a dead button and no way to find out
    # what was actually missing. These make the screen tell the truth.
    #
    # `permanent_placement` is the one type with no staffing by design: the
    # placement fee is invoiced once, so an empty grid is correct there.
    if engagement.primary.type != "permanent_placement":
        if not staffing.lines:
            gaps.append(
                NeedsYou(
                    field="staffing",
                    reason=(
                        "no staffing plan — enter the roles, hours and rates or "
                        "upload the staffing sheet; gross margin cannot be "
                        "calculated without one"
                    ),
                )
            )
        else:
            for idx, line in enumerate(staffing.lines):
                label = f"{line.role} ({line.seniority})"
                if line.hours_billable is None or line.hours_billable <= 0:
                    gaps.append(
                        NeedsYou(
                            field=f"staffing[{idx}].hours_billable",
                            reason=f"{label}: billable hours not set",
                        )
                    )
                # What a line needs depends on how the engagement earns.
                #
                # On a fixed fee the revenue is the agreed price whatever the
                # hours turn out to be, so the bill rate never enters the
                # margin — the cost does. Demanding a bill rate here asked for
                # a number nobody has on a contract where nobody bills by the
                # hour, and it is what put three meaningless blockers on a
                # fixed-price SOW.
                if _is_fixed_fee(engagement.primary.type):
                    if line.hourly_cost is None or line.hourly_cost <= 0:
                        gaps.append(
                            NeedsYou(
                                field=f"staffing[{idx}].hourly_cost",
                                reason=(
                                    f"{label}: no cost rate — the margin on a "
                                    "fixed fee is the fee against cost, so this "
                                    "is the number that decides it. Set it on "
                                    "the line or publish a cost band."
                                ),
                            )
                        )
                elif line.hourly_bill_rate is None or line.hourly_bill_rate <= 0:
                    gaps.append(
                        NeedsYou(
                            field=f"staffing[{idx}].hourly_bill_rate",
                            reason=(
                                f"{label}: no bill rate — add one to the client "
                                "rate card or set it on the line"
                            ),
                        )
                    )

        # 5. No GM model means Finance has nothing to approve against.
        if floors.get("gm_model_id") is None and not floors.get("has_gm", False):
            gaps.append(
                NeedsYou(
                    field="gm_model",
                    reason=(
                        "gross margin not calculated — complete the staffing "
                        "plan so the GM sheet can be built"
                    ),
                )
            )

    return gaps


# --- projected tasks (renewal + notice) ----------------------------------


def _projected_tasks(sow_version: SowVersion) -> list[dict[str, Any]]:
    """Cheap projection of the renewal + notice tasks the SOW would file."""

    fields = sow_version.extracted_fields or {}
    end_val = read_provenance(fields.get("term_end")).get("value")
    notice_val = read_provenance(fields.get("notice_date")).get("value")
    out: list[dict[str, Any]] = []
    if end_val:
        out.append(
            {"kind": "renewal_review", "due": end_val, "owner_role": "Sales"}
        )
    if notice_val:
        out.append(
            {"kind": "notice_deadline", "due": notice_val, "owner_role": "Legal"}
        )
    return out


def _default_currency(version: SowVersion) -> None:
    """Fill an absent currency with USD, marked as defaulted.

    Not as `extracted` — the document did not say it. `defaulted` is one of
    the five provenance flavours precisely so a value the system supplied is
    distinguishable from one it read (CLAUDE.md rule 10), and the confirm
    screen renders it with the source of the default.
    """

    fields = version.extracted_fields
    if not isinstance(fields, dict):
        return
    entry = fields.get("currency")
    current = read_provenance(entry).get("value") if entry else None
    if current not in (None, ""):
        return
    fields["currency"] = wrap_provenance(
        DEFAULT_CURRENCY,
        provenance="defaulted",
        page_ref=(read_provenance(entry).get("page_ref") if entry else None),
        source_id="policy.house_currency",
        warning="not stated in the SOW — SmarTek21 contracts in USD",
        status="unconfirmed",
    )
    # JSONB is mutated in place; tell SQLAlchemy the attribute changed.
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(version, "extracted_fields")


# --- source block ---------------------------------------------------------


async def _source_block(
    session: AsyncSession,
    *,
    opportunity_id: uuid.UUID,
    version: SowVersion,
) -> dict[str, Any]:
    """Client, title and file for the "Source & type" section.

    These three rows used to be read out of ``extracted_fields`` under the
    keys ``client_entity``, ``sow_title`` and ``file`` — none of which the
    extractor has ever produced. So every upload rendered them as "unknown" /
    "manual" and told the reviewer the information was "Not on the SOW", while
    the client name sat in ``client_legal_name`` and the file key sat on the
    version row.

    They are not extracted fields at all: the client is a resolved master-data
    record, the file is a stored object. They come from the records.
    """

    from app.models.client import Client, LegalEntity

    opp = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == opportunity_id)
        )
    ).scalar_one_or_none()

    client_name: str | None = None
    client_id: str | None = None
    legal_entity_name: str | None = None

    if opp is not None and opp.client_id is not None:
        client = (
            await session.execute(select(Client).where(Client.id == opp.client_id))
        ).scalar_one_or_none()
        if client is not None:
            client_name = client.name
            client_id = str(client.id)
            entity = (
                await session.execute(
                    select(LegalEntity)
                    .where(LegalEntity.client_id == client.id)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if entity is not None:
                legal_entity_name = entity.name

    fields = version.extracted_fields or {}
    metadata = fields.get("metadata") or {}

    # Title: what the SOW is, said once. Derived, not typed — the client plus
    # the engagement it covers is what a person calls this document.
    extracted_client = read_provenance(fields.get("client_legal_name")).get("value")
    title_client = client_name or extracted_client
    scope = read_provenance(fields.get("scope_summary")).get("value")
    sow_title: str | None = None
    if title_client:
        suffix = str(scope).strip() if scope else ""
        sow_title = f"{title_client} — {suffix[:60]}" if suffix else str(title_client)

    file_key = version.file_s3_key or None
    return {
        "client_id": client_id,
        "client_name": client_name,
        "client_legal_name_extracted": extracted_client,
        "legal_entity_name": legal_entity_name,
        "sow_title": sow_title,
        "file_s3_key": file_key,
        "file_name": file_key.rsplit("/", 1)[-1] if file_key else None,
        "ref_unit": metadata.get("ref_unit", "page"),
        "document_kind": metadata.get("document_kind"),
    }


# --- CEO exception pre-draft ---------------------------------------------


async def _predraft_ceo_exception(
    session: AsyncSession,
    *,
    sow_version: SowVersion,
    gm_model: GmModel | None,
    floors: dict[str, Any],
) -> CeoException | None:
    """When floors predict a fail, draft a placeholder CEO brief early.

    The brief lands with no ``package_id`` reference — it is a
    prediction, not a decision. When the package is later submitted the
    real ``draft_for_package`` call replaces this record.
    """

    if not floors.get("requires_ceo"):
        return None
    if gm_model is None:
        return None

    fields = sow_version.extracted_fields or {}
    scope = read_provenance(fields.get("scope_summary")).get("value") or ""
    inputs = {
        "scope": scope,
        "team_summary": f"auto-staffed {len(gm_model.resource_lines)} line(s)",
        "gm": {
            "us": {"value": floors.get("gm_us"), "passes": floors.get("us_pass")},
            "india": {"value": floors.get("gm_india"), "passes": floors.get("india_pass")},
            "blended": {"value": floors.get("gm_blended")},
        },
        "sources": [str(gm_model.id)],
    }
    brief = draft_brief(inputs)
    # Not persisted: we return the transient brief so the confirmation
    # page can render "Will trigger". The real row is drafted on submit.
    row = CeoException(
        id=uuid.uuid4(),
        package_id=uuid.uuid4(),  # placeholder; replaced on submit
        brief_json=brief,
    )
    return row


# --- public API ----------------------------------------------------------


async def build_confirmation(
    session: AsyncSession,
    *,
    opportunity_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    bedrock_classifier: BedrockClassifier | None = None,
    embedder: Embedder | None = None,
    auto_create_gm: bool = True,
) -> ConfirmationPayload:
    """Assemble the confirmation payload for one opportunity.

    Runs classify → staff → auto-GM in the same transaction. The GM
    model creation is skipped when an equivalent GM model already exists
    for the SOW version (idempotency).
    """

    # 1. Latest SOW version.
    from app.services.sow_extract import latest_version_for as _latest

    state = await _latest(session, opportunity_id)
    if state is None:
        raise SowNotFound(f"no sow_version for opportunity {opportunity_id}")

    version = (
        await session.execute(
            select(SowVersion).where(SowVersion.id == state.id)
        )
    ).scalar_one()

    # 2. Classify.
    engagement = classify(
        version.extracted_fields or {}, bedrock=bedrock_classifier
    )

    # 3. Staffing.
    #
    # ONE store, ONE query, ONE answer — scoped to THIS SOW. Whatever the
    # Staffing tab last saved for this sow is what the confirm screen shows.
    # The auto-plan never overwrites what a human saved (rule 11 of the
    # sprint directive: "auto-plan seeds only an empty record, once"). Two
    # SOWs under the same opportunity keep separate plans because the query
    # keys on `sow_id`, not `opportunity_id`.
    gm_model: GmModel | None = await _existing_gm_for_sow(
        session, sow_id=version.sow_id
    )

    if gm_model is not None:
        # A saved plan is the answer; the auto-plan does not run.
        staffing = _staffing_from_gm(gm_model)
    else:
        # No plan on file. `auto_staff` returns lines only when the SOW itself
        # carried a resource table (staff_aug / single_resource / managed_service
        # with a role named / T&M with a resource table). For everything else
        # it returns [] with a note; the confirm screen surfaces the gap in
        # `needs_you`.
        past = _make_past_sow_search(session, embedder)
        caps = _make_capability_search(session, embedder)
        staffing = await auto_staff(
            engagement.primary.type,
            version.extracted_fields or {},
            past_sow_search=past,
            capability_search=caps,
        )
        # Auto-seed a GmModel ONLY when the SOW itself supplied the roster
        # (auto_staff returned real lines). A fabricated roster is never
        # persisted — that was the bug where re-opening confirm showed
        # "manual" phantoms nobody had entered.
        if auto_create_gm and staffing.lines:
            price = (
                _extracted_price(version)
                if _is_fixed_fee(engagement.primary.type)
                else None
            )
            payload = _build_gm_payload(
                engagement.primary.type, staffing, version.id, total_price=price
            )
            if payload is not None:
                gm_model = await create_gm_model_version(
                    session,
                    opportunity_id=opportunity_id,
                    actor_id=actor_id,
                    payload=payload,
                )

    # 5. Floors + approvers + tasks + CEO pre-draft.
    floors = _compute_floors(gm_model)
    approvers = await resolve_all(session)
    tasks = _projected_tasks(version)
    ceo_draft = await _predraft_ceo_exception(
        session, sow_version=version, gm_model=gm_model, floors=floors
    )

    _default_currency(version)

    source = await _source_block(session, opportunity_id=opportunity_id, version=version)

    needs = _needs_you_for(version, engagement, staffing, floors)
    return ConfirmationPayload(
        sow_version=version,
        engagement=engagement,
        staffing=staffing,
        gm_model=gm_model,
        floors=floors,
        approvers=approvers,
        projected_tasks=tasks,
        needs_you=needs,
        ceo_exception=ceo_draft,
        source=source,
    )


async def submit_confirmation(
    session: AsyncSession,
    *,
    opportunity_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> ConfirmationPayload:
    """Idempotent commit of the confirmation.

    Runs :func:`build_confirmation` (ensuring GM exists), transitions
    the opportunity's ``governance_status`` to ``SOWDraft.confirmed`` if
    it isn't already, and emits ``sow_confirmation.submitted``. A repeat
    call is a no-op transition (same status, still audits the attempt).
    """

    payload = await build_confirmation(
        session, opportunity_id=opportunity_id, actor_id=actor_id
    )

    opp = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == opportunity_id)
        )
    ).scalar_one()
    old_status = opp.governance_status
    if old_status != "SOWDraft.confirmed":
        opp.governance_status = "SOWDraft.confirmed"

    await append_audit(
        session,
        actor_id=actor_id,
        action="sow_confirmation.submitted",
        entity="opportunity",
        entity_id=str(opportunity_id),
        before={"governance_status": old_status},
        after={
            "governance_status": opp.governance_status,
            "sow_version_id": str(payload.sow_version.id),
            "gm_model_id": (
                str(payload.gm_model.id) if payload.gm_model else None
            ),
            "engagement_type": payload.engagement.primary.type,
            "needs_you_count": len(payload.needs_you),
        },
    )
    await session.commit()
    return payload


# --- serialisation for the router ----------------------------------------


def _decimal_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def serialize_confirmation(payload: ConfirmationPayload) -> dict[str, Any]:
    v = payload.sow_version
    engagement = payload.engagement
    return {
        "source": payload.source,
        "sow_version": {
            "id": str(v.id),
            "extracted_fields": v.extracted_fields,
            "extract_status": v.extract_status,
            "engagement_type_suggested": v.engagement_type_suggested,
        },
        "engagement": {
            "primary": {
                "type": engagement.primary.type,
                "confidence": engagement.primary.confidence,
            },
            "secondary": (
                {
                    "type": engagement.secondary.type,
                    "confidence": engagement.secondary.confidence,
                }
                if engagement.secondary
                else None
            ),
            "rule_matched": engagement.rule_matched,
            "auto_confirm": engagement.auto_confirm,
        },
        "staffing": {
            "lines": [line.to_dict() for line in payload.staffing.lines],
            "notes": payload.staffing.notes,
            "warnings": payload.staffing.warnings,
            "sources": payload.staffing.sources,
        },
        "gm_model": (
            {
                "id": str(payload.gm_model.id),
                "engagement_type": payload.gm_model.engagement_type,
                "revenue_us": _decimal_str(payload.gm_model.revenue_us),
                "revenue_india": _decimal_str(payload.gm_model.revenue_india),
                "resource_line_count": len(payload.gm_model.resource_lines),
            }
            if payload.gm_model
            else None
        ),
        "floors": payload.floors,
        "approvers": {
            fn: {
                "user_id": str(r.user_id) if r.user_id else None,
                "source": r.source,
                "business_unit": r.business_unit,
            }
            for fn, r in payload.approvers.items()
        },
        "projected_tasks": payload.projected_tasks,
        "needs_you": [{"field": n.field, "reason": n.reason} for n in payload.needs_you],
        "ceo_gate": (
            {
                "will_trigger": True,
                "brief": payload.ceo_exception.brief_json,
            }
            if payload.ceo_exception
            else {"will_trigger": False}
        ),
    }


__all__ = [
    "ConfirmationPayload",
    "NeedsYou",
    "build_confirmation",
    "serialize_confirmation",
    "submit_confirmation",
]

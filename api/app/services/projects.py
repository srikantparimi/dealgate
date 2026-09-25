"""Released project read model, pinned to approved SOW and staffing versions."""

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.approval import ApprovalPackage
from app.models.client import Client
from app.models.forecast import ForecastPeriod
from app.models.gm_model import GmModel
from app.models.opportunity import Opportunity
from app.models.sow import SowVersion
from app.models.user import User
from app.services.deals import is_leader
from app.services.delivery_model import _extra_inputs_for_model, _model_to_payload, compute_live
from app.services.provenance import value_of
from app.services.user_identity import display_user_name


def decimal_string(value):
    return format(value, "f") if value is not None else None


async def list_projects(session, *, actor):
    stmt = (
        select(ApprovalPackage, Opportunity, Client, SowVersion, User)
        .join(Opportunity, Opportunity.id == ApprovalPackage.opportunity_id)
        .outerjoin(Client, Client.id == Opportunity.client_id)
        .join(SowVersion, SowVersion.id == ApprovalPackage.sow_version_id)
        .outerjoin(User, User.id == Opportunity.owner_id)
        .where(ApprovalPackage.released_at.is_not(None), Opportunity.archived_at.is_(None))
        .order_by(ApprovalPackage.released_at.desc())
    )
    if not is_leader(actor):
        stmt = stmt.where(Opportunity.owner_id == actor.id)
    rows = (await session.execute(stmt)).all()
    result, seen = [], set()
    for package, opportunity, client, sow, owner in rows:
        if opportunity.id in seen or (client and client.archived_at):
            continue
        seen.add(opportunity.id)
        model = await session.scalar(
            select(GmModel)
            .where(GmModel.id == package.gm_model_id)
            .options(selectinload(GmModel.resource_lines), selectinload(GmModel.cost_lines))
        )
        computed = compute_live(
            _model_to_payload(model), extra_inputs=_extra_inputs_for_model(model)
        )
        forecast = await session.scalar(
            select(ForecastPeriod)
            .where(ForecastPeriod.gm_model_id == model.id)
            .order_by(ForecastPeriod.week_ending.desc())
            .limit(1)
        )
        fields = sow.extracted_fields or {}
        result.append(
            {
                "id": str(opportunity.id),
                "package_id": str(package.id),
                "gm_model_id": str(model.id),
                "title": value_of(fields.get("sow_title"))
                or value_of(fields.get("title"))
                or f"{client.name if client else 'Project'} - {model.engagement_type.replace('_', ' ')}",
                "client_name": client.name if client else None,
                "owner_name": display_user_name(owner.name, owner.email) if owner else "Unassigned",
                "sow_version": sow.version_no,
                "gm_version": model.version,
                "released_at": package.released_at.isoformat(),
                "term_end": value_of(fields.get("term_end")),
                "approved": {
                    "us": decimal_string(computed.gm_us) if computed.complete else None,
                    "india": decimal_string(computed.gm_india) if computed.complete else None,
                },
                "forecast": {
                    "us": decimal_string(forecast.forecast_gm_us) if forecast else None,
                    "india": decimal_string(forecast.forecast_gm_india) if forecast else None,
                    "as_of": str(forecast.week_ending) if forecast else None,
                },
                "resources": [
                    {
                        "id": str(r.id),
                        "name": r.person_name,
                        "role": r.role,
                        "location": r.location,
                        "allocation": decimal_string(r.allocation_pct),
                        "hours": decimal_string(r.billable_hours),
                        "start_date": str(r.start_date),
                        "end_date": str(r.end_date),
                    }
                    for r in model.resource_lines
                ],
            }
        )
    return result

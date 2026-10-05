"""Tracking shares the real Pipeline Deal read boundary and audit-backed CAS."""

import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import func, select

from app.models.audit import AuditEvent
from app.models.user import User
from app.services.hubspot_pipeline import (
    PipelineFilters, get_pipeline_deal, matching_opportunity_ids, scope_pipeline_filters,
)


async def require_deal_access(session, actor, opportunity_id):
    from app.routers.pipeline import _require_reader

    _require_reader(actor)
    filters = await scope_pipeline_filters(session, actor, PipelineFilters(include_closed=True))
    deal = await get_pipeline_deal(session, opportunity_id, filters=filters)
    if deal is None:
        raise HTTPException(404, "deal not found")
    return deal


async def visible_deal_ids(session, actor, *, client_id=None):
    from app.routers.pipeline import PIPELINE_READ_ROLES

    if not set(actor.groups or []) & PIPELINE_READ_ROLES:
        return ()
    filters = PipelineFilters(include_closed=True, client=(client_id,) if client_id else ())
    filters = await scope_pipeline_filters(session, actor, filters)
    return tuple(await matching_opportunity_ids(session, filters))


async def assignable_users(session, actor, opportunity_id):
    from app.routers.pipeline import PIPELINE_READ_ROLES
    from app.services.test_fixtures import account_scope, user_allowed

    deal = await require_deal_access(session, actor, opportunity_id)
    scope = await account_scope(session, deal.client_id, opportunity_id=opportunity_id) if deal.client_id else None
    users = (await session.scalars(select(User).order_by(User.name, User.id))).all()
    return [user for user in users if set(user.groups or []) & PIPELINE_READ_ROLES and user_allowed(user, scope)]


async def require_assignee(session, actor, opportunity_id, assignee_id):
    if assignee_id not in {user.id for user in await assignable_users(session, actor, opportunity_id)}:
        raise HTTPException(403, "Assignee is outside this deal's authorized registered users")


async def revision(session, entity, row_id, values):
    count = await session.scalar(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.entity == entity, AuditEvent.entity_id == str(row_id)))
    payload = {"entity": entity, "id": str(row_id), "mutations": count, "values": values}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def check_revision(expected, actual):
    if expected is None:
        raise HTTPException(428, "A revision is required; refresh before editing")
    if expected != actual:
        raise HTTPException(409, "This record changed; refresh before editing")


async def locked_row(session, model, row_id):
    row = await session.scalar(select(model).where(model.id == row_id).with_for_update()
                               .execution_options(populate_existing=True))
    if row is None:
        raise HTTPException(404, "record not found")
    return row

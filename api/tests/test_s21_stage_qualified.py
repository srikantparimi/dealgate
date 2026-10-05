"""Pipeline-qualified identity and provider-defined deal stage outcomes."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.integrations.hubspot import StubHubSpotClient
from app.models.audit import AuditEvent
from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage
from app.services.hubspot_stage_mirror import StageInfo, StageMap, sync_stage_mirror


def stage(stage_id="shared", *, probability="1", closed="true", label="Outcome", order=0):
    metadata = {"probability": probability}
    if closed is not None:
        metadata["isClosed"] = closed
    return {"id": stage_id, "label": label, "displayOrder": order,
            "metadata": metadata, "archived": False}


def pipeline(pipeline_id="a", stages=None):
    return {"id": pipeline_id, "label": "Pipeline " + pipeline_id, "displayOrder": 0,
            "stages": stages if stages is not None else [stage()], "archived": False}


async def test_resolve_requires_matching_pipeline_when_supplied(session):
    result = await sync_stage_mirror(session, StubHubSpotClient(pipelines=[pipeline()]))
    assert result.resolve("shared", pipeline_id="a").is_closed_won
    assert result.resolve("shared", pipeline_id="b") is None
    assert result.resolve("shared", pipeline_id="") is None
    assert result.resolve("shared").pipeline_id == "a"


def test_stage_only_compatibility_refuses_ambiguous_identity():
    a = StageInfo("shared", "A", "a", 0, True, True, False, Decimal("1"))
    b = StageInfo("shared", "B", "b", 1, True, False, True, Decimal("0"))
    result = StageMap(by_id={}, by_pipeline_stage={("a", "shared"): a, ("b", "shared"): b})
    assert result.resolve("shared") is None
    assert result.resolve("shared", pipeline_id="a") == a
    assert result.resolve("shared", pipeline_id="b") == b


@pytest.mark.parametrize("probability,closed,label,order,won,lost", [
    ("1", "true", "Lost misleading name", 0, True, False),
    ("0", "true", "Won misleading name", 99, False, True),
    ("1", None, "Translated outcome", 0, True, False),
    ("0", None, "Translated outcome", 99, False, True),
    ("0.5", None, "Won label is not a state", 99, False, False),
])
async def test_outcome_uses_probability_not_label_or_order(session, probability, closed, label, order, won, lost):
    result = await sync_stage_mirror(session, StubHubSpotClient(pipelines=[pipeline(stages=[
        stage(probability=probability, closed=closed, label=label, order=order)])]))
    info = result.resolve("shared")
    assert info.is_closed_won is won and info.is_closed_lost is lost
    assert info.is_closed is (won or lost)


@pytest.mark.parametrize("probability,closed", [
    (None, "true"), ("", "false"), ("NaN", "true"), ("Infinity", "true"),
    ("-0.1", "false"), ("1.1", "true"), (True, "true"),
    ("0.5", "true"), ("1", "false"), ("0", "false"), ("0.5", "invalid"),
    ("0.999", "false"),
])
async def test_invalid_classification_fails_before_any_write(session, probability, closed):
    with pytest.raises(ValueError, match="stage_metadata"):
        await sync_stage_mirror(session, StubHubSpotClient(pipelines=[pipeline(stages=[
            stage(probability=probability, closed=closed)])]))
    await session.flush()
    assert list((await session.scalars(select(HubspotPipeline))).all()) == []
    assert list((await session.scalars(select(HubspotStage))).all()) == []


async def test_duplicate_id_in_different_pipelines_fails_closed_before_writes(session):
    with pytest.raises(ValueError, match="stage_identity"):
        await sync_stage_mirror(session, StubHubSpotClient(pipelines=[pipeline("a"), pipeline("b")]))
    await session.flush()
    assert list((await session.scalars(select(HubspotPipeline))).all()) == []


async def test_existing_binding_is_not_reassigned_even_when_original_pipeline_omitted(session):
    await sync_stage_mirror(session, StubHubSpotClient(pipelines=[pipeline("a")]))
    await session.commit()
    with pytest.raises(ValueError, match="stage_identity"):
        await sync_stage_mirror(session, StubHubSpotClient(pipelines=[pipeline("b")]))
    await session.flush()
    row = await session.get(HubspotStage, "shared")
    assert row.pipeline_id == "a"
    assert await session.get(HubspotPipeline, "b") is None


@pytest.mark.parametrize("payload", [None, {}, {"results": None}, {"results": {}},
    {"results": [None]}, {"results": [{"id": "a", "label": "A", "displayOrder": 0}]}])
async def test_malformed_provider_shape_is_not_successful_empty_refresh(session, payload):
    class Provider(StubHubSpotClient):
        async def list_pipelines(self):
            return payload

    with pytest.raises(ValueError, match="pipeline_metadata"):
        await sync_stage_mirror(session, Provider())


async def test_cached_unresolved_classification_is_not_guessed(session):
    session.add(HubspotPipeline(id="a", label="A", display_order=0))
    await session.flush()
    session.add(HubspotStage(id="cached", pipeline_id="a", label="Won", display_order=99,
        is_closed=True, probability=None))
    await session.flush()
    result = await sync_stage_mirror(session, StubHubSpotClient())
    assert result.resolve("cached") is None


async def test_changed_mirror_is_audited_without_duplicate_refresh_events(session):
    provider = StubHubSpotClient(pipelines=[pipeline()])
    await sync_stage_mirror(session, provider)
    await sync_stage_mirror(session, provider)
    events = list((await session.scalars(select(AuditEvent))).all())
    assert len(events) == 2
    provider.pipelines[0]["stages"][0]["metadata"]["probability"] = "0"
    await sync_stage_mirror(session, provider)
    events = list((await session.scalars(select(AuditEvent).order_by(AuditEvent.ts))).all())
    assert len(events) == 3
    assert events[-1].before["probability"] == "1"
    assert events[-1].after["probability"] == "0"
    await session.rollback()
    assert list((await session.scalars(select(HubspotStage))).all()) == []
    assert list((await session.scalars(select(AuditEvent))).all()) == []

"""Lead-run private PostgreSQL proof; authored independently, never self-executing on import."""
import asyncio
import copy
from collections import Counter
from datetime import timedelta
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid

import psycopg
from psycopg import sql
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from s21_coverage_concurrency_pg import ROOT, admin_identity, database_identity, identify, require


class BoundaryProvider:
    """Synthetic provider output, not a live document-extraction accuracy oracle."""
    def __init__(self, price="25000.00"):
        self.price = price

    def values(self):
        return dict(client_legal_name="Synthetic Assessment Client", client_domain="example.test",
            billing_basis_normalized="fixed_price", scope_summary="Four-week assessment workshops and report",
            price=self.price, currency="USD", billing_basis="fixed price",
            term_start="2026-11-01", term_end="2026-11-30", notice_date="2026-10-15",
            deliverables=["Assessment report"], milestones=["Report accepted"],
            acceptance_criteria="Client reviews the assessment report", assumptions=["Client supplies records"],
            exclusions=["Implementation"], signatories=[{"name": "Synthetic Buyer", "title": "Director"}],
            engagement_type_suggested="assessment")

    def extract(self, document):
        from app.integrations.bedrock_sow_extract import ExtractedFields
        require(bool(document.blocks), "Real document parser returned no blocks")
        return ExtractedFields(fields={name: dict(value=value, page_ref=1, status="unconfirmed")
            for name, value in self.values().items()}, model="qa-provider-boundary", prompt_version="qa-v1")


async def observe_parent(observer, *, database, blocked_pid, blocker_pid, label, task):
    # Opportunity SELECTs can exceed pg_stat_activity.query's default text limit.
    # Require the actual relation RowShareLock instead of a truncated FOR UPDATE suffix.
    deadline = asyncio.get_running_loop().time() + 20
    while asyncio.get_running_loop().time() < deadline:
        require(not task.done(), "Contender completed before an exact parent lock wait was observed")
        row = (await observer.execute(text("""
            SELECT a.application_name, a.wait_event_type, a.wait_event, a.query,
                   pg_blocking_pids(a.pid) AS blockers,
                   ARRAY(SELECT locktype FROM pg_locks WHERE pid=a.pid AND NOT granted) AS waiting,
                   EXISTS(SELECT 1 FROM pg_locks WHERE pid=a.pid AND granted
                     AND locktype='relation' AND mode='RowShareLock'
                     AND relation=to_regclass('public.opportunity')) AS parent_row_share
            FROM pg_stat_activity a WHERE a.pid=:pid AND a.datname=:database
        """), dict(pid=blocked_pid, database=database))).mappings().one_or_none()
        await observer.rollback()
        if (row and row["application_name"] == label and row["wait_event_type"] == "Lock"
                and blocker_pid in row["blockers"] and row["waiting"] and row["parent_row_share"]
                and row["query"].lstrip().upper().startswith("SELECT") and "opportunity." in row["query"]):
            evidence = dict(blocked_pid=blocked_pid, blocker_pid=blocker_pid, application_name=label,
                wait_event=row["wait_event"], ungranted_lock_types=list(row["waiting"]),
                parent_relation="public.opportunity", granted_mode="RowShareLock")
            print(json.dumps({"observed_before_release": evidence}), flush=True)
            return evidence
        await asyncio.sleep(0.05)
    raise AssertionError("No exact parent-row wait observed within 20 seconds: " + label)


async def release_after_wait(writer, reader, observer, database, pids, label, operation):
    task = asyncio.create_task(operation())
    try:
        evidence = await observe_parent(observer, database=database, blocked_pid=pids[1],
            blocker_pid=pids[0], label=label, task=task)
        await writer.commit()
        result = await asyncio.wait_for(task, 20)
        return result, evidence
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await reader.rollback()
        await writer.rollback()


async def submit(session, actor, deal_id, version_id, legacy):
    from fastapi import HTTPException
    from app.services.sow_confirmation import submit_confirmation
    from app.services.sow_extract import SowSubmissionIncomplete, submit_sow
    try:
        if legacy:
            await submit_sow(session, actor_id=actor.id, sow_version_id=version_id)
        else:
            await submit_confirmation(session, actor_id=actor.id, opportunity_id=deal_id)
        await session.commit()
        return dict(status=200, detail="unexpected confirmation")
    except SowSubmissionIncomplete as error:
        await session.rollback()
        return dict(status=422, missing=error.missing, detail=str(error))
    except HTTPException as error:
        await session.rollback()
        return dict(status=error.status_code, detail=error.detail)


async def seed(session, label, document):
    from app.auth import AuthUser
    from app.integrations.bedrock_sow_extract import EXTRACTED_FIELDS
    from app.models.opportunity import Opportunity
    from app.models.user import User
    from app.services.sow_confirmation import build_confirmation, scope_blockers
    from app.services.sow_extract import create_sow_version, confirm_field, run_extract
    from app.models.sow import SowVersion

    owner = User(id=uuid.uuid4(), email=label + "@example.test", name="Synthetic Reviewer", groups=["Sales"])
    session.add(owner)
    await session.flush()
    deal = Opportunity(id=uuid.uuid4(), owner_id=owner.id, name=label,
        source="sow_upload", governance_status="SOWDraft")
    session.add(deal)
    await session.flush()
    state = await create_sow_version(session, opportunity_id=deal.id, uploaded_by=owner.id,
        file_s3_key="synthetic/" + label + ".docx", file_hash=hashlib.sha256(document).hexdigest())
    provider = BoundaryProvider()
    require(set(provider.values()) == set(EXTRACTED_FIELDS), "Fixture must supply every legacy field")
    await run_extract(session, sow_version_id=state.id, bedrock=provider, file_bytes=document)
    for field, value in provider.values().items():
        await confirm_field(session, actor_id=owner.id, sow_version_id=state.id, field_name=field, value=value)
    payload = await build_confirmation(session, opportunity_id=deal.id, actor_id=owner.id, auto_create_gm=False)
    require(scope_blockers(payload) == [], "Baseline has an unrelated scope blocker")
    require(payload.engagement.auto_confirm, "Fixture must be deterministically classified")
    version = await session.get(SowVersion, state.id)
    require(all(version.extracted_fields[f]["status"] == "confirmed" for f in EXTRACTED_FIELDS),
        "Baseline legacy fields are not all confirmed")
    require(version.confirmed_at is None, "Baseline is already immutable")
    await session.commit()
    return AuthUser(owner.id, owner.email, owner.name, ("Sales",)), deal.id, version.id


async def verify_unchanged(sessions, *, deal_id, version_ids, expected_fields, replay_version=None):
    from app.audit import verify_chain
    from app.models.audit import AuditEvent
    from app.models.opportunity import Opportunity
    from app.models.sow import SowVersion
    async with sessions() as check:
        deal = await check.get(Opportunity, deal_id)
        require(deal.governance_status == "SOWDraft", "Rejected operation advanced governance")
        versions = [(await check.get(SowVersion, identifier)) for identifier in version_ids]
        stored_ids = set((await check.scalars(select(SowVersion.id)
            .where(SowVersion.sow_id == versions[0].sow_id))).all())
        require(stored_ids == set(version_ids), "Lost or duplicate SOW version rows")
        require(all(v.confirmed_at is None and v.confirmed_by is None for v in versions),
            "Rejected operation froze a SOW version")
        for version, fields in zip(versions, expected_fields, strict=True):
            require(version.extracted_fields == fields, "Rejected operation changed source evidence")
        events = list((await check.scalars(select(AuditEvent).where(
            AuditEvent.entity_id.in_([str(deal_id), *(str(v) for v in version_ids)])))).all())
        actions = Counter(e.action for e in events)
        require(actions["sow.uploaded"] == 1 and actions["sow.extracted"] == 1
            and actions["sow.field_confirmed"] == len(BoundaryProvider().values()),
            "Source setup history was lost, duplicated or changed")
        require(all(actions[name] == 0 for name in ("sow.confirmed", "sow_confirmation.submitted",
            "sow.extraction_conflict_resolved")), "Rejected operation left a success audit")
        if replay_version is not None:
            require(sum(e.action == "sow.extract_failed" and e.entity_id == str(replay_version)
                for e in events) == 1, "Expected exactly one committed conflict-producing replay")
        require(await verify_chain(check), "Audit chain is invalid")
        return dict(version_rows=len(stored_ids), unconfirmed_versions=len(versions),
            confirmation_audits=0, review_audits=0,
            conflict_replay_audits=1 if replay_version else 0)


async def run_cases(sessions, database):
    import httpx
    from fastapi import FastAPI
    from app.auth import current_user
    from app.db import get_session
    from app.models.opportunity import Opportunity
    from app.models.sow import SowVersion
    from app.models.user import User
    from app.routers.sow import router
    from app.services.extraction_conflicts import conflict_items
    from app.services.provenance import wrap
    from app.services.sow_confirmation import build_confirmation, scope_blockers
    from app.services.sow_extract import run_extract

    document = (ROOT / "fixtures/sample_sows/08_assessment_fixed_fee.docx").read_bytes()
    results = []
    for name in ("scope-replay", "legacy-replay", "owner-transfer", "new-version-selection"):
        async with sessions() as setup:
            actor, deal_id, version_id = await seed(setup, name, document)
            if name == "owner-transfer":
                await run_extract(setup, sow_version_id=version_id,
                    bedrock=BoundaryProvider("99900.00"), file_bytes=document)
                replacement = User(id=uuid.uuid4(), email="replacement@example.test", name="New Owner", groups=["Sales"])
                setup.add(replacement)
                await setup.commit()
                replacement_id = replacement.id

        async with sessions() as writer, sessions() as reader, sessions() as observer:
            label = "s21-confirm-" + name
            pids = [await identify(writer, database, label + "-writer"),
                await identify(reader, database, label), await identify(observer, database, label + "-observer")]
            require(len(set(pids)) == 3, "Need three distinct PostgreSQL backends")
            # Strong references deliberately keep pre-lock ORM identities cached.
            cached_parent = await reader.get(Opportunity, deal_id)
            cached_version = await reader.get(SowVersion, version_id)
            require(cached_parent.owner_id == actor.id, "Old owner was not initially authorized")
            original = copy.deepcopy(cached_version.extracted_fields)
            version_ids, expected = [version_id], [original]
            replay_version = None

            if name.endswith("-replay"):
                require(not conflict_items(cached_version)["items"], "Cached version already conflicted")
                await run_extract(writer, sow_version_id=version_id,
                    bedrock=BoundaryProvider("99900.00"), file_bytes=document)
                changed = await writer.get(SowVersion, version_id)
                expected = [copy.deepcopy(changed.extracted_fields)]
                require(list(changed.extracted_fields["metadata"]["reextract_conflicts"]) == ["price"],
                    "Replay must add exactly the price conflict")
                require(cached_version.extracted_fields == original, "Reader did not retain old fields")
                result, wait = await release_after_wait(writer, reader, observer, database, pids, label,
                    lambda: submit(reader, actor, deal_id, version_id, name == "legacy-replay"))
                require(result["status"] == 422, "Submission did not reject the committed conflict: " + str(result))
                if name == "legacy-replay":
                    require(result.get("missing") == ["extraction_conflict:price"], "Unrelated legacy gap")
                else:
                    require("extraction_conflict:price" in result["detail"], "Scope rejected an unrelated gap")
                replay_version = version_id

            elif name == "owner-transfer":
                before = conflict_items(cached_version)["items"]
                require(len(before) == 1 and before[0]["field"] == "price", "Missing reviewed conflict")
                parent = await writer.scalar(select(Opportunity).where(Opportunity.id == deal_id).with_for_update())
                parent.owner_id = replacement_id
                await writer.flush()
                app = FastAPI()
                app.include_router(router)
                app.dependency_overrides[current_user] = lambda: actor
                async def database_session():
                    yield reader
                app.dependency_overrides[get_session] = database_session
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                    async def review():
                        response = await client.post(f"/sow/versions/{version_id}/extraction-conflicts/price",
                            json=dict(review_token=before[0]["review_token"], decision="accept_candidate",
                                reason="Old owner reviewed before ownership transfer"))
                        return dict(status=response.status_code, detail=response.json())
                    result, wait = await release_after_wait(writer, reader, observer, database, pids, label, review)
                require(result["status"] == 403, "Old owner was not refused after transfer: " + str(result))
                async with sessions() as check:
                    require((await check.get(Opportunity, deal_id)).owner_id == replacement_id, "Transfer not committed")
                replay_version = version_id

            else:
                await writer.scalar(select(Opportunity).where(Opportunity.id == deal_id).with_for_update())
                values = BoundaryProvider().values()
                values["currency"] = None
                fields = {key: wrap(value, provenance="extracted", page_ref=1,
                    status="disputed" if value is None else "unconfirmed") for key, value in values.items()}
                # Honest ORM fixture insertion isolates selection, not the upload/version-ordinal API.
                newer = SowVersion(id=uuid.uuid4(), sow_id=cached_version.sow_id, uploaded_by=actor.id,
                    uploaded_at=cached_version.uploaded_at + timedelta(seconds=1), version_no=2,
                    file_s3_key="synthetic/new-version.docx", file_hash=hashlib.sha256(document + b"version2").hexdigest(),
                    extract_status="complete", extracted_fields=fields)
                writer.add(newer)
                await writer.flush()
                pending = await build_confirmation(writer, opportunity_id=deal_id, actor_id=actor.id, auto_create_gm=False)
                require(pending.sow_version.id == newer.id and
                    [gap.field for gap in scope_blockers(pending)] == ["currency"], "New source must have only currency gap")
                result, wait = await release_after_wait(writer, reader, observer, database, pids, label,
                    lambda: submit(reader, actor, deal_id, version_id, False))
                require(result["status"] == 422 and result["detail"] ==
                    "Complete scope: currency: extracted value missing", "Submission did not select the new source: " + str(result))
                version_ids.append(newer.id)
                expected.append(copy.deepcopy(fields))

        counts = await verify_unchanged(sessions, deal_id=deal_id, version_ids=version_ids,
            expected_fields=expected, replay_version=replay_version)
        results.append(dict(name=name, result=result, lock=wait, counts=counts))
    require(len(results) == 4, "Missing race case")
    return results


async def proof(private_url, database):
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from app.db import engine as application_engine
    engine = create_async_engine(private_url, pool_size=4, max_overflow=0,
        connect_args={"server_settings": {"statement_timeout": "30000", "lock_timeout": "30000"}})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as check:
            await identify(check, database, "s21-confirm-schema")
            migrated = list((await check.scalars(text("SELECT version_num FROM alembic_version"))).all())
            config = Config(str(ROOT / "api/alembic.ini"))
            config.set_main_option("script_location", str(ROOT / "api/alembic"))
            heads = ScriptDirectory.from_config(config).get_heads()
            require(len(heads) == 1 and migrated == heads, "Private schema is not the actual migration head")
        return dict(migration_head=migrated[0], scenarios=await run_cases(sessions, database))
    finally:
        await engine.dispose()
        await application_engine.dispose()


def main():
    require(len(sys.argv) == 1, "No arguments or externally supplied target/drop names accepted")
    require(not any(name == "app" or name.startswith("app.") for name in sys.modules),
        "Run as a standalone process before importing application configuration")
    raw = os.environ.get("S21_CONFIRMATION_ADMIN_URL")
    require(raw is not None, "Set the explicit S21_CONFIRMATION_ADMIN_URL administrative DSN")
    admin_url = make_url(raw)
    require((admin_url.drivername, admin_url.username, admin_url.host, admin_url.port, admin_url.database)
        == ("postgresql+psycopg", "s21", "127.0.0.1", 55421, "postgres") and not admin_url.query,
        "Refusing: require psycopg, s21, literal 127.0.0.1:55421/postgres and no URL query options")
    # libpq environment overrides (notably PGHOSTADDR/PGSERVICE/PGOPTIONS) must not redirect the DSN.
    for key in list(os.environ):
        if key.startswith("PG"):
            os.environ.pop(key)
    name = "s21_confirmation_lock_" + uuid.uuid4().hex
    marker = "owned-by-s21-confirmation-proof:" + uuid.uuid4().hex
    private_url = admin_url.set(drivername="postgresql+asyncpg", database=name)
    private_dsn = private_url.render_as_string(hide_password=False)
    os.environ.update(POSTGRES_URL=private_dsn, DATABASE_URL=private_dsn,
        DEALGATE_POSTGRES_URL=private_dsn, PYTHONDONTWRITEBYTECODE="1",
        DEALGATE_ENV="local", DEALGATE_TENANT_ID=name, AWS_EC2_METADATA_DISABLED="true",
        PYTHONPATH=os.pathsep.join((str(ROOT / "api"), str(ROOT))))
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(ROOT / "api"), str(ROOT)]
    print(json.dumps({"private_database": name, "state": "creating"}), flush=True)
    with psycopg.connect(admin_url.set(drivername="postgresql").render_as_string(hide_password=False),
            autocommit=True, connect_timeout=5, application_name="s21-confirmation-admin",
            options="-c statement_timeout=15000 -c lock_timeout=5000") as admin:
        admin_identity(admin)
        created, identity = False, None
        try:
            admin.execute(sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0").format(
                sql.Identifier(name), sql.Identifier("s21")))
            created = True
            admin.execute(sql.SQL("COMMENT ON DATABASE {} IS {}").format(sql.Identifier(name), sql.Literal(marker)))
            identity = database_identity(admin, name)
            require(identity and identity[1:] == ("s21", marker), "Private database ownership verification failed")
            subprocess.run([sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
                cwd=ROOT / "api", env=os.environ.copy(), check=True, timeout=300)
            evidence = asyncio.run(asyncio.wait_for(proof(private_url, name), timeout=240))
            evidence["source_revision"] = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        finally:
            if created:
                admin_identity(admin)
                require(re.fullmatch(r"s21_confirmation_lock_[0-9a-f]{32}", name) is not None
                    and identity is not None and database_identity(admin, name) == identity,
                    f"Cleanup refused: ownership/OID/marker changed; private database left intact: {name}")
                admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
                require(database_identity(admin, name) is None, "Private database cleanup not confirmed")
                print(json.dumps({"private_database": name, "cleanup": "confirmed"}), flush=True)
    print(json.dumps({"result": "PASS", "private_database": name, **evidence}, indent=2), flush=True)


if __name__ == "__main__":
    main()

"""Invited-then-SSO identity: job reads must honor the adopted row.

The upload POST resolves the caller through ``ensure_user``, which adopts
an admin-invited row by email when the token id differs (the designed
invite → first-SSO-login path). The job GET and pick endpoints compared
the raw token id against ``uploader_id`` instead, so the very person who
just uploaded got "not authorised to view this job" while the derive
card polled. Both read paths must resolve the adopted identity the same
way the write path does.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.user import User
from app.services.admin_users import InviteUserPayload, invite_user
from tests.test_sow_upload_router import (  # noqa: F401
    _client,
    _load_pdf,
    _local_env,
    _override_bedrock,
    _seed_client,
    app_with_deps,
)

INVITED_EMAIL = "invited-sso@smartek21.com"


async def _invite(session):
    user = await invite_user(
        session,
        actor_id=None,
        payload=InviteUserPayload(
            email=INVITED_EMAIL, name="Invited Sso", groups=["Sales"]
        ),
    )
    await session.commit()
    return user


@pytest.mark.asyncio
async def test_uploader_with_adopted_row_can_poll_their_job(
    app_with_deps, session  # noqa: F811
):
    invited = await _invite(session)
    await _seed_client(session, "Adopted Identity Client")
    _override_bedrock("Adopted Identity Client")

    # The local auth header derives a uuid5 token id from the email, which
    # deliberately differs from the invited row's random uuid — the same
    # shape as a Cognito sub meeting an admin-invited row.
    async with _client(app_with_deps) as c:
        upload = await c.post(
            "/sows/upload",
            headers={"X-Test-User": INVITED_EMAIL},
            files={"file": ("sow.pdf", _load_pdf("05_tm_capped.pdf"), "application/pdf")},
        )
        assert upload.status_code == 200, upload.text
        job_id = upload.json()["job_id"]

        poll = await c.get(
            f"/sows/jobs/{job_id}",
            headers={"X-Test-User": INVITED_EMAIL},
        )
    assert poll.status_code == 200, poll.text
    assert poll.json()["id"] == job_id

    # One person, one row: the upload adopted the invited row, not a twin.
    rows = (
        await session.scalars(select(User).where(User.email == INVITED_EMAIL))
    ).all()
    assert len(rows) == 1 and rows[0].id == invited.id


@pytest.mark.asyncio
async def test_adopted_uploader_can_resume_needs_pick(
    app_with_deps, session  # noqa: F811
):
    await _invite(session)
    _override_bedrock("Unknown Pick Client Ltd")

    async with _client(app_with_deps) as c:
        upload = await c.post(
            "/sows/upload",
            headers={"X-Test-User": INVITED_EMAIL},
            files={"file": ("sow.pdf", _load_pdf("05_tm_capped.pdf"), "application/pdf")},
        )
        assert upload.status_code == 200, upload.text
        body = upload.json()
        assert body["status"] == "needs_pick"

        pick = await c.post(
            f"/sows/jobs/{body['job_id']}/pick",
            headers={"X-Test-User": INVITED_EMAIL},
            json={"create_new": {"legal_name": "Unknown Pick Client Ltd",
                                 "domain": "unknownpick.example"}},
        )
    assert pick.status_code == 200, pick.text
    assert pick.json()["status"] == "done"

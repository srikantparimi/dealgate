import uuid

from sqlalchemy import select

from app.auth import AuthUser
from app.models.audit import AuditEvent
from app.models.user import User
from app.services.user_identity import display_user_email, display_user_name
from app.services.user_provisioning import ensure_user


def test_display_name_preserves_known_name_and_hides_uuid_placeholders():
    identifier = str(uuid.uuid4())
    assert display_user_name(" Jane Signer ", "jane@example.com") == "Jane Signer"
    assert display_user_name(identifier, "jane@example.com") == "jane@example.com"
    assert display_user_name(identifier, identifier) == "Name unavailable"
    assert display_user_email(identifier) == ""


async def test_provisioning_recovers_placeholder_profile_and_audits(session):
    identifier = uuid.uuid4()
    user = User(id=identifier, name=str(identifier), email=str(identifier), groups=["Finance"])
    session.add(user)
    await session.commit()
    actor = AuthUser(id=identifier, name="Jane Signer", email="jane@example.com", groups=("Finance",))
    resolved = await ensure_user(session, actor)
    assert resolved.name == "Jane Signer"
    assert resolved.email == "jane@example.com"
    event = (await session.execute(select(AuditEvent).where(AuditEvent.action == "user.profile_synced"))).scalar_one()
    assert event.after["name"] == "Jane Signer"


async def test_provisioning_does_not_replace_known_name_with_uuid(session):
    identifier = uuid.uuid4()
    user = User(id=identifier, name="Jane Signer", email="jane@example.com", groups=["Finance"])
    session.add(user)
    await session.commit()
    actor = AuthUser(id=identifier, name=str(identifier), email=str(identifier), groups=("Finance",))
    resolved = await ensure_user(session, actor)
    assert resolved.name == "Jane Signer"
    assert resolved.email == "jane@example.com"

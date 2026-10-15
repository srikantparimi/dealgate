from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


class User(Base):
    __tablename__ = "user"
    __table_args__ = (
        CheckConstraint(
            "hubspot_owner_link IN ('email','admin')", name="ck_user_hubspot_owner_link"
        ),
        # S23-PL2 B4: one DealGate user per HubSpot owner.
        Index(
            "ux_user_hubspot_owner",
            "hubspot_owner_id",
            unique=True,
            postgresql_where=text("hubspot_owner_id IS NOT NULL"),
            sqlite_where=text("hubspot_owner_id IS NOT NULL"),
        ),
        # S23-PL2: one Cognito login per user row.
        Index(
            "ux_user_cognito_sub",
            "cognito_sub",
            unique=True,
            postgresql_where=text("cognito_sub IS NOT NULL"),
            sqlite_where=text("cognito_sub IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # groups is a JSON array of role names (e.g. ["Sales", "SystemAdmin"]).
    groups: Mapped[list[str]] = mapped_column(JsonB, nullable=False, default=list)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # S23-PL2 B4: the HubSpot owner this user is. ``hubspot_owner_link`` says
    # how it was decided: ``email`` (automatic, exact email match) or
    # ``admin`` (override; with a NULL id it means "deliberately no owner" and
    # is never re-linked automatically). NULL = not decided yet.
    hubspot_owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hubspot_owner_link: Mapped[str | None] = mapped_column(String(8), nullable=True)
    hubspot_owner_linked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # S23-PL2: the Cognito ``sub`` of the login that owns this row, stored when
    # the row's id is not that sub (invited or HubSpot-created users), so a
    # read can find the row from an access token that carries no email.
    cognito_sub: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

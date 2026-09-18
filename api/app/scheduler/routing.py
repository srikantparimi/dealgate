"""Role → function-head resolution for escalation notifications.

The scheduler escalates overdue tasks to the head of the owner's function
(Sales, Legal, Finance, HR, Delivery). We keep the map in env vars so the
integrator wires real email addresses in staging/prod without a code deploy;
missing values gracefully degrade to the Sales leader (the intake fallback
already in production).
"""

from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

# Env vars — the integrator sets these in the scheduler task definition.
SALES_LEADER_EMAIL_ENV = "SALES_LEADER_EMAIL"
LEGAL_LEADER_EMAIL_ENV = "LEGAL_LEADER_EMAIL"
FINANCE_LEADER_EMAIL_ENV = "FINANCE_LEADER_EMAIL"
HR_LEADER_EMAIL_ENV = "HR_LEADER_EMAIL"
DELIVERY_LEADER_EMAIL_ENV = "DELIVERY_LEADER_EMAIL"


# Role groups a user might carry → the env var whose value is the head's email.
# Kept in one place so the scheduler and any future notifier stay aligned.
_ROLE_TO_HEAD_ENV: dict[str, str] = {
    "Sales": SALES_LEADER_EMAIL_ENV,
    "SalesLeader": SALES_LEADER_EMAIL_ENV,
    "Legal": LEGAL_LEADER_EMAIL_ENV,
    "LegalLeader": LEGAL_LEADER_EMAIL_ENV,
    "Finance": FINANCE_LEADER_EMAIL_ENV,
    "FinanceLeader": FINANCE_LEADER_EMAIL_ENV,
    "HR": HR_LEADER_EMAIL_ENV,
    "Delivery": DELIVERY_LEADER_EMAIL_ENV,
}


def _lookup_env_email(role_or_group: str) -> str | None:
    env_name = _ROLE_TO_HEAD_ENV.get(role_or_group)
    if env_name is None:
        return None
    value = (os.environ.get(env_name) or "").strip()
    return value or None


async def _find_or_create_user(
    session: AsyncSession, email: str, name: str
) -> User:
    row = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = User(email=email, name=name or email, groups=[])
    session.add(row)
    await session.flush()
    return row


async def resolve_head_for_role(
    session: AsyncSession, groups: list[str] | None
) -> User | None:
    """Return the User row for the head of the first matching function.

    Groups are searched in order; the caller sends the owner's `groups`
    list so the primary role wins. Missing env config yields ``None`` —
    the scheduler treats that as "no escalation target", logs, and skips
    the notification instead of crashing.
    """

    for group in groups or []:
        email = _lookup_env_email(group)
        if email:
            # Function head naming is a nicety, not a correctness concern.
            return await _find_or_create_user(session, email, f"{group} Head")

    # Final fallback: the Sales leader that the intake worker already relies on.
    sales_email = (os.environ.get(SALES_LEADER_EMAIL_ENV) or "").strip()
    if sales_email:
        return await _find_or_create_user(session, sales_email, "Sales Leader")
    return None


__all__ = [
    "DELIVERY_LEADER_EMAIL_ENV",
    "FINANCE_LEADER_EMAIL_ENV",
    "HR_LEADER_EMAIL_ENV",
    "LEGAL_LEADER_EMAIL_ENV",
    "SALES_LEADER_EMAIL_ENV",
    "resolve_head_for_role",
]

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog
from fastapi import Depends, Header, HTTPException, status

from app.auth.cognito import (
    CognitoAuthError,
    CognitoConfigError,
    verify_cognito_jwt,
)

log = structlog.get_logger("auth")


@dataclass(frozen=True)
class AuthUser:
    """The authenticated principal for a request.

    `id` is deterministic per email so tests can round-trip a fake user without
    hitting the DB. Real users get their DB row's UUID once Cognito lands.
    """

    id: uuid.UUID
    email: str
    name: str
    groups: tuple[str, ...] = field(default_factory=tuple)

    def has_any_role(self, roles: tuple[str, ...]) -> bool:
        return any(r in self.groups for r in roles)


def _fake_user_from_email(email: str, groups: tuple[str, ...]) -> AuthUser:
    # UUIDv5 keeps the id stable across processes for the same email.
    uid = uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")
    return AuthUser(id=uid, email=email, name=email.split("@")[0], groups=groups)


def _parse_test_groups() -> tuple[str, ...]:
    raw = os.environ.get("DEALGATE_TEST_GROUPS", "")
    return tuple(g.strip() for g in raw.split(",") if g.strip())


def _user_from_claims(claims: dict[str, Any]) -> AuthUser:
    """Map verified Cognito claims to :class:`AuthUser`.

    - ID tokens carry ``email``/``name``; access tokens do not — fall back to
      ``username`` / ``cognito:username`` so the API stays usable either way.
    - ``cognito:groups`` maps 1:1 to app roles (Marketing, Sales, ..., SystemAdmin).
    """

    sub = claims.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="token missing sub"
        )
    email = (
        claims.get("email")
        or claims.get("username")
        or claims.get("cognito:username")
    )
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="token missing email/username"
        )
    try:
        uid = uuid.UUID(str(sub))
    except ValueError:
        uid = uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:cognito:{sub}")
    groups = tuple(claims.get("cognito:groups") or [])
    name = claims.get("name") or email
    return AuthUser(id=uid, email=email, name=name, groups=groups)


async def current_user(
    authorization: str | None = Header(default=None),
    x_test_user: str | None = Header(default=None, alias="X-Test-User"),
) -> AuthUser:
    """Resolve the caller. Raises 401 if unauthenticated."""

    env = os.environ.get("DEALGATE_ENV", "local")
    if env == "local" and x_test_user:
        return _fake_user_from_email(x_test_user, _parse_test_groups())

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated"
        )
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated"
        )

    try:
        claims = verify_cognito_jwt(token)
    except CognitoConfigError as exc:
        log.error("cognito_config_missing", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="auth not configured"
        ) from exc
    except CognitoAuthError as exc:
        log.info("cognito_reject", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token"
        ) from exc

    return _user_from_claims(claims)


def require_role(*roles: str):
    """Dependency factory: 403 unless the caller is in one of `roles`."""

    allowed = tuple(roles)

    async def _dep(user: AuthUser = Depends(current_user)) -> AuthUser:
        granted = user.has_any_role(allowed)
        log.info(
            "role_check",
            user=user.email,
            required=list(allowed),
            user_groups=list(user.groups),
            granted=granted,
        )
        if not granted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role"
            )
        return user

    return _dep

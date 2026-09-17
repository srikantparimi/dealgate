from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field

import jwt
import structlog
from fastapi import Depends, Header, HTTPException, status

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


def _decode_jwt(token: str) -> AuthUser:
    # Signature verification is wired in when Cognito JWKS is available.
    # Until then we still enforce structure so route contracts don't drift.
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError as exc:  # pragma: no cover - jwt errors are opaque
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token"
        ) from exc
    email = payload.get("email")
    sub = payload.get("sub")
    if not email or not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="token missing sub/email"
        )
    try:
        uid = uuid.UUID(sub)
    except ValueError:
        uid = uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:jwt:{sub}")
    groups = tuple(payload.get("cognito:groups") or [])
    return AuthUser(id=uid, email=email, name=payload.get("name") or email, groups=groups)


async def current_user(
    authorization: str | None = Header(default=None),
    x_test_user: str | None = Header(default=None, alias="X-Test-User"),
) -> AuthUser:
    """Resolve the caller. Raises 401 if unauthenticated."""

    env = os.environ.get("DEALGATE_ENV", "local")
    if env == "local" and x_test_user:
        return _fake_user_from_email(x_test_user, _parse_test_groups())

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        return _decode_jwt(token)

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")


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

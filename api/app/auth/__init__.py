"""Auth dependencies: `current_user` + `require_role`.

Real Cognito integration lands in Sprint 3+. Sprint 1 supports two modes:

- `DEALGATE_ENV=local`: read `X-Test-User: <email>` and `DEALGATE_TEST_GROUPS`
  (comma-separated) — used by unit and dev sessions only.
- Any other env: verify the `Authorization: Bearer <jwt>` header with PyJWT.
  Signature verification is stubbed off until Cognito JWKS wiring in a later
  story; the payload shape (`sub`, `email`, `name`, `cognito:groups`) is the
  final one.
"""

from app.auth.deps import (
    AuthUser,
    current_user,
    require_role,
)

__all__ = ["AuthUser", "current_user", "require_role"]

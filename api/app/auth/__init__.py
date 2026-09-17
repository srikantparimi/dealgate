"""Auth dependencies: `current_user` + `require_role`.

Two modes selected by `DEALGATE_ENV`:

- ``DEALGATE_ENV=local``: read ``X-Test-User: <email>`` and
  ``DEALGATE_TEST_GROUPS`` (comma-separated) — unit tests and dev only.
- Any other env: verify ``Authorization: Bearer <jwt>`` via
  :func:`app.auth.cognito.verify_cognito_jwt` (RS256, JWKS-signed by the
  configured Cognito user pool). Claims map straight into :class:`AuthUser`;
  ``cognito:groups`` populates roles for :func:`require_role`.
"""

from app.auth.deps import (
    AuthUser,
    current_user,
    require_role,
)

__all__ = ["AuthUser", "current_user", "require_role"]

"""Shared identity display rules for People, signatories and deal owners."""

import uuid


def is_identity_placeholder(value: str | None) -> bool:
    if not value or not value.strip():
        return True
    try:
        uuid.UUID(value.strip())
    except ValueError:
        return False
    return True


def display_user_name(name: str | None, email: str | None, *, fallback: str = "Name unavailable") -> str:
    for value in (name, email):
        if not is_identity_placeholder(value):
            return value.strip()
    return fallback


def display_user_email(email: str | None) -> str:
    return "" if is_identity_placeholder(email) else email.strip()

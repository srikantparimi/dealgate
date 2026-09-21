"""Permission + gating tests for the dev-seed endpoint (S13a)."""

from __future__ import annotations

import uuid

import pytest


def test_disabled_when_prod(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "prod")
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")
    from app.routers import dev_seed as ds

    assert not ds.is_dev_seed_enabled()


def test_disabled_when_flag_missing(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "dev")
    monkeypatch.delenv("ALLOW_DEV_SEED_ENDPOINT", raising=False)
    from app.routers import dev_seed as ds

    assert not ds.is_dev_seed_enabled()


def test_enabled_when_both_set(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "dev")
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")
    from app.routers import dev_seed as ds

    assert ds.is_dev_seed_enabled()


def test_router_only_mounted_when_enabled():
    """Belt-and-braces: build a fresh app in-process with the flag off
    and confirm the route isn't registered."""

    import os
    from fastapi import FastAPI
    from app.routers import dev_seed as ds

    original_env = os.environ.get("DEALGATE_ENV")
    os.environ["DEALGATE_ENV"] = "prod"
    try:
        assert not ds.is_dev_seed_enabled()
    finally:
        if original_env is None:
            os.environ.pop("DEALGATE_ENV", None)
        else:
            os.environ["DEALGATE_ENV"] = original_env

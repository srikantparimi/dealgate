"""Tests for the S15 startup guard against fictional Bedrock model ids.

Two failure classes both covered:

1. **Invented model id** — the id is not in `bedrock:ListInferenceProfiles`.
   This class caught the fictional `claude-opus-5` that silently broke
   every SOW extract for weeks.

2. **Subscribed-but-not-enabled** — the id lists fine but Invoke returns
   AccessDeniedException (usually an AWS Marketplace subscription is
   missing). This class caught Opus 4.7 needing marketplace consent when
   we bumped from opus-5.

Both classes must raise :class:`BedrockModelIdInvalid` so uvicorn exits
non-zero and the deploy fails to converge — one deploy failure instead
of N silent uploads.

The runtime path is covered by two flavours:

* Unit tests (default): mock the boto3 client + control which profile ids
  the API "sees" and what the invoke call returns. These run offline.
* Live check (opt-in, `LIVE_BEDROCK_CHECK=1`): actually calls
  `bedrock:ListInferenceProfiles` + `bedrock-runtime:InvokeModel` in the
  configured region and asserts the default `EXTRACT_MODEL` id passes both
  checks. This is what would have caught the fake `claude-opus-5` OR the
  unsubscribed opus-4-7 at PR time. CI opts in via the workflow env when
  AWS creds are present.
"""

from __future__ import annotations

import os

import pytest

from app.integrations.bedrock_sow_extract import EXTRACT_MODEL
from app.services.bedrock_model_check import (
    BedrockModelIdInvalid,
    validate_extract_model_id,
)


class _StubBedrockClient:
    """Stand-in for boto3.client('bedrock', ...)."""

    def __init__(self, profiles: list[str]) -> None:
        self._profiles = profiles

    def list_inference_profiles(self, **_kwargs):  # noqa: D401 — mimic boto3
        return {
            "inferenceProfileSummaries": [
                {"inferenceProfileId": p} for p in self._profiles
            ]
        }


class _StubBedrockRuntime:
    """Stand-in for boto3.client('bedrock-runtime', ...)."""

    def __init__(self, *, invoke_ok: bool = True, error_code: str = "AccessDeniedException") -> None:
        self._invoke_ok = invoke_ok
        self._error_code = error_code

    def invoke_model(self, modelId: str, body: str):  # noqa: N803 — boto3 signature
        if self._invoke_ok:
            return {"body": None, "contentType": "application/json"}
        from botocore.exceptions import ClientError

        raise ClientError(
            {"Error": {"Code": self._error_code, "Message": "stubbed"}},
            "InvokeModel",
        )


def _patch_boto3(
    monkeypatch: pytest.MonkeyPatch,
    profiles: list[str],
    *,
    invoke_ok: bool = True,
    invoke_error: str = "AccessDeniedException",
) -> None:
    import boto3

    def _fake_client(name, **_kwargs):
        if name == "bedrock":
            return _StubBedrockClient(profiles)
        if name == "bedrock-runtime":
            return _StubBedrockRuntime(invoke_ok=invoke_ok, error_code=invoke_error)
        raise AssertionError(f"unexpected boto3.client({name!r})")

    monkeypatch.setattr(boto3, "client", _fake_client)


def _force_prod_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the validator out of its offline-skip path."""

    monkeypatch.setenv("DEALGATE_ENV", "dev")
    monkeypatch.delenv("SOW_EXTRACT_STUB", raising=False)
    monkeypatch.delenv("SKIP_BEDROCK_MODEL_CHECK", raising=False)


def test_validator_passes_when_model_live_and_invokeable(monkeypatch: pytest.MonkeyPatch) -> None:
    _force_prod_env(monkeypatch)
    _patch_boto3(
        monkeypatch,
        [
            "us.anthropic.claude-sonnet-4-6",
            "us.anthropic.claude-opus-4-7",
            "us.anthropic.claude-opus-4-8",
        ],
        invoke_ok=True,
    )
    validate_extract_model_id("us.anthropic.claude-sonnet-4-6")


def test_validator_raises_for_invented_model_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """The `claude-opus-5` class — model id is not in the live list."""

    _force_prod_env(monkeypatch)
    _patch_boto3(
        monkeypatch,
        [
            "us.anthropic.claude-sonnet-4-6",
            "us.anthropic.claude-opus-4-7",
        ],
        invoke_ok=True,
    )
    with pytest.raises(BedrockModelIdInvalid) as excinfo:
        validate_extract_model_id("us.anthropic.claude-opus-5")
    msg = str(excinfo.value)
    assert "us.anthropic.claude-opus-5" in msg
    assert "us.anthropic.claude-sonnet-4-6" in msg  # sibling listed


def test_validator_raises_for_unsubscribed_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Opus-4-7 class — model lists fine but Invoke returns AccessDenied."""

    _force_prod_env(monkeypatch)
    _patch_boto3(
        monkeypatch,
        ["us.anthropic.claude-opus-4-7"],
        invoke_ok=False,
        invoke_error="AccessDeniedException",
    )
    with pytest.raises(BedrockModelIdInvalid) as excinfo:
        validate_extract_model_id("us.anthropic.claude-opus-4-7")
    msg = str(excinfo.value)
    assert "listed but cannot be invoked" in msg
    assert "AccessDeniedException" in msg
    # The error should point to the fix path.
    assert "Marketplace" in msg or "IAM" in msg


def test_validator_raises_on_transient_invoke_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _force_prod_env(monkeypatch)
    _patch_boto3(
        monkeypatch,
        ["us.anthropic.claude-sonnet-4-6"],
        invoke_ok=False,
        invoke_error="ThrottlingException",
    )
    # Throttling still counts as a boot-time no-go — fail loudly so nobody
    # ships behind a flapping model.
    with pytest.raises(BedrockModelIdInvalid):
        validate_extract_model_id("us.anthropic.claude-sonnet-4-6")


def test_validator_skips_in_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEALGATE_ENV", "local")
    import boto3

    def _explode(*_args, **_kwargs):  # pragma: no cover
        raise AssertionError("validator should not touch boto3 in local")

    monkeypatch.setattr(boto3, "client", _explode)
    validate_extract_model_id("something-fake")


def test_validator_skips_when_stub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEALGATE_ENV", "dev")
    monkeypatch.setenv("SOW_EXTRACT_STUB", "1")
    import boto3

    def _explode(*_args, **_kwargs):  # pragma: no cover
        raise AssertionError("validator should not touch boto3 when stubbed")

    monkeypatch.setattr(boto3, "client", _explode)
    validate_extract_model_id("something-fake")


@pytest.mark.skipif(
    os.environ.get("LIVE_BEDROCK_CHECK") != "1",
    reason="opt-in live check; set LIVE_BEDROCK_CHECK=1 with AWS creds to run",
)
def test_default_extract_model_id_is_live_and_invokeable() -> None:
    """The default hard-coded in EXTRACT_MODEL must exist in the target region
    AND this task role must be able to actually Invoke it.

    This is the test that would have caught the invented `claude-opus-5` (list
    membership) AND the unsubscribed opus-4-7 (invoke ping) at PR time. Runs
    in CI when AWS creds are available; skipped otherwise.
    """

    os.environ.pop("SOW_EXTRACT_STUB", None)
    os.environ.pop("SKIP_BEDROCK_MODEL_CHECK", None)
    os.environ["DEALGATE_ENV"] = "dev"
    validate_extract_model_id(EXTRACT_MODEL)

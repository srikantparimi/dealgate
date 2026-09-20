"""Tests for the real Bedrock SOW extractor (S10-04).

Before this story ``BedrockSowExtract.extract`` returned
``ManualRequired("bedrock caller not yet implemented")`` unconditionally, and
``get_bedrock_sow()`` returned that class in production — so every deployed
upload derived nothing. Nothing failed loudly; the flow just dead-ended.

These tests pin the wire contract and every failure mode, with no AWS calls.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest
from botocore.exceptions import ClientError

from app.integrations.bedrock_sow_extract import (
    EXTRACT_PROMPT_VERSION,
    EXTRACTED_FIELDS,
    BedrockSowExtract,
    ExtractedFields,
    ManualRequired,
    StubBedrock,
    get_bedrock_sow,
)
from app.services.document_text import extract_document_text, text_document_from_string

FIXTURES = pathlib.Path(__file__).resolve().parents[2] / "fixtures" / "sample_sows"
DOCX = FIXTURES / "08_assessment_fixed_fee.docx"


def _good_fields() -> dict[str, Any]:
    return {
        name: {"value": f"v-{name}", "page_ref": 3, "status": "unconfirmed"}
        for name in EXTRACTED_FIELDS
    }


class _FakeBody:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._raw = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._raw


class _FakeRuntime:
    """Stands in for a bedrock-runtime client; records the request."""

    def __init__(self, payload: dict[str, Any] | None = None, error: Exception | None = None):
        self._payload = payload
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def invoke_model(self, *, modelId: str, body: str) -> dict[str, Any]:  # noqa: N803
        self.calls.append({"modelId": modelId, "body": json.loads(body)})
        if self._error is not None:
            raise self._error
        return {"body": _FakeBody(self._payload or {})}


def _tool_use_response(fields: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "tool_use",
                "name": "emit_sow_extract",
                "input": {"fields": fields},
            }
        ],
        "stop_reason": "tool_use",
    }


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "InvokeModel")


@pytest.fixture
def doc():
    return extract_document_text(DOCX.read_bytes())


def test_happy_path_returns_validated_fields(doc) -> None:
    runtime = _FakeRuntime(_tool_use_response(_good_fields()))
    result = BedrockSowExtract(client=runtime).extract(doc)

    assert isinstance(result, ExtractedFields)
    assert set(result.fields) == set(EXTRACTED_FIELDS)
    assert result.prompt_version == EXTRACT_PROMPT_VERSION


def test_request_uses_forced_tool_use_and_the_configured_model(doc, monkeypatch) -> None:
    """Schema enforcement is by forced tool use.

    This Bedrock deployment rejects `output_config.format` and `strict: true`
    with a ValidationException, so `tool_choice` is the mechanism. Pin it.
    """

    monkeypatch.setenv("SOW_EXTRACT_MODEL_ID", "us.anthropic.claude-sonnet-5")
    runtime = _FakeRuntime(_tool_use_response(_good_fields()))
    BedrockSowExtract(client=runtime).extract(doc)

    sent = runtime.calls[0]
    assert sent["modelId"] == "us.anthropic.claude-sonnet-5"
    body = sent["body"]
    assert body["anthropic_version"] == "bedrock-2023-05-31"
    assert body["tool_choice"] == {"type": "tool", "name": "emit_sow_extract"}
    assert body["tools"][0]["name"] == "emit_sow_extract"
    assert "output_config" not in body
    assert "strict" not in body["tools"][0]
    # The document reaches the model as numbered blocks, not as raw bytes.
    assert "[[1]] STATEMENT OF WORK" in body["messages"][0]["content"][0]["text"]


def test_model_id_defaults_to_an_inference_profile(doc) -> None:
    """A bare foundation-model id is rejected by Bedrock for these models:
    "Invocation of model ID ... with on-demand throughput isn't supported."
    """

    runtime = _FakeRuntime(_tool_use_response(_good_fields()))
    BedrockSowExtract(client=runtime).extract(doc)
    assert runtime.calls[0]["modelId"].startswith("us.anthropic.")


@pytest.mark.parametrize(
    ("code", "fragment"),
    [
        ("AccessDeniedException", "model access not enabled"),
        ("ValidationException", "rejected the request"),
        ("ThrottlingException", "temporarily unavailable"),
        ("ServiceUnavailableException", "temporarily unavailable"),
        ("SomethingElse", "bedrock error"),
    ],
)
def test_aws_failures_degrade_to_manual_required(doc, code, fragment) -> None:
    """Never a 500, never a fabricated payload — always a manual form."""

    runtime = _FakeRuntime(error=_client_error(code))
    result = BedrockSowExtract(client=runtime).extract(doc)
    assert isinstance(result, ManualRequired)
    assert fragment in result.reason


def test_schema_violation_is_not_persisted(doc) -> None:
    """A hallucinated or malformed payload must not reach the confirm screen."""

    bad = _good_fields()
    bad["price"] = {"value": "1", "page_ref": 0, "status": "unconfirmed"}  # page_ref < 1
    runtime = _FakeRuntime(_tool_use_response(bad))
    result = BedrockSowExtract(client=runtime).extract(doc)
    assert isinstance(result, ManualRequired)
    assert "validation" in result.reason


def test_unknown_field_is_rejected(doc) -> None:
    bad = _good_fields()
    bad["totally_invented"] = {"value": "x", "page_ref": 1, "status": "unconfirmed"}
    runtime = _FakeRuntime(_tool_use_response(bad))
    assert isinstance(BedrockSowExtract(client=runtime).extract(doc), ManualRequired)


def test_missing_field_is_rejected(doc) -> None:
    bad = _good_fields()
    del bad["price"]
    runtime = _FakeRuntime(_tool_use_response(bad))
    assert isinstance(BedrockSowExtract(client=runtime).extract(doc), ManualRequired)


def test_response_without_a_tool_call_is_manual_required(doc) -> None:
    runtime = _FakeRuntime({"content": [{"type": "text", "text": "I cannot"}], "stop_reason": "end_turn"})
    result = BedrockSowExtract(client=runtime).extract(doc)
    assert isinstance(result, ManualRequired)
    assert "no extract" in result.reason


def test_empty_document_never_calls_the_model() -> None:
    """Spending a model call on an empty document would be pure waste, and a
    reply to it could only be invented."""

    runtime = _FakeRuntime(_tool_use_response(_good_fields()))
    result = BedrockSowExtract(client=runtime).extract(text_document_from_string(""))
    assert isinstance(result, ManualRequired)
    assert runtime.calls == []


def test_client_identity_fields_are_part_of_the_contract() -> None:
    """`_client_signals` reads these to pre-fill the client picker; without
    them a SOW with no signature block opens a blank form (rule 10)."""

    assert "client_legal_name" in EXTRACTED_FIELDS
    assert "client_domain" in EXTRACTED_FIELDS


def test_stub_toggle_is_honoured(monkeypatch) -> None:
    """SOW_EXTRACT_STUB was set by e2e.yml but read by nothing."""

    monkeypatch.delenv("DEALGATE_ENV", raising=False)
    monkeypatch.setenv("SOW_EXTRACT_STUB", "1")
    assert isinstance(get_bedrock_sow(), StubBedrock)

    monkeypatch.delenv("SOW_EXTRACT_STUB", raising=False)
    monkeypatch.setenv("DEALGATE_ENV", "production")
    caller = get_bedrock_sow()
    assert isinstance(caller, BedrockSowExtract)
    assert not isinstance(caller, StubBedrock)

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
    fields = {
        name: {"value": f"v-{name}", "page_ref": 3, "status": "unconfirmed"}
        for name in EXTRACTED_FIELDS
    }
    fields["signatories"]["value"] = [{"name": "Alex Example", "role": "Client"}]
    return fields


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
    separate = {"direct_costs", "billing_basis_normalized", "engagement_type_suggested", "signatories"}
    tool_input = {"fields": fields}
    if isinstance(fields, dict):
        tool_input = {"fields": [dict(name=name, **entry) for name, entry in fields.items() if name not in separate],
                      **{name: entry for name, entry in fields.items() if name in separate}}
    return {
        "content": [
            {
                "type": "tool_use",
                "name": "emit_sow_extract",
                "input": tool_input,
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
    """Forced selection plus strict schema; local validation remains mandatory."""

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
    assert body["tools"][0]["strict"] is True
    # The document reaches the model as numbered blocks, not as raw bytes.
    assert "[[1]] STATEMENT OF WORK" in body["messages"][0]["content"][0]["text"]


def test_strict_wire_schema_is_closed_and_uses_supported_constraints(doc):
    runtime = _FakeRuntime(_tool_use_response(_good_fields()))
    BedrockSowExtract(client=runtime).extract(doc)
    schema = runtime.calls[0]["body"]["tools"][0]["input_schema"]

    def check(node):
        if isinstance(node, dict):
            assert not {"minimum", "maximum", "minLength", "maxLength"} & node.keys()
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for value in node.values():
                check(value)
        elif isinstance(node, list):
            for value in node:
                check(value)

    check(schema)
    assert schema["properties"]["fields"]["type"] == "array"
    assert set(schema["properties"]["fields"]["items"]["properties"]["name"]["enum"]) | {
        "billing_basis_normalized", "engagement_type_suggested", "signatories",
    } == set(EXTRACTED_FIELDS)


def test_signatories_have_separate_identity_and_role_in_provider_contract(doc):
    fields = _good_fields()
    people = [{"name": "Alex Example", "role": "Client"},
              {"name": "Casey Example", "role": "SmarTek21"}]
    fields["signatories"]["value"] = people
    runtime = _FakeRuntime(_tool_use_response(fields))
    result = BedrockSowExtract(client=runtime).extract(doc)
    assert isinstance(result, ExtractedFields)
    assert result.fields["signatories"]["value"] == people
    body = runtime.calls[0]["body"]
    value = body["tools"][0]["input_schema"]["properties"]["signatories"]["properties"]["value"]
    assert value["type"] == ["array", "null"]
    assert value["items"]["properties"]["name"]["type"] == "string"
    assert set(value["items"]["required"]) == {"name", "role"}
    assert "Do not append" in body["system"]


@pytest.mark.parametrize("value", ["Alex Example", ["Alex Example (Client)"],
    [{"name": "", "role": "Client"}], [{"name": 1, "role": None}],
    [{"name": "Alex Example", "role": [], "extra": True}]])
def test_real_provider_rejects_untyped_or_invalid_signatory_identity(doc, value):
    fields = _good_fields()
    fields["signatories"]["value"] = value
    runtime = _FakeRuntime(_tool_use_response(fields))
    assert isinstance(BedrockSowExtract(client=runtime).extract(doc), ManualRequired)
    assert len(runtime.calls) == 1


@pytest.mark.parametrize("entry", [{"page_ref": 1},
    {"value": [{"name": "Alex Example", "role": None}], "page_ref": 1},
    {"value": [], "page_ref": 1, "status": []},
    {"value": [], "page_ref": 1, "status": "unconfirmed", "extra": True}])
def test_real_provider_rejects_malformed_signatory_wrapper(doc, entry):
    fields = _good_fields()
    fields["signatories"] = entry
    runtime = _FakeRuntime(_tool_use_response(fields))
    assert isinstance(BedrockSowExtract(client=runtime).extract(doc), ManualRequired)
    assert len(runtime.calls) == 1


def test_duplicate_named_entries_are_rejected(doc):
    payload = _tool_use_response(_good_fields())
    payload["content"][0]["input"]["fields"].append(dict(name="price", value="1", page_ref=1, status="unconfirmed"))
    assert isinstance(BedrockSowExtract(client=_FakeRuntime(payload)).extract(doc), ManualRequired)


@pytest.mark.parametrize("payload", [[], None, {"content": None}, {"content": [None]},
    {"content": [{"type": "tool_use", "name": "emit_sow_extract", "input": []}]}])
def test_malformed_provider_envelope_never_crashes_or_retries(doc, payload):
    runtime = _FakeRuntime(payload)
    assert isinstance(BedrockSowExtract(client=runtime).extract(doc), ManualRequired)
    assert len(runtime.calls) == 1


@pytest.mark.parametrize("fields", ["{}", [], None, 1])
def test_malformed_fields_are_not_coerced_or_retried(doc, fields):
    runtime = _FakeRuntime(_tool_use_response(fields))
    assert isinstance(BedrockSowExtract(client=runtime).extract(doc), ManualRequired)
    assert len(runtime.calls) == 1


def test_boolean_page_reference_is_not_an_integer_locator(doc):
    fields = _good_fields()
    fields["price"]["page_ref"] = True
    runtime = _FakeRuntime(_tool_use_response(fields))
    assert isinstance(BedrockSowExtract(client=runtime).extract(doc), ManualRequired)


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

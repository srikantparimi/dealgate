"""S15: fail-loudly startup check for SOW_EXTRACT_MODEL_ID.

Two failure classes both silently broke SOW extract in Sep 2026:

1. **Invented model id** — `us.anthropic.claude-opus-5` was hand-set on the
   deployed task-def; Bedrock returns ValidationException on invoke, the
   pipeline squashed it into an empty `manual_required` row, and nothing
   surfaced to the UI. Caught by the list-membership check below.

2. **Subscribed-but-not-enabled model** — Opus 4.7 is a live inference
   profile but requires an AWS Marketplace subscription
   (aws-marketplace:Subscribe) that had not been completed. Bedrock
   returns AccessDeniedException on invoke, same silent squash downstream.
   Caught by the invoke-ping below.

Both checks run at FastAPI startup. Either failure raises
:class:`BedrockModelIdInvalid`, uvicorn exits non-zero, ECS marks the task
unhealthy, and the deploy fails to converge — one deploy failure instead
of N silent uploads.

The invoke ping is a 5-token "ping" against the configured profile, ~$0.00003
per boot and ~500 ms wall time. The cost of a bad model reaching production
is measured in days of user confusion; this is the right layer.

Skipped in local/test or when `SOW_EXTRACT_STUB=1` so unit tests stay offline.
"""

from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("dealgate.bedrock_model_check")


class BedrockModelIdInvalid(RuntimeError):
    """The configured SOW_EXTRACT_MODEL_ID is not a live Bedrock profile."""


def _should_skip() -> bool:
    if os.environ.get("SOW_EXTRACT_STUB") == "1":
        return True
    if os.environ.get("DEALGATE_ENV", "local") in ("local", "test"):
        return True
    if os.environ.get("SKIP_BEDROCK_MODEL_CHECK") == "1":
        # Escape hatch for red-glass debugging; log so misuse is visible.
        log.warning("bedrock model check disabled via SKIP_BEDROCK_MODEL_CHECK=1")
        return True
    return False


def validate_extract_model_id(model_id: str | None = None) -> None:
    """Assert the configured model id (a) exists in the region's profiles
    AND (b) can actually be invoked by this task role.

    Raises :class:`BedrockModelIdInvalid` when either check fails. Never
    swallows the underlying error — the whole point is to fail loudly at
    deploy time. Both classes localised to boot means one deploy failure
    instead of N silent uploads.
    """

    if _should_skip():
        return

    from app.integrations.bedrock_sow_extract import _model_id

    resolved = model_id or _model_id()
    if not resolved:
        raise BedrockModelIdInvalid("SOW_EXTRACT_MODEL_ID is empty")

    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    region = os.environ.get("AWS_REGION", "us-east-2")

    # ---- Check 1: profile is live in this region ------------------------
    bedrock = boto3.client("bedrock", region_name=region)
    try:
        resp = bedrock.list_inference_profiles(maxResults=100)
    except (BotoCoreError, ClientError) as exc:
        raise BedrockModelIdInvalid(
            f"could not list Bedrock inference profiles in {region}: {exc}"
        ) from exc

    live_ids = {p.get("inferenceProfileId") for p in resp.get("inferenceProfileSummaries", [])}
    if resolved not in live_ids:
        siblings = sorted(
            i for i in live_ids if i and any(tag in i for tag in ("opus", "sonnet", "haiku"))
        )
        raise BedrockModelIdInvalid(
            f"SOW_EXTRACT_MODEL_ID={resolved!r} is not a live Bedrock inference "
            f"profile in {region}. Available Anthropic profiles: {siblings}"
        )

    # ---- Check 2: this task role can actually invoke the profile --------
    # Catches the AWS-Marketplace-subscription class of bug where the model
    # is listable but Invoke returns AccessDenied. 5 tokens ≈ $0.00003.
    runtime = boto3.client("bedrock-runtime", region_name=region)
    ping_body = json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 5,
            "messages": [{"role": "user", "content": "ping"}],
        }
    )
    try:
        runtime.invoke_model(modelId=resolved, body=ping_body)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "Unknown")
        raise BedrockModelIdInvalid(
            f"SOW_EXTRACT_MODEL_ID={resolved!r} is listed but cannot be invoked "
            f"({code}). Common causes: (a) AWS Marketplace subscription not "
            f"completed for this model — subscribe in the Bedrock console; "
            f"(b) IAM policy missing bedrock:InvokeModel on the inference-profile "
            f"or foundation-model ARN. Full error: {exc}"
        ) from exc
    except (BotoCoreError, TimeoutError) as exc:
        raise BedrockModelIdInvalid(
            f"transport failure invoking {resolved!r} in {region}: {exc}"
        ) from exc

    log.info(
        "bedrock model check ok",
        extra={"model_id": resolved, "region": region},
    )

"""SES email adapter used by the notification sender worker.

Design mirrors :mod:`app.integrations.s3_evidence`: a real client that talks
to AWS via ``aiobotocore`` (loaded lazily so the API image can start without
it) plus an in-process :class:`StubSES` the test suite uses.

The DealGate SES account is in the sandbox: only verified addresses receive
mail. In dev/staging, ``SES_FROM_ADDRESS`` and the recipient email must both
be verified in the SES console (see infra-tf/modules/api ses identity
resource added alongside this file).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import structlog

log = structlog.get_logger("integrations.ses")


DEFAULT_FROM_ADDRESS = "srikantp@smartek21.com"


class SESError(Exception):
    """Raised when SES rejects the SendEmail call."""


@dataclass(frozen=True)
class SendResult:
    """What the sender worker records after a successful call."""

    message_id: str


def _from_address() -> str:
    return (os.environ.get("SES_FROM_ADDRESS") or DEFAULT_FROM_ADDRESS).strip()


def _region() -> str:
    return os.environ.get("AWS_REGION", "us-east-1")


class SESClient:
    """Thin async wrapper around aiobotocore SES SendEmail.

    aiobotocore is imported inside :meth:`send` so tests + the API image (which
    does not need it) do not pay the dependency cost at boot.
    """

    def __init__(self, region: str | None = None, from_address: str | None = None) -> None:
        self._region = region or _region()
        self._from = from_address or _from_address()

    async def send(
        self,
        *,
        to_address: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
    ) -> SendResult:
        try:
            from aiobotocore.session import get_session  # local import
        except ImportError as exc:  # pragma: no cover - depends on runtime env
            raise SESError(
                "aiobotocore is not installed; add it to the sender's image"
            ) from exc

        session = get_session()
        body: dict[str, Any] = {"Text": {"Data": body_text, "Charset": "UTF-8"}}
        if body_html:
            body["Html"] = {"Data": body_html, "Charset": "UTF-8"}

        try:
            async with session.create_client("ses", region_name=self._region) as client:
                response = await client.send_email(
                    Source=self._from,
                    Destination={"ToAddresses": [to_address]},
                    Message={
                        "Subject": {"Data": subject, "Charset": "UTF-8"},
                        "Body": body,
                    },
                )
        except Exception as exc:  # pragma: no cover - network
            raise SESError(str(exc)) from exc

        message_id = response.get("MessageId") or ""
        log.info("ses_send_ok", to=to_address, message_id=message_id)
        return SendResult(message_id=message_id)


class StubSES(SESClient):
    """In-process client for tests / offline dev.

    Every :meth:`send` call is appended to :attr:`sent` and returns a
    predictable message id. Tests that want to simulate a failure swap the
    instance for one whose :attr:`fail_with` is set.
    """

    def __init__(
        self,
        *,
        region: str = "us-east-1",
        from_address: str = DEFAULT_FROM_ADDRESS,
        fail_with: str | None = None,
    ) -> None:
        self._region = region
        self._from = from_address
        self.sent: list[dict[str, Any]] = []
        self.fail_with = fail_with

    async def send(
        self,
        *,
        to_address: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
    ) -> SendResult:
        if self.fail_with:
            raise SESError(self.fail_with)
        payload = {
            "from": self._from,
            "to": to_address,
            "subject": subject,
            "body_text": body_text,
            "body_html": body_html,
        }
        self.sent.append(payload)
        return SendResult(message_id=f"stub-{len(self.sent):06d}")


def get_ses_client() -> SESClient:
    """Factory the worker uses. Override with :class:`StubSES` in tests."""

    return SESClient()


__all__ = [
    "DEFAULT_FROM_ADDRESS",
    "SESClient",
    "SESError",
    "SendResult",
    "StubSES",
    "get_ses_client",
]

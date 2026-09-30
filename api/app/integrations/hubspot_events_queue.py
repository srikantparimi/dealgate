"""S19 slice 1 §B4/§B5: async SQS client for the HubSpot events pipeline.

The api webhook receiver enqueues verified events here; the worker
(`worker.hubspot_intake`) drains the queue with long-poll and hands the
raw payload back to :mod:`app.services.hubspot_intake` which re-reads the
deal from the CRM API (rule 7 — webhook payloads are untrusted).

Design mirrors :mod:`app.integrations.ses`:
- ``aiobotocore`` imported inside methods so the API can start without the
  optional dep on developer machines.
- ``StubHubSpotEventsQueue`` for tests + local runs so nothing hits AWS.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger("hubspot_events_queue")


def _queue_url() -> str:
    return os.environ.get("HUBSPOT_EVENT_QUEUE_URL", "").strip()


def _region() -> str:
    return os.environ.get("AWS_REGION", "us-east-2")


@dataclass(frozen=True)
class SentMessage:
    message_id: str


@dataclass(frozen=True)
class ReceivedMessage:
    message_id: str
    receipt_handle: str
    body: dict[str, Any]
    receive_count: int


class HubSpotEventsQueueError(RuntimeError):
    """Any SQS failure surfaces as this — the caller decides retry/fail."""


class HubSpotEventsQueue:
    """Real SQS client. Instantiated lazily; aiobotocore imported per call."""

    def __init__(self, *, queue_url: str | None = None, region: str | None = None) -> None:
        self._queue_url = queue_url or _queue_url()
        self._region = region or _region()

    @property
    def queue_url(self) -> str:
        if not self._queue_url:
            raise HubSpotEventsQueueError(
                "HUBSPOT_EVENT_QUEUE_URL is not set — TF wires it via the api task-def env"
            )
        return self._queue_url

    async def send(self, payload: dict[str, Any]) -> SentMessage:
        try:
            from aiobotocore.session import get_session
        except ImportError as exc:  # pragma: no cover
            raise HubSpotEventsQueueError(
                "aiobotocore is not installed; add it to the api/worker image"
            ) from exc

        session = get_session()
        try:
            async with session.create_client("sqs", region_name=self._region) as client:
                response = await client.send_message(
                    QueueUrl=self.queue_url,
                    MessageBody=json.dumps(payload),
                )
        except Exception as exc:  # pragma: no cover — network
            raise HubSpotEventsQueueError(str(exc)) from exc
        message_id = response.get("MessageId") or ""
        log.info("hubspot_queue_enqueued", message_id=message_id)
        return SentMessage(message_id=message_id)

    async def receive(
        self, *, max_messages: int = 10, wait_seconds: int = 20
    ) -> list[ReceivedMessage]:
        try:
            from aiobotocore.session import get_session
        except ImportError as exc:  # pragma: no cover
            raise HubSpotEventsQueueError(
                "aiobotocore is not installed; add it to the worker image"
            ) from exc

        session = get_session()
        try:
            async with session.create_client("sqs", region_name=self._region) as client:
                response = await client.receive_message(
                    QueueUrl=self.queue_url,
                    MaxNumberOfMessages=max_messages,
                    WaitTimeSeconds=wait_seconds,
                    AttributeNames=["ApproximateReceiveCount"],
                )
        except Exception as exc:  # pragma: no cover
            raise HubSpotEventsQueueError(str(exc)) from exc

        messages = response.get("Messages") or []
        received: list[ReceivedMessage] = []
        for m in messages:
            try:
                body = json.loads(m.get("Body") or "{}")
            except json.JSONDecodeError:
                log.warning("hubspot_queue_bad_body", message_id=m.get("MessageId"))
                body = {}
            receive_count = int(
                (m.get("Attributes") or {}).get("ApproximateReceiveCount") or "0"
            )
            received.append(
                ReceivedMessage(
                    message_id=m.get("MessageId") or "",
                    receipt_handle=m.get("ReceiptHandle") or "",
                    body=body,
                    receive_count=receive_count,
                )
            )
        return received

    async def delete(self, receipt_handle: str) -> None:
        try:
            from aiobotocore.session import get_session
        except ImportError as exc:  # pragma: no cover
            raise HubSpotEventsQueueError(
                "aiobotocore is not installed; add it to the worker image"
            ) from exc

        session = get_session()
        try:
            async with session.create_client("sqs", region_name=self._region) as client:
                await client.delete_message(
                    QueueUrl=self.queue_url, ReceiptHandle=receipt_handle
                )
        except Exception as exc:  # pragma: no cover
            raise HubSpotEventsQueueError(str(exc)) from exc


@dataclass
class StubHubSpotEventsQueue(HubSpotEventsQueue):
    """In-process queue for tests + local runs.

    ``sent`` retains every enqueued payload so tests can assert on shape.
    ``inbox`` seeds messages the consumer receives; consume/delete flip
    them to ``deleted``.
    """

    sent: list[dict[str, Any]] = field(default_factory=list)
    inbox: list[dict[str, Any]] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    _handle_seq: int = 0

    def __init__(self) -> None:  # type: ignore[override]
        super().__init__(queue_url="stub://local", region="us-east-2")
        self.sent = []
        self.inbox = []
        self.deleted = []
        self._handle_seq = 0

    async def send(self, payload: dict[str, Any]) -> SentMessage:  # type: ignore[override]
        self.sent.append(payload)
        return SentMessage(message_id=f"stub-{len(self.sent)}")

    async def receive(  # type: ignore[override]
        self, *, max_messages: int = 10, wait_seconds: int = 20
    ) -> list[ReceivedMessage]:
        batch = self.inbox[:max_messages]
        self.inbox = self.inbox[max_messages:]
        received: list[ReceivedMessage] = []
        for i, body in enumerate(batch):
            self._handle_seq += 1
            received.append(
                ReceivedMessage(
                    message_id=f"stub-msg-{self._handle_seq}",
                    receipt_handle=f"stub-rh-{self._handle_seq}",
                    body=body,
                    receive_count=1,
                )
            )
        return received

    async def delete(self, receipt_handle: str) -> None:  # type: ignore[override]
        self.deleted.append(receipt_handle)


_INSTANCE: HubSpotEventsQueue | None = None


def get_queue() -> HubSpotEventsQueue:
    """FastAPI dependency-friendly accessor.

    A single instance per process so aiobotocore's connection pool sticks.
    Tests replace via ``app.dependency_overrides[get_queue]``.
    """

    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = HubSpotEventsQueue()
    return _INSTANCE


def set_queue_for_tests(queue: HubSpotEventsQueue | None) -> None:
    """Test helper — swap the singleton, restore on teardown."""

    global _INSTANCE
    _INSTANCE = queue

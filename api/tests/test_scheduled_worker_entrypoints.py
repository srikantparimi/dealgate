"""Regression coverage for EventBridge-launched worker process lifetimes."""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from worker import alert_scheduler, notification_sender, renewals_scheduler


@asynccontextmanager
async def _session_scope(session: object):
    yield session


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module", "operation", "result"),
    [
        (alert_scheduler, "run_tick", alert_scheduler.TickResult()),
        (notification_sender, "process_batch", 0),
        (renewals_scheduler, "run_tick", renewals_scheduler.TickResult()),
    ],
)
async def test_eventbridge_worker_runs_once_and_returns(
    monkeypatch: pytest.MonkeyPatch,
    module: object,
    operation: str,
    result: object,
) -> None:
    session = object()
    calls: list[object] = []

    async def fake_operation(actual_session: object) -> object:
        calls.append(actual_session)
        return result

    monkeypatch.setattr(module, "session_factory", lambda: _session_scope(session))
    monkeypatch.setattr(module, operation, fake_operation)

    await module.run_once()

    assert calls == [session]

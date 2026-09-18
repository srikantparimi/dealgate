"""Scheduler support package (S2-E3 Wave 2).

Holds the ``scheduler_fired`` idempotency ledger + role→leader mapping used
by the alert scheduler worker. Business logic lives in
``worker.alert_scheduler`` — this package is deliberately thin and free of
side effects at import time.
"""

from app.scheduler.ledger import SchedulerFired, record_trigger
from app.scheduler.routing import (
    LEGAL_LEADER_EMAIL_ENV,
    SALES_LEADER_EMAIL_ENV,
    resolve_head_for_role,
)

__all__ = [
    "LEGAL_LEADER_EMAIL_ENV",
    "SALES_LEADER_EMAIL_ENV",
    "SchedulerFired",
    "record_trigger",
    "resolve_head_for_role",
]

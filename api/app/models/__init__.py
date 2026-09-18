"""ORM models. One file per table group, all sharing `app.db.Base`.

Importing this package registers every mapper on `Base.metadata` — Alembic's
`env.py` relies on that side-effect.
"""

from app.models.audit import AuditEvent
from app.models.client import Agreement, Client, LegalEntity
from app.models.integration import IntegrationEvent
from app.models.notification import Notification, NotificationSetting
from app.models.opportunity import Opportunity
from app.models.policy import PolicyVersion
from app.models.rate_card import RateCardRow, RateCardVersion
from app.models.task import Task
from app.models.user import User

__all__ = [
    "Agreement",
    "AuditEvent",
    "Client",
    "IntegrationEvent",
    "LegalEntity",
    "Notification",
    "NotificationSetting",
    "Opportunity",
    "PolicyVersion",
    "RateCardRow",
    "RateCardVersion",
    "Task",
    "User",
]

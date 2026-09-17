"""ORM models. One file per table group, all sharing `app.db.Base`.

Importing this package registers every mapper on `Base.metadata` — Alembic's
`env.py` relies on that side-effect.
"""

from app.models.audit import AuditEvent
from app.models.client import Agreement, Client, LegalEntity
from app.models.integration import IntegrationEvent
from app.models.opportunity import Opportunity
from app.models.task import Task
from app.models.user import User

__all__ = [
    "Agreement",
    "AuditEvent",
    "Client",
    "IntegrationEvent",
    "LegalEntity",
    "Opportunity",
    "Task",
    "User",
]

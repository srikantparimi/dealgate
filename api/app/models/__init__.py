"""ORM models. One file per table group, all sharing `app.db.Base`.

Importing this package registers every mapper on `Base.metadata` — Alembic's
`env.py` relies on that side-effect.
"""

from app.models.adviser_estimate import AdviserEstimate
from app.models.approval import Approval, ApprovalPackage
from app.models.audit import AuditEvent
from app.models.ceo_exception import CeoDelegate, CeoException
from app.models.client import Agreement, Client, LegalEntity
from app.models.gm_model import CostLine, GmModel, ResourceLine
from app.models.hubspot_writeback import HubspotWritebackJob
from app.models.integration import IntegrationEvent
from app.models.notification import Notification, NotificationSetting
from app.models.opportunity import Opportunity
from app.models.policy import PolicyVersion
from app.models.rate_card import RateCardRow, RateCardVersion
from app.models.sow import Sow, SowVersion
from app.models.task import Task
from app.models.user import User

# Import last: extends Sow/SowVersion/GmModel with the columns migration
# 0009 adds and registers ``legacy_import_batch``. Must run after the base
# mappers above so ``__table__.append_column`` sees the ready tables.
from app.models.legacy import LegacyImportBatch  # noqa: E402  (order matters)

__all__ = [
    "AdviserEstimate",
    "Agreement",
    "Approval",
    "ApprovalPackage",
    "AuditEvent",
    "CeoDelegate",
    "CeoException",
    "Client",
    "CostLine",
    "GmModel",
    "HubspotWritebackJob",
    "IntegrationEvent",
    "LegacyImportBatch",
    "LegalEntity",
    "Notification",
    "NotificationSetting",
    "Opportunity",
    "PolicyVersion",
    "RateCardRow",
    "RateCardVersion",
    "ResourceLine",
    "Sow",
    "SowVersion",
    "Task",
    "User",
]

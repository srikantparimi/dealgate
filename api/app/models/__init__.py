"""ORM models. One file per table group, all sharing `app.db.Base`.

Importing this package registers every mapper on `Base.metadata` — Alembic's
`env.py` relies on that side-effect.
"""

from app.models.actual import ActualImportBatch, ActualPeriod
from app.models.adviser_estimate import AdviserEstimate
from app.models.approval import Approval, ApprovalPackage
from app.models.agreement_tracking import AgreementDocument, AgreementGap
from app.models.audit import AuditEvent
from app.models.capability import CapabilityCatalog
from app.models.ceo_exception import CeoDelegate, CeoException
from app.models.client import Agreement, Client, LegalEntity
from app.models.client_alias import ClientAlias
from app.models.client_contact import ClientContact as ClientContact
from app.models.client_rate_card import ClientRateCard, ClientRateCardRow
from app.models.direct_cost_settings import DirectCostSettings
from app.models.embedding import SowEmbedding
from app.models.forecast import ForecastPeriod
from app.models.function_owner import FunctionOwner
from app.models.gm_model import CostLine, GmModel, ResourceLine
from app.models.hubspot_writeback import HubspotWritebackJob
from app.models.integration import IntegrationEvent
from app.models.notification import Notification, NotificationSetting
from app.models.opportunity import Opportunity
from app.models.policy import PolicyVersion
from app.models.rate_card import RateCardRow, RateCardVersion
from app.models.renewal import Renewal
from app.models.signed_sow import SignedSowUpload
from app.models.sow import Sow, SowVersion
from app.models.sow_upload_job import SowUploadJob
from app.models.task import Task
from app.models.user import User

# Import last: extends Sow/SowVersion/GmModel with the columns migration
# 0009 adds and registers ``legacy_import_batch``. Must run after the base
# mappers above so ``__table__.append_column`` sees the ready tables.
from app.models.legacy import LegacyImportBatch  # noqa: E402  (order matters)

# S7 wave 2: WBS phases + reusable templates. Phase model uses the same
# ``append_column`` idiom to attach ``phase_id`` FKs to resource_line and
# cost_line, so it must import after ``legacy`` for the mapper order to
# be deterministic.
from app.models.gm_model_phase import GmModelPhase  # noqa: E402
from app.models.gm_model_template import GmModelTemplate  # noqa: E402

__all__ = [
    "ActualImportBatch",
    "ActualPeriod",
    "AdviserEstimate",
    "Agreement",
    "AgreementDocument",
    "AgreementGap",
    "Approval",
    "ApprovalPackage",
    "AuditEvent",
    "CapabilityCatalog",
    "CeoDelegate",
    "CeoException",
    "Client",
    "ClientAlias",
    "ClientRateCard",
    "ClientRateCardRow",
    "CostLine",
    "DirectCostSettings",
    "ForecastPeriod",
    "FunctionOwner",
    "GmModel",
    "GmModelPhase",
    "GmModelTemplate",
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
    "Renewal",
    "ResourceLine",
    "SignedSowUpload",
    "Sow",
    "SowEmbedding",
    "SowUploadJob",
    "SowVersion",
    "Task",
    "User",
]

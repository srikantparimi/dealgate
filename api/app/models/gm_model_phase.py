"""``gm_model_phase`` — WBS phase row (S7 wave 2).

Blueprint §8 explicit inputs list carries "Work breakdown". A phase is a
first-class row that groups the resource + cost lines that implement a
piece of the SOW. Migration ``20260919_0024`` owns the DDL; this file
registers the mapper + the new ``ResourceLine.phase_id`` /
``CostLine.phase_id`` FK columns via the ``append_column`` idiom the
legacy scope already uses (so we do not fork the base ``gm_model.py``).

Nullable ``phase_id`` on resource/cost lines is deliberate — legacy
rows and freshly created models default to ``NULL`` and render in the
Builder's "Ungrouped" bucket.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


class GmModelPhase(Base):
    __tablename__ = "gm_model_phase"
    __table_args__ = (
        UniqueConstraint("gm_model_id", "order", name="uq_gm_model_phase_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    gm_model_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("gm_model.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    sow_deliverable_ref: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Back-populated from GmModel / ResourceLine / CostLine below via
    # relationship() calls attached after the class body so we avoid a
    # circular import at module load time.


# ---- attach the FK column + relationship to resource_line / cost_line ----
# Same pattern legacy.py uses: append_column so the base gm_model.py file
# owned by S3 does not need editing, and the mapper still surfaces
# ``ResourceLine.phase_id`` and ``ResourceLine.phase`` after this module
# imports.

from app.models.gm_model import CostLine, GmModel, ResourceLine  # noqa: E402


def _add_column(cls, name: str, column: Column) -> None:
    if hasattr(cls, name):
        return
    column.name = name
    cls.__table__.append_column(column)
    cls.__mapper__.add_property(name, cls.__table__.c[name])


_add_column(
    ResourceLine,
    "phase_id",
    Column(Uuid, ForeignKey("gm_model_phase.id"), nullable=True),
)
_add_column(
    CostLine,
    "phase_id",
    Column(Uuid, ForeignKey("gm_model_phase.id"), nullable=True),
)


# Relationships (safe to attach after both mappers exist).
if not hasattr(GmModel, "phases"):
    GmModel.phases = relationship(  # type: ignore[attr-defined]
        "GmModelPhase",
        primaryjoin="GmModel.id == GmModelPhase.gm_model_id",
        foreign_keys="GmModelPhase.gm_model_id",
        cascade="all, delete-orphan",
        order_by="GmModelPhase.order",
        backref="gm_model",
    )

if not hasattr(GmModelPhase, "resource_lines"):
    GmModelPhase.resource_lines = relationship(  # type: ignore[attr-defined]
        "ResourceLine",
        primaryjoin="GmModelPhase.id == foreign(ResourceLine.phase_id)",
        viewonly=True,
    )

if not hasattr(GmModelPhase, "cost_lines"):
    GmModelPhase.cost_lines = relationship(  # type: ignore[attr-defined]
        "CostLine",
        primaryjoin="GmModelPhase.id == foreign(CostLine.phase_id)",
        viewonly=True,
    )


__all__ = ["GmModelPhase"]

"""Manual checklist model.

Stores one row per checklist item verified for an application (for example
``Bank Maintenance Originality Verified`` or ``OCR Review Completed``). Items
are stored separately so each can carry its own checked state, reviewer and
timestamp. A given item name is unique per application.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.application import Application


class ManualChecklist(Base):
    """One manual checklist item verified for an application.

    Attributes:
        id: Auto-incrementing primary key.
        application_id: Application this item belongs to (foreign key, cascades).
        item_name: Name of the checklist item.
        is_checked: Whether the item has been verified as true.
        reviewer: Name of the reviewer who checked the item.
        checked_at: When the item was marked (UTC), if checked.
    """

    __tablename__ = "manual_checklists"
    __table_args__ = (
        Index("ix_manual_checklists_application_id", "application_id"),
        UniqueConstraint(
            "application_id",
            "item_name",
            name="uq_manual_checklists_application_id_item_name",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_checked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    reviewer: Mapped[str | None] = mapped_column(String(255))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    application: Mapped[Application] = relationship(back_populates="checklist_items")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ManualChecklist id={self.id} item={self.item_name} checked={self.is_checked}>"

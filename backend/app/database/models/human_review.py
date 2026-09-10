"""Human review model.

Records a manual review decision made by a reviewer against an application.
A review may attach corrections (see :class:`HumanCorrection`) and carries
free-form comments. Reviews form an auditable trail of human oversight on top
of the automated validation results.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.models.enums import ReviewDecision

if TYPE_CHECKING:
    from app.database.models.application import Application
    from app.database.models.human_correction import HumanCorrection


class HumanReview(Base):
    """A manual review decision for an application.

    Attributes:
        id: Auto-incrementing primary key.
        application_id: Application being reviewed (foreign key, cascades).
        reviewer_name: Name of the reviewer who made the decision.
        reviewed_at: When the review was recorded (UTC).
        decision: Approve, correct or reject the application.
        comments: Free-form justification or notes from the reviewer.
    """

    __tablename__ = "human_reviews"
    __table_args__ = (
        Index("ix_human_reviews_application_id", "application_id"),
        Index("ix_human_reviews_reviewer_name", "reviewer_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    reviewer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    decision: Mapped[ReviewDecision] = mapped_column(nullable=False)
    comments: Mapped[str | None] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    application: Mapped[Application] = relationship(back_populates="human_reviews")
    corrections: Mapped[list[HumanCorrection]] = relationship(
        back_populates="review",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<HumanReview id={self.id} decision={self.decision}>"

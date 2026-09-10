"""Visual detection result model.

Stores the outcome of visual detection runs (signatures, stamps) for a
document. The detection itself is performed by a dedicated vision pipeline
(``detection_engine``) that is outside this module; the business rule engine
consumes these rows to verify that required signatures and stamps are present.
The ``detection_type`` column carries an opaque string (e.g. ``SIGNATURE``,
``STAMP``) so future detection kinds can be added without a schema change.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.database.models.document import Document


class VisualDetection(Base):
    """Result of one visual detection run for a document and detection kind.

    Attributes:
        id: Auto-incrementing primary key.
        document_id: Document that was inspected (foreign key, cascades).
        detection_type: Kind of detection (e.g. ``SIGNATURE``, ``STAMP``).
        is_present: Whether the detection kind was found in the document.
        confidence: Detection confidence reported by the engine (0.0 - 1.0).
        detection_engine: Identifier of the engine that produced the result.
        detected_at: When the detection completed (UTC).
    """

    __tablename__ = "visual_detection_results"
    __table_args__ = (
        Index("ix_visual_detection_results_document_id", "document_id"),
        UniqueConstraint(
            "document_id",
            "detection_type",
            name="uq_visual_detection_results_document_id_detection_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    detection_type: Mapped[str] = mapped_column(String(50), nullable=False)
    is_present: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    detection_engine: Mapped[str | None] = mapped_column(String(100))
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    document: Mapped[Document] = relationship(back_populates="visual_detections")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<VisualDetection id={self.id} type={self.detection_type} "
            f"present={self.is_present}>"
        )

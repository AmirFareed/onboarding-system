"""Pydantic schemas for the FeedbackEntry entity."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FeedbackEntryBase(BaseModel):
    """Common feedback dataset attributes shared by all variants."""

    field_name: str = Field(min_length=1, max_length=255)
    human_value: str = Field(min_length=1)


class FeedbackEntryCreate(FeedbackEntryBase):
    """Payload for creating a new feedback dataset sample."""

    application_id: int | None = None
    ocr_value: str | None = None
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)


class FeedbackEntryRead(FeedbackEntryBase):
    """Serialized feedback dataset sample including database-managed fields."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int | None
    ocr_value: str | None
    confidence_score: float | None
    recorded_at: datetime

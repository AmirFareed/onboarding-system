"""Pydantic schemas for the HumanReview and HumanCorrection entities."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.database.models.enums import ReviewDecision


class HumanCorrectionBase(BaseModel):
    """Common human correction attributes shared by all variants."""

    field_name: str = Field(min_length=1, max_length=255)
    corrected_value: str = Field(min_length=1)


class HumanCorrectionCreate(HumanCorrectionBase):
    """Payload for creating a new human correction."""

    original_value: str | None = None
    reason: str | None = None


class HumanCorrectionRead(HumanCorrectionBase):
    """Serialized human correction including database-managed fields."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    original_value: str | None
    reason: str | None


class HumanReviewBase(BaseModel):
    """Common human review attributes shared by all variants."""

    reviewer_name: str = Field(min_length=1, max_length=255)
    decision: ReviewDecision
    comments: str | None = None


class HumanReviewCreate(HumanReviewBase):
    """Payload for creating a new human review."""

    application_id: int


class HumanReviewRead(HumanReviewBase):
    """Serialized human review including database-managed fields."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    reviewed_at: datetime
    corrections: list[HumanCorrectionRead] = []

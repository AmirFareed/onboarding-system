"""Pydantic schemas for the ManualChecklist entity."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ManualChecklistBase(BaseModel):
    """Common manual checklist attributes shared by all variants."""

    item_name: str = Field(min_length=1, max_length=255)
    is_checked: bool = False
    reviewer: str | None = Field(default=None, max_length=255)
    checked_at: datetime | None = None


class ManualChecklistCreate(ManualChecklistBase):
    """Payload for creating a new manual checklist item."""

    application_id: int


class ManualChecklistUpdate(BaseModel):
    """Payload for updating a manual checklist item's verification state."""

    is_checked: bool
    reviewer: str | None = Field(default=None, max_length=255)
    checked_at: datetime | None = None


class ManualChecklistRead(ManualChecklistBase):
    """Serialized manual checklist item including database-managed fields."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int

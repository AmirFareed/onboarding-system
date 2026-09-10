"""Pydantic schemas for the Application entity.

These models validate data entering and leaving the database layer. Read models
enable ``from_attributes`` ORM mode so repository results serialize directly;
create/update models describe the payloads accepted by future API endpoints.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.database.models.enums import ApplicationStatus


class ApplicationBase(BaseModel):
    """Common application attributes shared by all variants."""

    status: ApplicationStatus = ApplicationStatus.SUBMITTED
    created_by: str = Field(min_length=1, max_length=255)
    name: str | None = Field(
        default=None,
        max_length=255,
        description="Display name derived from the first uploaded PDF filename.",
    )
    notes: str | None = None


class ApplicationCreate(ApplicationBase):
    """Payload for creating a new application."""


class ApplicationUpdate(BaseModel):
    """Payload for partially updating an application.

    Every field is optional so clients can send only the values they wish to
    change. A value of ``None`` clears the corresponding attribute.
    """

    status: ApplicationStatus | None = None
    notes: str | None = None


class ApplicationRead(ApplicationBase):
    """Serialized application including database-managed fields."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    submitted_at: datetime
    updated_at: datetime

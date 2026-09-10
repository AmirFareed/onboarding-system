"""Pydantic schemas for the AuditLog entity."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuditLogCreate(BaseModel):
    """Payload for creating a new audit log record."""

    application_id: int | None = None
    username: str = Field(min_length=1, max_length=255)
    action: str = Field(min_length=1, max_length=100)
    details: dict[str, Any] | None = None


class AuditLogRead(BaseModel):
    """Serialized audit log record including database-managed fields."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int | None
    username: str
    action: str
    performed_at: datetime
    details: dict[str, Any] | None

"""Pydantic schemas for the IT system-log API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SystemLogRead(BaseModel):
    """One readable audit log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int | None
    username: str
    actor_role: str | None
    action: str
    severity: str | None
    previous_status: str | None
    new_status: str | None
    document_id: int | None
    performed_at: datetime
    details: dict[str, Any] | None


class SystemLogListResponse(BaseModel):
    """Paginated system log results, newest first."""

    items: list[SystemLogRead]
    total: int
    offset: int
    limit: int


class ErrorResponse(BaseModel):
    """Envelope used for system-log error responses."""

    detail: str = Field(default="System log error")
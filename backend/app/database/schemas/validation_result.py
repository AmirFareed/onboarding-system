"""Pydantic schemas for the ValidationResult entity."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.database.models.enums import Severity, ValidationStatus


class ValidationResultBase(BaseModel):
    """Common validation result attributes shared by all variants."""

    rule_id: str = Field(min_length=1, max_length=100)
    rule_name: str = Field(min_length=1, max_length=255)
    rule_category: str = Field(min_length=1, max_length=100)
    severity: Severity


class ValidationResultCreate(ValidationResultBase):
    """Payload for creating a new validation result."""

    application_id: int
    status: ValidationStatus = ValidationStatus.PENDING_MANUAL_REVIEW
    message: str | None = None


class ValidationResultRead(ValidationResultBase):
    """Serialized validation result including database-managed fields."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    status: ValidationStatus
    message: str | None
    validated_at: datetime

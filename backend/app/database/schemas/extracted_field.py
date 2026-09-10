"""Pydantic schemas for the ExtractedField entity."""

from pydantic import BaseModel, ConfigDict, Field


class ExtractedFieldBase(BaseModel):
    """Common extracted field attributes shared by all variants."""

    field_name: str = Field(min_length=1, max_length=255)
    extracted_value: str = Field(min_length=1)


class ExtractedFieldCreate(ExtractedFieldBase):
    """Payload for creating a new extracted field."""

    ocr_result_id: int
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    normalized_value: str | None = None


class ExtractedFieldRead(ExtractedFieldBase):
    """Serialized extracted field including database-managed fields."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    ocr_result_id: int
    confidence_score: float | None
    normalized_value: str | None

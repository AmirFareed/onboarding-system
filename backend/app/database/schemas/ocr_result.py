"""Pydantic schemas for the OCRResult entity."""

from pydantic import BaseModel, ConfigDict, Field

from app.database.schemas.extracted_field import ExtractedFieldRead


class OCRResultBase(BaseModel):
    """Common OCR result attributes shared by all variants."""

    document_id: int
    raw_ocr_text: str = Field(min_length=1)
    ocr_engine: str = Field(min_length=1, max_length=100)


class OCRResultCreate(OCRResultBase):
    """Payload for creating a new OCR result."""

    processing_time_ms: int | None = Field(default=None, ge=0)
    overall_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class OCRResultRead(OCRResultBase):
    """Serialized OCR result including database-managed fields."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    processing_time_ms: int | None
    overall_confidence: float | None
    extracted_fields: list[ExtractedFieldRead] = []

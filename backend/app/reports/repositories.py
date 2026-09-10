"""Repository access for the validation report module.

The report module is read-only and reuses the existing repositories; this
facade exists so the module's architecture stays self-contained and the
service never imports repository internals from scattered locations. No new
repository is defined -- the module must not mutate or own any data.
"""

from __future__ import annotations

from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.document_analysis_repository import (
    DocumentAnalysisRepository,
)
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.extracted_field_repository import (
    ExtractedFieldRepository,
)
from app.database.repositories.ocr_repository import OCRRepository
from app.database.repositories.validation_repository import ValidationRepository
from app.database.repositories.visual_detection_repository import (
    VisualDetectionRepository,
)

__all__ = [
    "ApplicationRepository",
    "DocumentAnalysisRepository",
    "DocumentRepository",
    "ExtractedFieldRepository",
    "OCRRepository",
    "ValidationRepository",
    "VisualDetectionRepository",
]

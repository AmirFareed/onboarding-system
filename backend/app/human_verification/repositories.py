"""Repository layer facade for the final human verification module.

Re-exports the repositories this module needs from the shared database layer so
the service depends on the module facade instead of importing repository paths
directly.
"""

from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.audit_log_repository import AuditLogRepository
from app.database.repositories.document_analysis_repository import (
    DocumentAnalysisRepository,
)
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.extracted_field_repository import (
    ExtractedFieldRepository,
)
from app.database.repositories.feedback_repository import FeedbackRepository
from app.database.repositories.human_correction_repository import (
    HumanCorrectionRepository,
)
from app.database.repositories.human_review_repository import HumanReviewRepository
from app.database.repositories.manual_checklist_repository import (
    ManualChecklistRepository,
)
from app.database.repositories.ocr_repository import OCRRepository
from app.database.repositories.validation_repository import ValidationRepository
from app.database.repositories.visual_detection_repository import (
    VisualDetectionRepository,
)

__all__ = [
    "ApplicationRepository",
    "AuditLogRepository",
    "DocumentAnalysisRepository",
    "DocumentRepository",
    "ExtractedFieldRepository",
    "FeedbackRepository",
    "HumanCorrectionRepository",
    "HumanReviewRepository",
    "ManualChecklistRepository",
    "OCRRepository",
    "ValidationRepository",
    "VisualDetectionRepository",
]

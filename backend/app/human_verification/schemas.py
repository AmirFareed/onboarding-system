"""Pydantic models forming the final human verification API contract.

The review screen carries everything the employee needs to make the final
decision -- the aggregated validation report, the uploaded documents, the
normalized and confidence-scored extracted fields, the visual detection results
and the current checklist state -- while the review request carries the
decision, the checklist completion, the optional corrections and the mandatory
rejection reason for rejections.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.database.models.enums import ReviewDecision
from app.reports.schemas import ReportApplicationInfo, ValidationReport


class ChecklistItem(BaseModel):
    """One manual checklist item submitted with a review.

    Attributes:
        item_name: Name of the checklist item (see ``CHECKLIST_ITEMS``).
        is_checked: Whether the reviewer verified the item.
    """

    item_name: str = Field(min_length=1, max_length=255)
    is_checked: bool = False


class ChecklistItemRead(BaseModel):
    """Serialized checklist item including its stored state."""

    model_config = ConfigDict(from_attributes=True)

    item_name: str
    is_checked: bool
    reviewer: str | None = None
    checked_at: datetime | None = None


class CorrectionItem(BaseModel):
    """One field-level correction submitted with a CORRECT decision.

    Attributes:
        field_name: Name of the corrected field.
        corrected_value: Value confirmed by the reviewer.
        reason: Optional explanation for the correction.
        document_id: Id of the document the field was extracted from.
            Disambiguates two documents on the same application that extract
            a same-named field; when omitted, the correction matches any
            field with that name (fine when the name is unique on the
            application, which is the common case).
    """

    field_name: str = Field(min_length=1, max_length=255)
    corrected_value: str = Field(min_length=1)
    reason: str | None = None
    document_id: int | None = None


class CorrectionItemRead(BaseModel):
    """Serialized correction attached to a stored review."""

    model_config = ConfigDict(from_attributes=True)

    field_name: str
    document_id: int | None = None
    original_value: str | None = None
    corrected_value: str
    reason: str | None = None


class HumanReviewRequest(BaseModel):
    """Payload submitting the employee's final decision.

    Attributes:
        decision: One of ``APPROVE``, ``CORRECT`` or ``REJECT``.
        comments: Optional free-form notes.
        rejection_reason: Mandatory explanation when the decision is ``REJECT``.
        checklist: Manual checklist state; every item must be checked to
            approve.
        corrections: Corrected values; at least one is required to correct.
    """

    decision: ReviewDecision
    comments: str | None = None
    rejection_reason: str | None = None
    checklist: list[ChecklistItem] = Field(default_factory=list)
    corrections: list[CorrectionItem] = Field(default_factory=list)


class HumanReviewResponse(BaseModel):
    """A stored human review as returned by the history and screen endpoints."""

    review_id: int
    application_id: int
    decision: ReviewDecision
    reviewer_name: str
    comments: str | None = None
    rejection_reason: str | None = None
    reviewed_at: datetime
    checklist_checked: int
    checklist_total: int
    corrections: list[CorrectionItemRead] = Field(default_factory=list)


class ReviewSummary(BaseModel):
    """Outcome of a submitted review.

    Attributes:
        application_id: Id of the application.
        review_id: Id of the stored review.
        decision: The employee's decision.
        reviewer_name: Name of the employee.
        application_status: Status the application was moved to.
        reviewed_at: When the decision was recorded.
        comments: Free-form notes, if any.
        rejection_reason: Mandatory reason for a rejection, if any.
        corrections_count: Number of corrections stored.
        checklist_checked: Number of checklist items checked.
        checklist_total: Total number of checklist items.
    """

    application_id: int
    review_id: int
    decision: ReviewDecision
    reviewer_name: str
    application_status: str
    reviewed_at: datetime
    comments: str | None = None
    rejection_reason: str | None = None
    corrections_count: int
    checklist_checked: int
    checklist_total: int


class ReviewDocumentItem(BaseModel):
    """Uploaded document metadata shown on the review screen.

    Attributes:
        document_id: Id of the document.
        document_type: Document type of the document.
        original_filename: Filename supplied by the uploader.
        file_type: Media type of the stored file.
        processing_status: Current processing status of the document.
        ocr_status: OCR/extraction outcome for the document.
        ocr_confidence: OCR confidence for the document, when available.
        ocr_text_preview: Prefix of the raw OCR text for manual inspection.
        uploaded_at: When the document was uploaded.
    """

    document_id: int
    document_type: str
    original_filename: str
    file_type: str
    processing_status: str
    ocr_status: str
    ocr_confidence: float | None = None
    ocr_text_preview: str | None = None
    uploaded_at: datetime


class ReviewFieldItem(BaseModel):
    """One extracted field with its confidence and normalization state.

    Attributes:
        field_name: Name of the field.
        document_id: Id of the document that carried the field.
        file_name: Original filename of the owning document.
        extracted_value: Value produced by the extraction engine.
        normalized_value: Canonical form of the value, if normalization ran.
        confidence_score: Field confidence (0.0 - 1.0).
        confidence_source: Source that produced the score.
        verification_status: Per-field verification state.
        human_corrected_value: Value confirmed by a reviewer, if any.
        human_verified: Whether a reviewer verified the field.
    """

    field_name: str
    document_id: int
    file_name: str
    extracted_value: str
    normalized_value: str | None = None
    confidence_score: float | None = None
    confidence_source: str | None = None
    verification_status: str | None = None
    human_corrected_value: str | None = None
    human_verified: bool = False


class ReviewDetectionItem(BaseModel):
    """One stored visual detection outcome shown on the review screen."""

    document_id: int
    document_type: str
    detection_type: str
    is_present: bool
    confidence: float | None = None
    detection_engine: str | None = None
    detected_at: datetime


class ReviewScreen(BaseModel):
    """Everything required for the employee's final review.

    Attributes:
        application_id: Id of the application.
        application: Static application information.
        report: The aggregated validation report.
        documents: Uploaded documents with their OCR state.
        fields: Normalized and confidence-scored extracted fields.
        visual_detections: Stored signature/stamp detection outcomes.
        checklist: Current manual checklist state.
        previous_review: The most recent review, if any.
    """

    application_id: int
    application: ReportApplicationInfo
    report: ValidationReport
    documents: list[ReviewDocumentItem] = Field(default_factory=list)
    fields: list[ReviewFieldItem] = Field(default_factory=list)
    visual_detections: list[ReviewDetectionItem] = Field(default_factory=list)
    checklist: list[ChecklistItemRead] = Field(default_factory=list)
    previous_review: HumanReviewResponse | None = None


class ReviewHistory(BaseModel):
    """All final reviews recorded for an application.

    Attributes:
        application_id: Id of the application.
        reviews: Stored reviews, most recent first.
    """

    application_id: int
    reviews: list[HumanReviewResponse] = Field(default_factory=list)


class ReviewerCommentsRequest(BaseModel):
    """Payload for saving reviewer comments.

    Attributes:
        reviewer_comments: The reviewer comment text. Empty/whitespace-only
            values are stored as None. Maximum 5,000 characters.
    """

    reviewer_comments: str | None = None


class ReviewerCommentsResponse(BaseModel):
    """Response carrying the reviewer comment for an application.

    Attributes:
        application_id: Id of the application.
        reviewer_comments: The saved reviewer comment, or None if not yet
            saved.
    """

    application_id: int
    reviewer_comments: str | None = None


class EditedReportRequest(BaseModel):
    """Payload for saving an edited copy of the printable validation report.

    Attributes:
        html: The full edited report HTML. Empty/whitespace-only values are
            stored as None, which reverts the report view and PDF download
            to always regenerating fresh from live pipeline data.
    """

    html: str | None = None


class EditedReportResponse(BaseModel):
    """Response carrying the saved edited report HTML for an application.

    Attributes:
        application_id: Id of the application.
        html: The saved edited report HTML, or None if not (or no longer)
            saved.
    """

    application_id: int
    html: str | None = None


class ErrorResponse(BaseModel):
    """Standard error response body.

    Attributes:
        detail: Human-readable error description.
    """

    detail: str


__all__ = [
    "ChecklistItem",
    "ChecklistItemRead",
    "CorrectionItem",
    "CorrectionItemRead",
    "EditedReportRequest",
    "EditedReportResponse",
    "ErrorResponse",
    "HumanReviewRequest",
    "HumanReviewResponse",
    "ReviewDetectionItem",
    "ReviewDocumentItem",
    "ReviewFieldItem",
    "ReviewHistory",
    "ReviewScreen",
    "ReviewSummary",
    "ReviewerCommentsRequest",
    "ReviewerCommentsResponse",
]

"""Final human verification service.

``HumanVerificationService`` is the decision layer of the pipeline: it loads the
application, its validation report and the supporting evidence for the review
screen, then records the employee's final decision. It never runs OCR,
normalization, rules or detections -- it only reads what earlier phases
persisted and writes the review, the checklist state, the corrections, the
application status and the audit trail. The system never overrides the
employee's decision.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.database.models.enums import ReviewDecision
from app.document_processing.constants import ProcessingMethod
from app.feedback.constants import ORIGIN_FINAL_HUMAN_REVIEW
from app.human_verification.constants import (
    ACTION_APPLICATION_APPROVED,
    ACTION_APPLICATION_CORRECTED,
    ACTION_APPLICATION_REJECTED,
    ACTION_CHECKLIST_COMPLETED,
    ACTION_REVIEW_SUBMITTED,
    CHECKLIST_ITEMS,
    OCR_PREVIEW_LENGTH,
    OCR_STATUS_NOT_PROCESSED,
    OCR_STATUS_OCR_PROCESSED,
    OCR_STATUS_TEXT_EXTRACTED,
    REVIEW_VERSION,
)
from app.human_verification.exceptions import (
    ApplicationNotFound,
    HumanReviewError,
    ReviewAlreadyCompleted,
    ReviewPersistenceError,
)
from app.human_verification.repositories import (
    ApplicationRepository,
    AuditLogRepository,
    DocumentRepository,
    ExtractedFieldRepository,
    FeedbackRepository,
    HumanCorrectionRepository,
    HumanReviewRepository,
    ManualChecklistRepository,
    OCRRepository,
    VisualDetectionRepository,
)
from app.human_verification.schemas import (
    ChecklistItemRead,
    CorrectionItemRead,
    HumanReviewRequest,
    HumanReviewResponse,
    ReviewDetectionItem,
    ReviewDocumentItem,
    ReviewFieldItem,
    ReviewHistory,
    ReviewScreen,
    ReviewSummary,
)
from app.human_verification.validators import (
    decision_to_status,
    validate_decision_rules,
)
from app.reports.services import ValidationReportService

logger = logging.getLogger(__name__)


class HumanVerificationService:
    """Assemble the final review screen and record the employee's decision.

    Covers the full final-review workflow: ``get_review`` assembles the
    aggregated report, documents, extracted fields, visual detections and
    checklist state for an employee to review; ``submit_review`` records their
    decision (approve, correct or reject) and moves the application to a
    terminal status; ``get_history`` returns a previously submitted review.

    Args:
        db: Active database session.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._applications = ApplicationRepository(db)
        self._documents = DocumentRepository(db)
        self._ocr_results = OCRRepository(db)
        self._fields = ExtractedFieldRepository(db)
        self._detections = VisualDetectionRepository(db)
        self._reviews = HumanReviewRepository(db)
        self._corrections = HumanCorrectionRepository(db)
        self._checklist = ManualChecklistRepository(db)
        self._feedback = FeedbackRepository(db)
        self._audit = AuditLogRepository(db)
        self._report_service = ValidationReportService(db)

    # -- Public API -----------------------------------------------------------

    def get_review(self, *, application_id: int) -> ReviewScreen:
        """Assemble everything the employee needs for the final review.

        The screen bundles the aggregated validation report, the uploaded
        documents with their OCR state, the normalized and confidence-scored
        extracted fields, the visual detection outcomes, the current checklist
        state and any previous review. It only reads stored data.

        Args:
            application_id: Id of the application.

        Returns:
            The review screen payload.

        Raises:
            ApplicationNotFound: When the application does not exist.
        """
        self._get_application(application_id)
        report = self._report_service.get_report(application_id=application_id)
        documents = list(self._documents.get_all_by_application(application_id))
        ocr_results = list(self._ocr_results.get_by_application(application_id))
        ocr_by_document = {result.document_id: result for result in ocr_results}
        ocr_document_id = {result.id: result.document_id for result in ocr_results}
        document_map = {document.id: document for document in documents}
        fields = list(self._fields.get_by_application(application_id))
        detections = list(self._detections.get_by_application(application_id))
        logger.info("Human review opened for application id=%s", application_id)
        return ReviewScreen(
            application_id=application_id,
            application=report.application,
            report=report,
            documents=self._document_items(documents, ocr_by_document),
            fields=self._field_items(fields, ocr_document_id, document_map),
            visual_detections=self._detection_items(detections, document_map),
            checklist=self._checklist_state(application_id),
            previous_review=self._latest_review(application_id),
        )

    def submit_review(
        self,
        *,
        application_id: int,
        request: HumanReviewRequest,
        reviewer_name: str,
    ) -> ReviewSummary:
        """Record the employee's final decision for an application.

        The decision is validated (checklist completeness, rejection reason,
        corrections), the checklist state is persisted, the review and its
        corrections are stored, matching extracted fields and the feedback
        dataset are updated when a value actually changes, the application
        status is moved and the audit trail is written. The application can only
        be reviewed once; no reopen workflow exists.

        Args:
            application_id: Id of the application.
            request: Review payload with the employee's decision.
            reviewer_name: Name of the authenticated employee submitting the
                review.

        Returns:
            A summary of the recorded review.

        Raises:
            ApplicationNotFound: When the application does not exist.
            ReviewAlreadyCompleted: When the application was already reviewed.
            HumanReviewError: When the review payload violates the decision
                rules.
            ReviewPersistenceError: When the review could not be persisted.
        """
        application = self._get_application(application_id)
        self._report_service.get_report(application_id=application_id)
        if self._reviews.get_by_application(application_id):
            raise ReviewAlreadyCompleted()
        try:
            validate_decision_rules(request)
            self._persist_checklist(application_id, request, reviewer_name)
            review = self._reviews.create(
                application_id=application_id,
                reviewer_name=reviewer_name,
                decision=request.decision,
                comments=request.comments,
                rejection_reason=request.rejection_reason,
            )
            corrections_count = self._apply_corrections(
                application_id,
                review.id,
                request,
                reviewer_name,
            )
            status = decision_to_status(request.decision)
            self._applications.update(application, status=status)
            self._record_audit(
                application_id, review.id, request, corrections_count, reviewer_name
            )
        except HumanReviewError:
            raise
        except Exception as exc:
            logger.exception(
                "Review persistence failed for application id=%s",
                application_id,
            )
            raise ReviewPersistenceError() from exc

        checklist_checked = self._count_checked(application_id)
        logger.info(
            "Human review submitted for application id=%s by reviewer=%s: "
            "decision=%s",
            application_id,
            reviewer_name,
            request.decision.value,
        )
        return ReviewSummary(
            application_id=application_id,
            review_id=review.id,
            decision=request.decision,
            reviewer_name=reviewer_name,
            application_status=status.value,
            reviewed_at=review.reviewed_at,
            comments=request.comments,
            rejection_reason=request.rejection_reason,
            corrections_count=corrections_count,
            checklist_checked=checklist_checked,
            checklist_total=len(CHECKLIST_ITEMS),
        )

    def get_history(self, *, application_id: int) -> ReviewHistory:
        """Return the final reviews recorded for an application.

        Args:
            application_id: Id of the application.

        Returns:
            The recorded reviews, most recent first.

        Raises:
            ApplicationNotFound: When the application does not exist.
        """
        self._get_application(application_id)
        reviews = list(self._reviews.get_by_application(application_id))
        return ReviewHistory(
            application_id=application_id,
            reviews=[self._to_review_response(review) for review in reviews],
        )

    # -- Internals ------------------------------------------------------------

    def _get_application(self, application_id: int):
        """Return the application or raise ``ApplicationNotFound``."""
        application = self._applications.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFound()
        return application

    def _document_items(self, documents, ocr_by_document) -> list[ReviewDocumentItem]:
        """Build the review-screen rows for the uploaded documents."""
        items: list[ReviewDocumentItem] = []
        for document in documents:
            ocr = ocr_by_document.get(document.id)
            if ocr is None:
                ocr_status = OCR_STATUS_NOT_PROCESSED
                ocr_confidence = None
                preview = None
            elif ocr.processing_method == ProcessingMethod.PADDLE_OCR.value:
                ocr_status = OCR_STATUS_OCR_PROCESSED
                ocr_confidence = ocr.overall_confidence
                preview = ocr.raw_ocr_text[:OCR_PREVIEW_LENGTH]
            else:
                ocr_status = OCR_STATUS_TEXT_EXTRACTED
                ocr_confidence = ocr.overall_confidence
                preview = ocr.raw_ocr_text[:OCR_PREVIEW_LENGTH]
            items.append(
                ReviewDocumentItem(
                    document_id=document.id,
                    document_type=document.document_type.value,
                    original_filename=document.original_filename,
                    file_type=document.file_type,
                    processing_status=document.processing_status.value,
                    ocr_status=ocr_status,
                    ocr_confidence=ocr_confidence,
                    ocr_text_preview=preview,
                    uploaded_at=document.uploaded_at,
                )
            )
        return items

    def _field_items(
        self,
        fields,
        ocr_document_id: dict[int, int],
        document_map: dict[int, object],
    ) -> list[ReviewFieldItem]:
        """Build the review-screen rows for the extracted fields."""
        items: list[ReviewFieldItem] = []
        for field in fields:
            document_id = ocr_document_id.get(field.ocr_result_id)
            document = document_map.get(document_id) if document_id is not None else None
            items.append(
                ReviewFieldItem(
                    field_name=field.field_name,
                    document_id=document_id or 0,
                    file_name=(
                        document.original_filename
                        if document is not None
                        else "unknown"
                    ),
                    extracted_value=field.extracted_value,
                    normalized_value=field.normalized_value,
                    confidence_score=field.confidence_score,
                    confidence_source=field.confidence_source,
                    verification_status=field.verification_status,
                    human_corrected_value=field.human_corrected_value,
                    human_verified=field.human_verified,
                )
            )
        return items

    def _detection_items(
        self,
        detections,
        document_map: dict[int, object],
    ) -> list[ReviewDetectionItem]:
        """Build the review-screen rows for the visual detections."""
        items: list[ReviewDetectionItem] = []
        for detection in detections:
            document = document_map.get(detection.document_id)
            items.append(
                ReviewDetectionItem(
                    document_id=detection.document_id,
                    document_type=(
                        document.document_type.value
                        if document is not None
                        else "UNKNOWN"
                    ),
                    detection_type=detection.detection_type,
                    is_present=detection.is_present,
                    confidence=detection.confidence,
                    detection_engine=detection.detection_engine,
                    detected_at=detection.detected_at,
                )
            )
        return items

    def _checklist_state(self, application_id: int) -> list[ChecklistItemRead]:
        """Return the current checklist state, defaulting items to unchecked."""
        stored = {
            item.item_name: item
            for item in self._checklist.get_by_application(application_id)
        }
        state: list[ChecklistItemRead] = []
        for name in CHECKLIST_ITEMS:
            item = stored.get(name)
            state.append(
                ChecklistItemRead(
                    item_name=name,
                    is_checked=item.is_checked if item is not None else False,
                    reviewer=item.reviewer if item is not None else None,
                    checked_at=item.checked_at if item is not None else None,
                )
            )
        return state

    def _count_checked(self, application_id: int) -> int:
        """Return the number of checked checklist items for an application."""
        return sum(1 for item in self._checklist_state(application_id) if item.is_checked)

    def _persist_checklist(
        self,
        application_id: int,
        request: HumanReviewRequest,
        reviewer_name: str,
    ) -> None:
        """Store the submitted checklist items with the reviewer."""
        for item in request.checklist:
            self._checklist.upsert(
                application_id=application_id,
                item_name=item.item_name,
                is_checked=item.is_checked,
                reviewer=reviewer_name if item.is_checked else None,
            )

    def _apply_corrections(
        self,
        application_id: int,
        review_id: int,
        request: HumanReviewRequest,
        reviewer_name: str,
    ) -> int:
        """Store corrections, updating fields and feedback when values change.

        Each correction is recorded in ``human_corrections`` for the audit
        trail. When a matching extracted field exists and the corrected value
        differs from the stored value, the field's human-corrected state is
        updated and a feedback-dataset sample is recorded so ground truth is
        never duplicated for an unchanged value.

        A correction carrying a ``document_id`` matches only the field
        extracted from that document, so two documents on the same
        application extracting a same-named field can be corrected
        independently. A correction without one falls back to matching by
        field name alone, same as before ``document_id`` existed.

        Returns:
            The number of corrections stored.
        """
        if not request.corrections:
            return 0
        all_fields = list(self._fields.get_by_application(application_id))
        fields_by_key = {
            (field.ocr_result.document_id, field.field_name): field for field in all_fields
        }
        fields_by_name = {field.field_name: field for field in all_fields}
        for correction in request.corrections:
            if correction.document_id is not None:
                field = fields_by_key.get((correction.document_id, correction.field_name))
            else:
                field = fields_by_name.get(correction.field_name)
            current = (
                field.human_corrected_value or field.extracted_value
                if field is not None
                else None
            )
            original_value = current
            self._corrections.create(
                review_id=review_id,
                field_name=correction.field_name,
                corrected_value=correction.corrected_value,
                document_id=correction.document_id,
                original_value=original_value,
                reason=correction.reason,
            )
            if field is not None and correction.corrected_value != current:
                field.human_corrected_value = correction.corrected_value
                field.human_verified = True
                field.reviewer = reviewer_name
                field.reviewed_at = datetime.now(UTC)
                self._feedback.create(
                    application_id=application_id,
                    field_name=correction.field_name,
                    human_value=correction.corrected_value,
                    ocr_value=field.extracted_value,
                    confidence_score=field.confidence_score,
                    document_id=field.ocr_result.document_id,
                    ocr_result_id=field.ocr_result_id,
                    normalized_value=field.normalized_value,
                    confidence_source=field.confidence_source,
                    correction_reason=correction.reason,
                    reviewer=reviewer_name,
                    decision=request.decision.value,
                    origin=ORIGIN_FINAL_HUMAN_REVIEW,
                )
                logger.info(
                    "Field %s corrected for application id=%s "
                    "(feedback recorded)",
                    correction.field_name,
                    application_id,
                )
        return len(request.corrections)

    def _record_audit(
        self,
        application_id: int,
        review_id: int,
        request: HumanReviewRequest,
        corrections_count: int,
        reviewer_name: str,
    ) -> None:
        """Write the audit entries for a submitted review."""
        self._audit.create(
            application_id=application_id,
            username=reviewer_name,
            action=ACTION_REVIEW_SUBMITTED,
            details={
                "decision": request.decision.value,
                "review_id": review_id,
                "version": REVIEW_VERSION,
            },
        )
        if request.decision is ReviewDecision.APPROVE:
            action = ACTION_APPLICATION_APPROVED
            details: dict[str, object] = {"review_id": review_id}
        elif request.decision is ReviewDecision.CORRECT:
            action = ACTION_APPLICATION_CORRECTED
            details = {"review_id": review_id, "corrections": corrections_count}
        else:
            action = ACTION_APPLICATION_REJECTED
            details = {
                "review_id": review_id,
                "rejection_reason": request.rejection_reason,
            }
        self._audit.create(
            application_id=application_id,
            username=reviewer_name,
            action=action,
            details=details,
        )
        if request.decision is ReviewDecision.APPROVE:
            self._audit.create(
                application_id=application_id,
                username=reviewer_name,
                action=ACTION_CHECKLIST_COMPLETED,
                details={"review_id": review_id, "total": len(CHECKLIST_ITEMS)},
            )
            logger.info(
                "Checklist completed for application id=%s by reviewer=%s: "
                "%s/%s items",
                application_id,
                reviewer_name,
                len(CHECKLIST_ITEMS),
                len(CHECKLIST_ITEMS),
            )
        logger.info(
            "Audit record created for application id=%s action=%s",
            application_id,
            action,
        )

    def _latest_review(self, application_id: int) -> HumanReviewResponse | None:
        """Return the most recent review for an application, if any."""
        reviews = list(self._reviews.get_by_application(application_id))
        if not reviews:
            return None
        return self._to_review_response(reviews[0])

    def _to_review_response(self, review) -> HumanReviewResponse:
        """Serialize a stored review with its corrections and checklist."""
        corrections = [
            CorrectionItemRead.model_validate(correction)
            for correction in self._corrections.get_by_review(review.id)
        ]
        return HumanReviewResponse(
            review_id=review.id,
            application_id=review.application_id,
            decision=review.decision,
            reviewer_name=review.reviewer_name,
            comments=review.comments,
            rejection_reason=review.rejection_reason,
            reviewed_at=review.reviewed_at,
            checklist_checked=self._count_checked(review.application_id),
            checklist_total=len(CHECKLIST_ITEMS),
            corrections=corrections,
        )


__all__ = ["HumanVerificationService"]

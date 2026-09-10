"""Report aggregation service.

``ValidationReportService`` is read-only: it loads what earlier pipeline stages
persisted (documents, OCR results, extracted fields, validation results,
visual detections, analysis results), aggregates it into the structured report,
derives the overall status from the stored validation results and builds the
deterministic recommendation list. It never runs a rule, never runs a
detection and never writes to the database.

The HTML report is rendered from a Jinja2 template in ``app/templates``. The
same JSON model that the ``validation-report`` endpoint returns is passed to
the template, so a future PDF exporter can consume either the model or the
rendered HTML without the report logic changing.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from app.completeness.services import CompletenessService
from app.confidence.constants import FieldVerificationStatus
from app.database.models.enums import DocumentType, ValidationStatus
from app.document_processing.constants import ProcessingMethod
from app.reports.constants import (
    BLUR_MESSAGE_MARKER,
    DOCUMENT_TYPE_BY_RULE,
    DUPLICATE_MESSAGE_MARKER,
    REPORT_GROUP_ORDER,
    REPORT_VERSION,
    TECHNICAL_VALIDATION_CATEGORY,
    VISUAL_TYPE_BY_RULE,
    ReportOverallStatus,
)
from app.reports.exceptions import (
    ApplicationNotFound,
    ReportGenerationFailed,
)
from app.reports.repositories import (
    ApplicationRepository,
    DocumentAnalysisRepository,
    DocumentRepository,
    ExtractedFieldRepository,
    OCRRepository,
    ValidationRepository,
    VisualDetectionRepository,
)
from app.reports.schemas import (
    ReportApplicationInfo,
    ReportDocumentItem,
    ReportExtractionSummary,
    ReportRecommendation,
    ReportRuleCategorySummary,
    ReportRuleSummary,
    ReportVisualDetectionSummary,
    ValidationReport,
    ValidationSummary,
)
from app.reports.validators import (
    build_recommendations,
    derive_overall_status,
    group_label,
)
from app.rule_engine.constants import (
    CONFIDENCE_FLOOR,
    RULE_CATEGORY_KEYS,
    SIGNATURE_DETECTION,
    STAMP_DETECTION,
)

logger = logging.getLogger(__name__)

#: Directory holding the report's HTML templates (``backend/app/templates``).
_TEMPLATES_DIR: Path = Path(__file__).resolve().parent.parent / "templates"

#: Shared Jinja2 environment; templates are loaded from disk per render.
_environment = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


class ValidationReportService:
    """Aggregate stored validation data into a report for employee review.

    Args:
        db: Active database session.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._applications = ApplicationRepository(db)
        self._documents = DocumentRepository(db)
        self._ocr_results = OCRRepository(db)
        self._fields = ExtractedFieldRepository(db)
        self._validation = ValidationRepository(db)
        self._detections = VisualDetectionRepository(db)
        self._analysis = DocumentAnalysisRepository(db)

    # -- Public API -----------------------------------------------------------

    def get_report(self, *, application_id: int) -> ValidationReport:
        """Generate the full validation report for an application.

        Args:
            application_id: Id of the application.

        Returns:
            The structured validation report.

        Raises:
            ApplicationNotFound: When the application does not exist.
            ReportGenerationFailed: When aggregation or rendering fails.
        """
        logger.info("Report generation started for application id=%s", application_id)
        try:
            report = self._build_report(application_id)
        except ApplicationNotFound:
            raise
        except Exception as exc:
            logger.exception(
                "Report generation failed for application id=%s",
                application_id,
            )
            raise ReportGenerationFailed() from exc
        logger.info(
            "Report generation completed for application id=%s: "
            "overall_status=%s rules=%s recommendations=%s",
            application_id,
            report.overall_status,
            report.rule_summary.total,
            len(report.recommendations),
        )
        return report

    def get_summary(self, *, application_id: int) -> ValidationSummary:
        """Generate the condensed validation summary for an application.

        Args:
            application_id: Id of the application.

        Returns:
            The condensed report with headline totals.

        Raises:
            ApplicationNotFound: When the application does not exist.
            ReportGenerationFailed: When aggregation fails.
        """
        logger.info("Summary generation started for application id=%s", application_id)
        try:
            report = self._build_report(application_id)
        except ApplicationNotFound:
            raise
        except Exception as exc:
            logger.exception(
                "Summary generation failed for application id=%s",
                application_id,
            )
            raise ReportGenerationFailed() from exc
        summary = ValidationSummary(
            application_id=report.application_id,
            report_version=report.report_version,
            generated_at=datetime.now(UTC),
            overall_status=report.overall_status,
            application_status=report.application.status,
            document_count=len(report.document_summary),
            rule_total=report.rule_summary.total,
            rule_passed=report.rule_summary.passed,
            rule_failed=report.rule_summary.failed,
            rule_warnings=report.rule_summary.warnings,
            rule_pending_review=report.rule_summary.pending_manual_review,
            field_count=report.extraction_summary.total_fields,
            overall_confidence=report.extraction_summary.overall_confidence,
            recommendation_count=len(report.recommendations),
        )
        logger.info(
            "Summary generated for application id=%s: overall_status=%s",
            application_id,
            summary.overall_status,
        )
        return summary

    def render_html(self, *, application_id: int) -> str:
        """Render the printable HTML report for an application.

        Args:
            application_id: Id of the application.

        Returns:
            The rendered HTML document.

        Raises:
            ApplicationNotFound: When the application does not exist.
            ReportGenerationFailed: When rendering fails.
        """
        report = self.get_report(application_id=application_id)
        application = self._get_application(application_id)

        completeness = None
        try:
            completeness = CompletenessService(self._db).get_report(
                application_id=application_id,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "Completeness report unavailable for application id=%s",
                application_id,
            )

        doc_labels = {
            DocumentType.AUTHORITY_LETTER: "Authority Letter",
            DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE: "Account Maintenance Certificate",
            DocumentType.ONE_LINK_LETTER: "1-Link Application Form",
            DocumentType.TRIPARTITE_AGREEMENT: "Tripartite Agreement",
            DocumentType.BUSINESS_REQUIREMENT_DOCUMENT: "Onboarding / Business Requirement Document",
            DocumentType.BILATERAL_AGREEMENT: "Bilateral / Business Agreement",
            DocumentType.CNIC_FRONT: "CNIC (Front & Back)",
            DocumentType.CNIC_BACK: "CNIC (Front & Back)",
            DocumentType.FORMAL_REQUEST_LETTER: "Formal Request Letter",
            DocumentType.SCHEDULE_OF_CHARGES: "Schedule of Charges / Bilateral",
        }

        required_copies = {
            DocumentType.AUTHORITY_LETTER: 1,
            DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE: 1,
            DocumentType.ONE_LINK_LETTER: 3,
            DocumentType.TRIPARTITE_AGREEMENT: 3,
            DocumentType.BUSINESS_REQUIREMENT_DOCUMENT: 1,
            DocumentType.BILATERAL_AGREEMENT: 1,
            DocumentType.CNIC_FRONT: 2,
            DocumentType.CNIC_BACK: 2,
            DocumentType.FORMAL_REQUEST_LETTER: 1,
        }

        try:
            from app.human_verification.comment_defaults import (
                resolve_reviewer_comment,
            )
            template = _environment.get_template("validation_report.html")
            reviewer_comment = resolve_reviewer_comment(
                saved=application.reviewer_comments,
                status=application.status,
            )
            html = template.render(
                report=report,
                completeness=completeness,
                doc_labels=doc_labels,
                required_copies=required_copies,
                reviewer_comment=reviewer_comment,
            )
        except Exception as exc:
            logger.exception(
                "HTML report generation failed for application id=%s",
                application_id,
            )
            raise ReportGenerationFailed() from exc
        logger.info("HTML report generated for application id=%s", application_id)
        return html

    def render_pdf(self, *, application_id: int) -> bytes:
        """Render the printable HTML report as a PDF document.

        Reuses the same Jinja2 template and context as ``render_html`` so
        the PDF and HTML reports are always consistent.  Uses WeasyPrint
        for HTML-to-PDF conversion with full CSS support.

        Args:
            application_id: Id of the application.

        Returns:
            The PDF document as raw bytes.

        Raises:
            ApplicationNotFound: When the application does not exist.
            ReportGenerationFailed: When PDF rendering fails.
        """
        try:
            from weasyprint import HTML as WeasyHTML
        except ImportError as exc:
            logger.exception("WeasyPrint not installed")
            raise ReportGenerationFailed() from exc

        html = self.render_html(application_id=application_id)
        try:
            pdf_bytes = WeasyHTML(string=html).write_pdf()
        except Exception as exc:
            logger.exception(
                "PDF report generation failed for application id=%s",
                application_id,
            )
            raise ReportGenerationFailed() from exc
        logger.info("PDF report generated for application id=%s", application_id)
        return pdf_bytes

    # -- Internals ------------------------------------------------------------

    def _get_application(self, application_id: int):
        """Return the application or raise ``ApplicationNotFound``."""
        application = self._applications.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFound()
        return application

    def _build_report(self, application_id: int) -> ValidationReport:
        """Assemble the full report from the stored data of an application."""
        application = self._get_application(application_id)
        documents = list(self._documents.get_all_by_application(application_id))
        ocr_by_document = {
            ocr_result.document_id: ocr_result
            for ocr_result in self._ocr_results.get_by_application(application_id)
        }
        analysis_by_document = {
            result.document_id: result
            for result in self._analysis.get_by_application(application_id)
        }
        fields = list(self._fields.get_by_application(application_id))
        detections = list(self._detections.get_by_application(application_id))
        rule_rows = list(
            self._validation.get_by_application_and_categories(
                application_id,
                RULE_CATEGORY_KEYS,
            )
        )
        technical_rows = list(
            self._validation.get_by_application_and_categories(
                application_id,
                {TECHNICAL_VALIDATION_CATEGORY},
            )
        )

        document_summary = [
            self._document_item(
                document,
                ocr_by_document.get(document.id),
                analysis_by_document.get(document.id),
                technical_rows,
            )
            for document in documents
        ]
        extraction_summary = self._extraction_summary(fields)
        rule_summary = self._rule_summary(rule_rows)
        visual_summary = self._visual_summary(detections)
        has_failure = any(
            row.status is ValidationStatus.FAIL
            for row in rule_rows + technical_rows
        )
        # No stored rule rows at all means business validation hasn't run yet
        # (e.g. the application is still missing required documents and never
        # reached the rule engine) -- treated the same as "pending manual
        # review" so derive_overall_status below can never call an
        # unvalidated application APPROVED. Previously this case raised
        # NoValidationResults (a 422) and blocked the report entirely, which
        # meant the printable report couldn't show completeness/missing-
        # document status until the pipeline finished -- exactly backwards
        # for what this report needs to do for an incomplete application.
        has_pending = not rule_rows or any(
            row.status is ValidationStatus.PENDING_MANUAL_REVIEW
            for row in rule_rows
        )
        overall_status = derive_overall_status(
            application_status=application.status.value,
            has_failure=has_failure,
            has_pending_review=has_pending,
        )
        findings = self._findings(
            rule_rows=rule_rows,
            technical_rows=technical_rows,
            fields=fields,
            has_pending=has_pending,
            overall_status=overall_status,
        )
        recommendations = [
            ReportRecommendation(**item)
            for item in build_recommendations(findings)
        ]

        return ValidationReport(
            application_id=application.id,
            report_version=REPORT_VERSION,
            generated_at=datetime.now(UTC),
            application=ReportApplicationInfo(
                application_id=application.id,
                name=application.name,
                status=application.status.value,
                submitted_at=application.submitted_at,
                updated_at=application.updated_at,
                created_by=application.created_by,
            ),
            overall_status=overall_status.value,
            document_summary=document_summary,
            extraction_summary=extraction_summary,
            rule_summary=rule_summary,
            visual_detection_summary=visual_summary,
            recommendations=recommendations,
        )

    def _document_item(self, document, ocr_result, analysis_result, technical_rows):
        """Build the per-document summary row."""
        if ocr_result is None:
            ocr_status = "NOT_PROCESSED"
            ocr_confidence = None
        elif ocr_result.processing_method == ProcessingMethod.PADDLE_OCR.value:
            ocr_status = "OCR_PROCESSED"
            ocr_confidence = ocr_result.overall_confidence
        else:
            ocr_status = "TEXT_EXTRACTED"
            ocr_confidence = ocr_result.overall_confidence

        document_technical = [
            row for row in technical_rows if row.document_id == document.id
        ]
        if not document_technical:
            technical_status = "NOT_VALIDATED"
        elif any(
            row.status is ValidationStatus.FAIL for row in document_technical
        ):
            technical_status = "FAILED"
        else:
            technical_status = "PASS"

        return ReportDocumentItem(
            document_id=document.id,
            document_type=document.document_type.value,
            processing_status=document.processing_status.value,
            ocr_status=ocr_status,
            ocr_confidence=ocr_confidence,
            technical_validation_status=technical_status,
            analysis_status=(
                analysis_result.verification_status if analysis_result else "NOT_ANALYZED"
            ),
        )

    def _extraction_summary(self, fields) -> ReportExtractionSummary:
        """Tally the per-field verification outcomes."""
        auto_verified = sum(
            1
            for field in fields
            if field.verification_status == FieldVerificationStatus.AUTO_VERIFIED.value
        )
        human_corrected = sum(
            1
            for field in fields
            if field.verification_status == FieldVerificationStatus.CORRECTED.value
            or field.human_corrected_value
        )
        pending_review = sum(
            1
            for field in fields
            if field.verification_status == FieldVerificationStatus.PENDING_REVIEW.value
        )
        cannot_verify = sum(
            1
            for field in fields
            if field.verification_status == FieldVerificationStatus.CANNOT_VERIFY.value
        )
        confidences = [
            field.confidence_score
            for field in fields
            if field.confidence_score is not None
        ]
        overall_confidence = (
            round(sum(confidences) / len(confidences), 4) if confidences else None
        )
        return ReportExtractionSummary(
            total_fields=len(fields),
            auto_verified=auto_verified,
            human_corrected=human_corrected,
            pending_review=pending_review,
            cannot_verify=cannot_verify,
            overall_confidence=overall_confidence,
        )

    def _rule_summary(self, rule_rows) -> ReportRuleSummary:
        """Tally the business rule rows overall and per report group."""
        group_totals: dict[str, dict[str, int]] = {
            label: _empty_totals() for label in REPORT_GROUP_ORDER
        }
        overall = _empty_totals()
        for row in rule_rows:
            label = group_label(row.rule_category, row.rule_id)
            if label not in group_totals:
                group_totals[label] = _empty_totals()
            _tally(group_totals[label], row.status)
            _tally(overall, row.status)
        return ReportRuleSummary(
            total=overall["total"],
            passed=overall["passed"],
            failed=overall["failed"],
            warnings=overall["warnings"],
            pending_manual_review=overall["pending_manual_review"],
            by_category=[
                ReportRuleCategorySummary(
                    category=label,
                    total=group_totals[label]["total"],
                    passed=group_totals[label]["passed"],
                    failed=group_totals[label]["failed"],
                    warnings=group_totals[label]["warnings"],
                    pending_manual_review=group_totals[label]["pending_manual_review"],
                )
                for label in REPORT_GROUP_ORDER
            ],
        )

    def _visual_summary(self, detections) -> ReportVisualDetectionSummary:
        """Tally the stored visual detection outcomes."""
        signature_present = signature_missing = 0
        stamp_present = stamp_missing = 0
        confidences = [
            detection.confidence
            for detection in detections
            if detection.confidence is not None
        ]
        for detection in detections:
            if detection.detection_type == SIGNATURE_DETECTION:
                if detection.is_present:
                    signature_present += 1
                else:
                    signature_missing += 1
            elif detection.detection_type == STAMP_DETECTION:
                if detection.is_present:
                    stamp_present += 1
                else:
                    stamp_missing += 1
        return ReportVisualDetectionSummary(
            documents_checked=len({detection.document_id for detection in detections}),
            signature_detected=signature_present,
            signature_missing=signature_missing,
            stamp_detected=stamp_present,
            stamp_missing=stamp_missing,
            average_confidence=(
                round(sum(confidences) / len(confidences), 4) if confidences else None
            ),
        )

    def _findings(
        self,
        *,
        rule_rows,
        technical_rows,
        fields,
        has_pending: bool,
        overall_status: ReportOverallStatus,
    ) -> dict:
        """Compute the recommendation triggers from the stored data."""
        failed_rules = {row.rule_id for row in rule_rows if row.status is ValidationStatus.FAIL}
        failed_document_messages = {
            row.rule_id: row.message
            for row in rule_rows
            if row.status is ValidationStatus.FAIL and row.rule_id in DOCUMENT_TYPE_BY_RULE
        }
        date_failures = any(
            row.rule_category == "date" and row.status is ValidationStatus.FAIL
            for row in rule_rows
        )
        blurred_documents = [
            row.document_id
            for row in technical_rows
            if row.status is ValidationStatus.FAIL
            and row.message
            and BLUR_MESSAGE_MARKER in row.message
            and row.document_id is not None
        ]
        low_confidence = any(
            field.confidence_score is not None
            and field.confidence_score < CONFIDENCE_FLOOR
            for field in fields
        ) or any(
            field.verification_status
            in (
                FieldVerificationStatus.PENDING_REVIEW.value,
                FieldVerificationStatus.CANNOT_VERIFY.value,
            )
            for field in fields
        )
        return {
            "missing_document_types": [
                DOCUMENT_TYPE_BY_RULE[rule_id]
                for rule_id, message in failed_document_messages.items()
                if not (message and DUPLICATE_MESSAGE_MARKER in message)
            ],
            "duplicate_document_types": [
                DOCUMENT_TYPE_BY_RULE[rule_id]
                for rule_id, message in failed_document_messages.items()
                if message and DUPLICATE_MESSAGE_MARKER in message
            ],
            "missing_signature_documents": [
                VISUAL_TYPE_BY_RULE[rule_id]
                for rule_id in failed_rules
                if rule_id in VISUAL_TYPE_BY_RULE
                and rule_id.startswith("VIS_SIGNATURE_")
            ],
            "missing_stamp_documents": [
                VISUAL_TYPE_BY_RULE[rule_id]
                for rule_id in failed_rules
                if rule_id in VISUAL_TYPE_BY_RULE
                and rule_id.startswith("VIS_STAMP_")
            ],
            "iban_inconsistent": "CROSS_IBAN_MATCH" in failed_rules,
            "holder_inconsistent": "CROSS_ACCOUNT_HOLDER_MATCH" in failed_rules,
            "account_number_inconsistent": "CROSS_ACCOUNT_NUMBER_MATCH" in failed_rules,
            "period_inconsistent": "CROSS_PERIOD_MATCH" in failed_rules,
            "reconciliation_failed": "POL_BALANCE_RECONCILIATION" in failed_rules,
            "blurred_documents": blurred_documents,
            "low_confidence": low_confidence,
            "date_failures": date_failures,
            "pending_review": has_pending,
            "approved": overall_status is ReportOverallStatus.APPROVED,
        }


def _empty_totals() -> dict[str, int]:
    """Return a zeroed per-group tally dict."""
    return {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "warnings": 0,
        "pending_manual_review": 0,
    }


def _tally(totals: dict[str, int], status) -> None:
    """Increment ``totals`` for one validation status."""
    totals["total"] += 1
    if status is ValidationStatus.PASS:
        totals["passed"] += 1
    elif status is ValidationStatus.FAIL:
        totals["failed"] += 1
    elif status is ValidationStatus.WARNING:
        totals["warnings"] += 1
    elif status is ValidationStatus.PENDING_MANUAL_REVIEW:
        totals["pending_manual_review"] += 1

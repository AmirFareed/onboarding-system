"""Technical file validation service.

Validates every stored document of an application for technical suitability
(accessibility, format, PDF/image structure, blur, rotation and readability) and
persists one :class:`ValidationResult` row per check, reusing the Phase 2
validation results table. The service never inspects document meaning and never
performs OCR. Reports can be produced from a fresh run (``validate``) or
reconstructed from the stored check rows (``get_reports``); both paths share the
same derivation logic so a stored report always matches a fresh one.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import cv2
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.models.document import Document
from app.database.models.enums import Severity, ValidationStatus
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.validation_repository import ValidationRepository
from app.technical_validation.constants import (
    BLUR_THRESHOLD,
    CHECK_BLANK_PAGE,
    CHECK_BLUR,
    CHECK_FILE_EXISTS,
    CHECK_FILE_NOT_EMPTY,
    CHECK_FILE_READABLE,
    CHECK_FILE_TYPE,
    CHECK_IMAGE_LOAD,
    CHECK_IMAGE_RESOLUTION,
    CHECK_PDF_DIMENSIONS,
    CHECK_PDF_OPEN,
    CHECK_PDF_PAGES,
    CHECK_PDF_PASSWORD,
    CHECK_PDF_RENDER,
    CHECK_READABILITY,
    CHECK_ROTATION,
    MIN_IMAGE_HEIGHT,
    MIN_IMAGE_WIDTH,
    ROTATION_TOLERANCE_DEGREES,
    SEVERITY_FAIL,
    SEVERITY_PASS,
    SEVERITY_WARNING,
    TECHNICAL_VALIDATION_RULE_CATEGORY,
    FileFormat,
    ReadabilityStatus,
    RotationStatus,
)
from app.technical_validation.exceptions import (
    ApplicationNotFound,
    CorruptedPDF,
    EmptyFile,
    FileNotFound,
    FileUnreadable,
    InvalidImage,
    PasswordProtectedPDF,
    TechnicalValidationFailed,
    UnsupportedFileFormat,
)
from app.technical_validation.schemas import (
    TechnicalValidationListResponse,
    TechnicalValidationReport,
)
from app.technical_validation.utils import (
    estimate_rotation_angle,
    is_blank_image,
    render_pdf_first_page,
    variance_of_laplacian,
)
from app.technical_validation.validators import (
    detect_format,
    validate_file_not_empty,
    validate_file_present,
    validate_file_readable,
    validate_image,
    validate_pdf,
)
from app.upload.exceptions import StorageException
from app.upload.storage import StorageService

logger = logging.getLogger(__name__)

#: Human-readable name of every technical check, keyed by rule id.
_CHECK_NAMES: dict[str, str] = {
    CHECK_FILE_EXISTS: "File exists",
    CHECK_FILE_READABLE: "File is readable",
    CHECK_FILE_NOT_EMPTY: "File is not empty",
    CHECK_FILE_TYPE: "File type is supported",
    CHECK_PDF_OPEN: "PDF can be opened",
    CHECK_PDF_PASSWORD: "PDF is not password protected",
    CHECK_PDF_PAGES: "PDF has at least one page",
    CHECK_PDF_DIMENSIONS: "PDF page dimensions are valid",
    CHECK_PDF_RENDER: "PDF page can be rendered",
    CHECK_IMAGE_LOAD: "Image loads successfully",
    CHECK_IMAGE_RESOLUTION: "Image resolution meets minimum",
    CHECK_BLUR: "Image is not blurry",
    CHECK_ROTATION: "Document is not rotated",
    CHECK_BLANK_PAGE: "Page is not blank",
    CHECK_READABILITY: "Document readability",
}

#: Actionable recommendation per failed or warning check name.
_RECOMMENDATIONS: dict[str, str] = {
    "File exists": "Ensure the document's file is present in storage and re-upload the document",
    "File is readable": "Ensure the document's file is readable and re-upload the document",
    "File is not empty": "Re-upload the document with its full content",
    "File type is supported": "Provide the document as a PDF, JPEG or PNG file",
    "PDF can be opened": "Upload an undamaged PDF document",
    "PDF is not password protected": "Upload the PDF without password protection",
    "PDF has at least one page": "Upload a PDF that contains at least one page",
    "PDF page dimensions are valid": "Re-generate the PDF with valid page dimensions",
    "PDF page can be rendered": "Re-upload the PDF so its pages can be rendered",
    "Image loads successfully": "Re-scan or re-export the document as a valid image",
    "Image resolution meets minimum": (
        f"Re-scan the document at a resolution of at least "
        f"{MIN_IMAGE_WIDTH}x{MIN_IMAGE_HEIGHT} pixels"
    ),
    "Image is not blurry": "Re-scan the document so the image is in focus",
    "Document is not rotated": "Re-scan the document so its content is oriented upright",
    "Page is not blank": "Re-scan the document so the page contains content",
}

#: Rule ids that make up the PDF structural checks.
_PDF_RULE_IDS: frozenset[str] = frozenset(
    {
        CHECK_PDF_OPEN,
        CHECK_PDF_PASSWORD,
        CHECK_PDF_PAGES,
        CHECK_PDF_DIMENSIONS,
    }
)

#: Rule ids that make up the image validity checks.
_IMAGE_RULE_IDS: frozenset[str] = frozenset(
    {CHECK_IMAGE_LOAD, CHECK_IMAGE_RESOLUTION}
)

#: Rule ids that make up the file accessibility checks.
_ACCESSIBILITY_RULE_IDS: frozenset[str] = frozenset(
    {CHECK_FILE_EXISTS, CHECK_FILE_READABLE, CHECK_FILE_NOT_EMPTY}
)


@dataclass
class _Check:
    """In-memory representation of one technical check before persistence.

    Attributes:
        rule_id: Opaque identifier of the check.
        rule_name: Human-readable check name.
        status: Resolution state of the check.
        severity: Importance level derived from the status.
        message: Explanation of the outcome.
        blur_score: Sharpness score for the blur check.
        rotation_angle: Rotation estimate for the rotation check.
        file_format: Detected format label for the file-type check.
    """

    rule_id: str
    rule_name: str
    status: ValidationStatus
    severity: Severity
    message: str | None
    blur_score: float | None = None
    rotation_angle: float | None = None
    file_format: str | None = None


def _pass_check(rule_id: str, message: str | None = None) -> _Check:
    """Build a passed check record for ``rule_id``."""
    return _Check(
        rule_id=rule_id,
        rule_name=_CHECK_NAMES[rule_id],
        status=ValidationStatus.PASS,
        severity=SEVERITY_PASS,
        message=message,
    )


def _fail_check(rule_id: str, message: str | None = None) -> _Check:
    """Build a failed check record for ``rule_id``."""
    return _Check(
        rule_id=rule_id,
        rule_name=_CHECK_NAMES[rule_id],
        status=ValidationStatus.FAIL,
        severity=SEVERITY_FAIL,
        message=message,
    )


def _warn_check(rule_id: str, message: str | None = None) -> _Check:
    """Build a warning check record for ``rule_id``."""
    return _Check(
        rule_id=rule_id,
        rule_name=_CHECK_NAMES[rule_id],
        status=ValidationStatus.WARNING,
        severity=SEVERITY_WARNING,
        message=message,
    )


def _format_label(document: Document) -> str:
    """Return a display label for a document's format from its stored path.

    Args:
        document: Document whose stored path determines the label.

    Returns:
        The uppercased extension (e.g. ``PDF``, ``TIFF``) or ``UNKNOWN``.
    """
    suffix = Path(document.stored_file_path).suffix.lower().lstrip(".")
    return suffix.upper() or "UNKNOWN"


def _derive_readability(checks: list[_Check]) -> ReadabilityStatus:
    """Derive the overall readability from the individual checks.

    Any failed check makes the document unreadable; any warning (a rotated
    document) makes it partially readable; otherwise it is readable.

    Args:
        checks: Every technical check performed for the document.

    Returns:
        The derived :class:`ReadabilityStatus`.
    """
    non_aggregate = [check for check in checks if check.rule_id != CHECK_READABILITY]
    if any(check.status is ValidationStatus.FAIL for check in non_aggregate):
        return ReadabilityStatus.UNREADABLE
    if any(check.status is ValidationStatus.WARNING for check in non_aggregate):
        return ReadabilityStatus.PARTIALLY_READABLE
    return ReadabilityStatus.READABLE


def _derive_overall_status(checks: list[_Check]) -> ValidationStatus:
    """Derive the overall validation status from the individual checks.

    Args:
        checks: Every technical check performed for the document.

    Returns:
        ``FAIL`` when any check failed, else ``WARNING`` when any check warned,
        else ``PASS``.
    """
    if any(check.status is ValidationStatus.FAIL for check in checks):
        return ValidationStatus.FAIL
    if any(check.status is ValidationStatus.WARNING for check in checks):
        return ValidationStatus.WARNING
    return ValidationStatus.PASS


def _derive_recommendations(
    failed_checks: list[str],
    warnings: list[str],
) -> list[str]:
    """Map the failing and warning check names onto actionable guidance.

    Args:
        failed_checks: Names of the failed checks.
        warnings: Names of the warning checks.

    Returns:
        Deduplicated recommendations, or a single "suitable for processing"
        recommendation when nothing needs attention.
    """
    recommendations: list[str] = []
    for name in [*failed_checks, *warnings]:
        recommendation = _RECOMMENDATIONS.get(name)
        if recommendation and recommendation not in recommendations:
            recommendations.append(recommendation)
    if not recommendations:
        recommendations.append("Document is technically suitable for processing")
    return recommendations


def _build_report(
    application_id: int,
    document: Document,
    checks: list[_Check],
    validated_at: datetime,
) -> TechnicalValidationReport:
    """Assemble a report from the checks performed for one document.

    Args:
        application_id: Application the document belongs to.
        document: Validated document metadata.
        checks: Technical checks performed for the document.
        validated_at: Timestamp of the validation run.

    Returns:
        The serialized technical validation report.
    """
    failed_checks = [
        check.rule_name
        for check in checks
        if check.status is ValidationStatus.FAIL and check.rule_id != CHECK_READABILITY
    ]
    warnings = [
        check.rule_name
        for check in checks
        if check.status is ValidationStatus.WARNING and check.rule_id != CHECK_READABILITY
    ]
    rotation = _value_from(checks, CHECK_ROTATION)
    return TechnicalValidationReport(
        application_id=application_id,
        document_id=document.id,
        file_name=document.original_filename,
        file_type=_format_label(document),
        validation_timestamp=validated_at,
        validation_status=_derive_overall_status(checks),
        file_accessible=_checks_pass(checks, _ACCESSIBILITY_RULE_IDS),
        file_type_valid=_checks_pass(checks, {CHECK_FILE_TYPE}),
        pdf_valid=_checks_pass_or_none(checks, _PDF_RULE_IDS),
        image_valid=_checks_pass_or_none(checks, _IMAGE_RULE_IDS),
        blur_score=_value_from(checks, CHECK_BLUR, "blur_score"),
        rotation_angle=_value_from(checks, CHECK_ROTATION, "rotation_angle"),
        rotation_status=(
            RotationStatus.ROTATED
            if rotation is not None and rotation.status is ValidationStatus.WARNING
            else RotationStatus.NOT_ROTATED
        ),
        readability_status=_derive_readability(checks),
        failed_checks=failed_checks,
        warnings=warnings,
        recommendations=_derive_recommendations(failed_checks, warnings),
    )


def _checks_pass(checks: list[_Check], rule_ids: frozenset[str]) -> bool:
    """Return whether every present check of ``rule_ids`` passed.

    Args:
        checks: Technical checks performed for the document.
        rule_ids: Rule ids that make up the grouped check.

    Returns:
        ``False`` when no matching check exists or any of them failed/warned.
    """
    matching = [check for check in checks if check.rule_id in rule_ids]
    return bool(matching) and all(
        check.status is ValidationStatus.PASS for check in matching
    )


def _checks_pass_or_none(
    checks: list[_Check],
    rule_ids: frozenset[str],
) -> bool | None:
    """Return whether every check of ``rule_ids`` passed, or ``None``.

    ``None`` indicates the group does not apply to this document (e.g. the PDF
    checks for an image document).

    Args:
        checks: Technical checks performed for the document.
        rule_ids: Rule ids that make up the grouped check.

    Returns:
        ``None`` when no matching check exists, otherwise whether all passed.
    """
    matching = [check for check in checks if check.rule_id in rule_ids]
    if not matching:
        return None
    return all(check.status is ValidationStatus.PASS for check in matching)


def _value_from(
    checks: list[_Check],
    rule_id: str,
    attribute: str | None = None,
) -> float | None:
    """Return the value of ``attribute`` from the check with ``rule_id``.

    Args:
        checks: Technical checks performed for the document.
        rule_id: Rule id whose check carries the value.
        attribute: Check attribute to read; the check itself when ``None``.

    Returns:
        The attribute value, or ``None`` when no such check exists.
    """
    for check in checks:
        if check.rule_id == rule_id:
            return getattr(check, attribute) if attribute else check
    return None


class TechnicalValidationService:
    """Runs technical validation and reads stored validation reports.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._storage = StorageService(get_settings().upload_storage_root)
        self._applications = ApplicationRepository(db)
        self._documents = DocumentRepository(db)
        self._validation = ValidationRepository(db)

    def validate(self, *, application_id: int) -> TechnicalValidationListResponse:
        """Run technical validation for every document of an application.

        Each document is validated independently; a document-level failure is
        captured inside its own report and never aborts the run. Every check is
        persisted as a :class:`ValidationResult` row sharing the run timestamp.

        Args:
            application_id: Id of the application to validate.

        Returns:
            The complete technical validation report for the application.

        Raises:
            ApplicationNotFound: When the application does not exist.
            TechnicalValidationFailed: When the run fails unexpectedly.
        """
        application = self._get_application(application_id)
        documents = list(
            self._documents.get_all_by_application(application_id)
        )
        logger.info(
            "Technical validation started for application id=%s (%s documents)",
            application.id,
            len(documents),
        )
        run_at = datetime.now(UTC)
        reports: list[TechnicalValidationReport] = []
        try:
            for document in documents:
                logger.info(
                    "Technical validation started for document id=%s (application id=%s)",
                    document.id,
                    application.id,
                )
                checks = self._run_checks(document)
                self._persist_checks(application.id, document, run_at, checks)
                report = _build_report(application.id, document, checks, run_at)
                self._log_document_outcome(document, report)
                reports.append(report)
        except Exception as exc:
            logger.exception(
                "Technical validation failed for application id=%s",
                application.id,
            )
            raise TechnicalValidationFailed(
                "Technical validation failed unexpectedly"
            ) from exc

        logger.info(
            "Technical validation completed for application id=%s: %s reports generated",
            application.id,
            len(reports),
        )
        return TechnicalValidationListResponse(
            application_id=application.id,
            items=reports,
            total=len(reports),
        )

    def get_reports(self, *, application_id: int) -> TechnicalValidationListResponse:
        """Return every stored technical validation report for an application.

        Reports are reconstructed from the persisted per-check rows and reflect
        whatever validation runs have already happened.

        Args:
            application_id: Id of the application.

        Returns:
            The stored reports, ordered by document then newest run first.

        Raises:
            ApplicationNotFound: When the application does not exist.
        """
        application = self._get_application(application_id)
        documents = {
            document.id: document
            for document in self._documents.get_all_by_application(application_id)
        }
        rows = self._validation.get_by_application_and_category(
            application_id,
            TECHNICAL_VALIDATION_RULE_CATEGORY,
        )
        reports = _reports_from_rows(documents, rows)
        logger.info(
            "Returned %s stored technical validation reports for application id=%s",
            len(reports),
            application.id,
        )
        return TechnicalValidationListResponse(
            application_id=application.id,
            items=reports,
            total=len(reports),
        )

    def _get_application(self, application_id: int):
        """Return the application or raise ``ApplicationNotFound``."""
        application = self._applications.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFound()
        return application

    def _run_checks(self, document: Document) -> list[_Check]:
        """Run every technical check applicable to a stored document.

        Args:
            document: Document metadata describing the stored file.

        Returns:
            The ordered list of checks, ending with the readability aggregate.
        """
        checks: list[_Check] = []
        path = self._accessibility_checks(document, checks)
        file_format = self._format_checks(document, checks, verified=path is not None)
        if path is not None and file_format is not None:
            if file_format is FileFormat.PDF:
                self._pdf_checks(path, checks)
            else:
                self._image_checks(path, checks)
        self._readability_check(checks)
        return checks

    def _accessibility_checks(
        self,
        document: Document,
        checks: list[_Check],
    ) -> Path | None:
        """Run the accessibility checks, returning the resolved file path.

        A missing or unreadable file stops the checks because nothing deeper
        can be inspected; ``None`` is returned in that case.

        Args:
            document: Document whose stored file is checked.
            checks: Check list being assembled.

        Returns:
            The resolved absolute file path, or ``None`` when the file cannot
            be used for further inspection.
        """
        try:
            path = self._storage.resolve(document.stored_file_path)
        except StorageException as exc:
            checks.append(
                _fail_check(CHECK_FILE_EXISTS, f"Stored file path is invalid: {exc}")
            )
            return None
        logger.info(
            "Opened stored file %r for document id=%s",
            document.stored_file_path,
            document.id,
        )
        try:
            validate_file_present(path)
            checks.append(_pass_check(CHECK_FILE_EXISTS, "Stored file exists"))
        except FileNotFound as exc:
            checks.append(_fail_check(CHECK_FILE_EXISTS, exc.detail))
            return None
        try:
            validate_file_readable(path)
            checks.append(_pass_check(CHECK_FILE_READABLE, "Stored file is readable"))
        except FileUnreadable as exc:
            checks.append(_fail_check(CHECK_FILE_READABLE, exc.detail))
            return None
        try:
            validate_file_not_empty(path)
            checks.append(_pass_check(CHECK_FILE_NOT_EMPTY, "Stored file is not empty"))
        except EmptyFile as exc:
            checks.append(_fail_check(CHECK_FILE_NOT_EMPTY, exc.detail))
        except FileUnreadable as exc:
            checks.append(_fail_check(CHECK_FILE_NOT_EMPTY, exc.detail))
        return path

    def _format_checks(
        self,
        document: Document,
        checks: list[_Check],
        *,
        verified: bool,
    ) -> FileFormat | None:
        """Run the file-type check for a document.

        Args:
            document: Document whose format is checked.
            checks: Check list being assembled.
            verified: Whether the file could be accessed for inspection.

        Returns:
            The normalized :class:`FileFormat` when supported, else ``None``.
        """
        label = _format_label(document)
        try:
            _, file_format = detect_format(document)
        except UnsupportedFileFormat as exc:
            check = _fail_check(CHECK_FILE_TYPE, exc.detail)
            check.file_format = label
            checks.append(check)
            return None
        if verified:
            check = _pass_check(CHECK_FILE_TYPE, f"Detected format: {file_format.value}")
        else:
            check = _fail_check(
                CHECK_FILE_TYPE,
                "File format could not be verified because the file is not accessible",
            )
        check.file_format = label
        checks.append(check)
        return file_format

    def _pdf_checks(self, path: Path, checks: list[_Check]) -> None:
        """Run the PDF structural and visual checks.

        Args:
            path: Absolute path of the PDF file.
            checks: Check list being assembled.
        """
        try:
            metrics = validate_pdf(path)
        except PasswordProtectedPDF as exc:
            checks.append(
                _pass_check(CHECK_PDF_OPEN, "PDF opened; encryption detected")
            )
            checks.append(_fail_check(CHECK_PDF_PASSWORD, exc.detail))
            return
        except CorruptedPDF as exc:
            checks.append(_fail_check(CHECK_PDF_OPEN, exc.detail))
            return
        checks.append(_pass_check(CHECK_PDF_OPEN, "PDF opened successfully"))
        checks.append(_pass_check(CHECK_PDF_PASSWORD, "PDF is not encrypted"))
        if metrics.page_count >= 1:
            checks.append(
                _pass_check(CHECK_PDF_PAGES, f"PDF has {metrics.page_count} pages")
            )
        else:
            checks.append(_fail_check(CHECK_PDF_PAGES, "PDF contains no pages"))
        if metrics.dimensions_valid:
            checks.append(
                _pass_check(CHECK_PDF_DIMENSIONS, "Every page has valid dimensions")
            )
        else:
            checks.append(
                _fail_check(CHECK_PDF_DIMENSIONS, "A page has invalid dimensions")
            )
        image = render_pdf_first_page(path)
        if image is None:
            checks.append(
                _warn_check(
                    CHECK_PDF_RENDER,
                    "First page could not be rendered for visual analysis",
                )
            )
        else:
            self._visual_checks(image, checks)

    def _image_checks(self, path: Path, checks: list[_Check]) -> None:
        """Run the image load, resolution and visual checks.

        Args:
            path: Absolute path of the image file.
            checks: Check list being assembled.
        """
        try:
            metrics = validate_image(path)
        except InvalidImage as exc:
            checks.append(_fail_check(CHECK_IMAGE_LOAD, exc.detail))
            return
        checks.append(
            _pass_check(
                CHECK_IMAGE_LOAD,
                f"Image loaded successfully ({metrics.width}x{metrics.height})",
            )
        )
        if metrics.resolution_valid:
            checks.append(
                _pass_check(
                    CHECK_IMAGE_RESOLUTION,
                    f"Resolution {metrics.width}x{metrics.height} meets the minimum",
                )
            )
        else:
            checks.append(
                _fail_check(
                    CHECK_IMAGE_RESOLUTION,
                    f"Resolution {metrics.width}x{metrics.height} is below the "
                    f"minimum {MIN_IMAGE_WIDTH}x{MIN_IMAGE_HEIGHT}",
                )
            )
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        self._visual_checks(image, checks)

    def _visual_checks(self, image, checks: list[_Check]) -> None:
        """Run the blur and rotation checks on an image.

        Args:
            image: BGR image to analyse (loaded image or rendered PDF page).
            checks: Check list being assembled.
        """
        blur_score = variance_of_laplacian(image)
        if blur_score >= BLUR_THRESHOLD:
            blur_check = _pass_check(
                CHECK_BLUR,
                f"Blur score {blur_score:.1f} is above the threshold {BLUR_THRESHOLD:.1f}",
            )
        else:
            blur_check = _fail_check(
                CHECK_BLUR,
                f"Blur score {blur_score:.1f} is below the threshold {BLUR_THRESHOLD:.1f}",
            )
        blur_check.blur_score = round(blur_score, 2)
        checks.append(blur_check)

        angle = estimate_rotation_angle(image)
        if abs(angle) < ROTATION_TOLERANCE_DEGREES:
            rotation_check = _pass_check(
                CHECK_ROTATION,
                f"Rotation angle {angle:.1f} degrees is within tolerance",
            )
        else:
            rotation_check = _warn_check(
                CHECK_ROTATION,
                f"Document appears rotated by {angle:.1f} degrees",
            )
        rotation_check.rotation_angle = round(angle, 2)
        checks.append(rotation_check)

        if is_blank_image(image):
            checks.append(
                _fail_check(
                    CHECK_BLANK_PAGE,
                    "Page contains no readable content (blank)",
                )
            )
        else:
            checks.append(_pass_check(CHECK_BLANK_PAGE, "Page contains readable content"))

    def _readability_check(self, checks: list[_Check]) -> None:
        """Append the aggregate readability check to the check list.

        Args:
            checks: Check list being assembled.
        """
        readability = _derive_readability(checks)
        if readability is ReadabilityStatus.READABLE:
            checks.append(
                _pass_check(CHECK_READABILITY, "Document is technically readable")
            )
        elif readability is ReadabilityStatus.PARTIALLY_READABLE:
            checks.append(
                _warn_check(
                    CHECK_READABILITY,
                    "Document is partially readable (rotation detected)",
                )
            )
        else:
            checks.append(
                _fail_check(CHECK_READABILITY, "Document is not technically readable")
            )

    def _persist_checks(
        self,
        application_id: int,
        document: Document,
        run_at: datetime,
        checks: list[_Check],
    ) -> None:
        """Persist one validation result row per performed check.

        Args:
            application_id: Application being validated.
            document: Document being validated.
            run_at: Shared timestamp of the validation run.
            checks: Checks to persist.
        """
        for check in checks:
            self._validation.create(
                application_id=application_id,
                document_id=document.id,
                rule_id=check.rule_id,
                rule_name=check.rule_name,
                rule_category=TECHNICAL_VALIDATION_RULE_CATEGORY,
                severity=check.severity,
                status=check.status,
                message=check.message,
                blur_score=check.blur_score,
                rotation_angle=check.rotation_angle,
                file_format=check.file_format,
                validated_at=run_at,
            )

    def _log_document_outcome(
        self,
        document: Document,
        report: TechnicalValidationReport,
    ) -> None:
        """Log whether the validation of one document passed or failed.

        Args:
            document: Validated document.
            report: Report describing the outcome.
        """
        if report.validation_status is ValidationStatus.PASS:
            logger.info(
                "Technical validation passed for document id=%s (application id=%s)",
                document.id,
                report.application_id,
            )
        else:
            logger.warning(
                "Technical validation failed for document id=%s (application id=%s): "
                "%s failed checks, %s warnings",
                document.id,
                report.application_id,
                len(report.failed_checks),
                len(report.warnings),
            )


def _reports_from_rows(
    documents: dict[int, Document],
    rows: list,
) -> list[TechnicalValidationReport]:
    """Reconstruct reports from stored validation result rows.

    Rows arrive ordered by document then newest run first; consecutive rows
    sharing a document and run timestamp form a single report.

    Args:
        documents: Application documents keyed by id (for metadata lookups).
        rows: Stored technical validation check rows.

    Returns:
        The reconstructed reports.
    """
    reports: list[TechnicalValidationReport] = []
    index = 0
    while index < len(rows):
        first = rows[index]
        run_key = (first.document_id, first.validated_at)
        group = [first]
        index += 1
        while (
            index < len(rows)
            and (rows[index].document_id, rows[index].validated_at) == run_key
        ):
            group.append(rows[index])
            index += 1
        document = documents.get(first.document_id)
        if document is None:  # pragma: no cover - cascading FK keeps this aligned
            continue
        checks = [_check_from_row(row) for row in group]
        reports.append(_build_report(first.application_id, document, checks, first.validated_at))
    return reports


def _check_from_row(row) -> _Check:
    """Convert a stored validation result row back into an in-memory check.

    Args:
        row: A stored :class:`ValidationResult` instance.

    Returns:
        The equivalent check record.
    """
    return _Check(
        rule_id=row.rule_id,
        rule_name=row.rule_name,
        status=row.status,
        severity=row.severity,
        message=row.message,
        blur_score=row.blur_score,
        rotation_angle=row.rotation_angle,
        file_format=row.file_format,
    )

"""Default reviewer comment generator.

Single source of truth for the default communication text shown in the
printable validation report when the reviewer has not saved a custom comment.
"""

from app.database.models.enums import ApplicationStatus

_APPROVED_COMMENT = (
    "The submitted documents have been reviewed and validated. All required "
    "documentation has been received and verification checks have been "
    "completed successfully."
)

_REJECTED_COMMENT = (
    "The submitted documents have been reviewed. Unfortunately, the "
    "application could not be approved due to the issues identified in this "
    "report. Please review the issues and contact your relationship manager "
    "for further guidance."
)

_FAILED_COMMENT = (
    "The submitted documents have been reviewed against the required "
    "documentation and verification criteria. Additional documents and/or "
    "clarification are required for the review to proceed. Please address "
    "the items identified in this report and provide the requested documents."
)

_DEFAULT_COMMENT = (
    "The submitted documents are currently being reviewed. A final decision "
    "will be communicated once the review is complete."
)

_STATUS_MAP: dict[ApplicationStatus, str] = {
    ApplicationStatus.APPROVED: _APPROVED_COMMENT,
    ApplicationStatus.REJECTED: _REJECTED_COMMENT,
    ApplicationStatus.NEEDS_DOCUMENTS: _FAILED_COMMENT,
    ApplicationStatus.SUBMITTED: _DEFAULT_COMMENT,
    ApplicationStatus.PROCESSING: _DEFAULT_COMMENT,
    ApplicationStatus.PROCESSING_FAILED: _DEFAULT_COMMENT,
    ApplicationStatus.PENDING_REVIEW: _DEFAULT_COMMENT,
    ApplicationStatus.CORRECTED: _APPROVED_COMMENT,
}


def get_default_comment(status: ApplicationStatus | str) -> str:
    """Return the default reviewer comment for the given application status.

    Args:
        status: The application status (enum value or string).

    Returns:
        A professional default comment appropriate for the status.
    """
    if isinstance(status, str):
        try:
            status = ApplicationStatus(status)
        except ValueError:
            return _DEFAULT_COMMENT
    return _STATUS_MAP.get(status, _DEFAULT_COMMENT)


def resolve_reviewer_comment(
    saved: str | None, status: ApplicationStatus | str
) -> str:
    """Resolve the reviewer comment for display, applying precedence rules.

    Precedence:
        1. Saved reviewer_comments (if non-null and non-empty after trim)
        2. Generated default comment based on application status

    Args:
        saved: The saved reviewer comment from the database, or None.
        status: The application status for default generation.

    Returns:
        The comment to display in the printable report.
    """
    trimmed = (saved or "").strip()
    if trimmed:
        return trimmed
    return get_default_comment(status)

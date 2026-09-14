"""HTTP endpoints for the final human verification module.

Exposes the review screen (``GET``), the final decision submission (``POST``)
and the review history (``GET``). Routes stay thin: they build the service per
request and translate the module's domain exceptions -- and the validation
report exceptions raised while loading the report -- into documented HTTP
errors.
"""

import logging
from functools import wraps
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_role
from app.auth.roles import ROLE_REVIEWER
from app.database.connection import get_db
from app.database.models.user import User
from app.database.repositories.application_repository import (
    ApplicationRepository,
)
from app.human_verification.exceptions import ApplicationNotFound, HumanReviewError
from app.human_verification.schemas import (
    EditedReportRequest,
    EditedReportResponse,
    ErrorResponse,
    HumanReviewRequest,
    ReviewerCommentsRequest,
    ReviewerCommentsResponse,
    ReviewHistory,
    ReviewScreen,
    ReviewSummary,
)
from app.human_verification.services import HumanVerificationService
from app.reports.exceptions import ReportError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["human-verification"])

_GET_DB = Annotated[Session, Depends(get_db)]
_CURRENT_USER = Annotated[User, Depends(get_current_user)]
_REVIEWER = Annotated[User, Depends(require_role(ROLE_REVIEWER))]

#: Shared OpenAPI error-response documentation reused by every endpoint.
_ERROR_RESPONSES = {
    400: {
        "model": ErrorResponse,
        "description": "Review decision is internally inconsistent.",
    },
    404: {"model": ErrorResponse, "description": "Application not found."},
    409: {
        "model": ErrorResponse,
        "description": "Application has already been reviewed.",
    },
    422: {
        "model": ErrorResponse,
        "description": (
            "No validation results, incomplete checklist, missing rejection "
            "reason or missing corrections."
        ),
    },
    500: {"model": ErrorResponse, "description": "Review could not be persisted."},
}


def _handle_human_review_errors(func):
    """Translate module and report errors into HTTP error responses.

    Keeps the error mapping inside the human verification module while remaining
    compatible with FastAPI versions that do not expose router-level exception
    handlers. Report errors surface while loading the validation report and are
    re-exposed with their own status codes.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (HumanReviewError, ReportError) as exc:
            logger.error(
                "Human review error %s: %s",
                exc.__class__.__name__,
                exc.detail,
            )
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return wrapper


def _service(db: Session) -> HumanVerificationService:
    """Build the human verification service bound to the request session."""
    return HumanVerificationService(db)


@router.get(
    "/applications/{application_id}/human-review",
    response_model=ReviewScreen,
    summary="Open the final review screen",
    description=(
        "Assembles everything the employee needs for the final decision: the "
        "validation report, the uploaded documents with their OCR state, the "
        "normalized and confidence-scored extracted fields, the visual "
        "detection outcomes, the current checklist state and any previous "
        "review. No pipeline stage is re-run."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_human_review_errors
def get_human_review(
    application_id: int,
    db: _GET_DB,
) -> ReviewScreen:
    """Open the final review screen for an application.

    Args:
        application_id: Id of the application.
        db: Active database session.

    Returns:
        The review screen payload.

    Raises:
        HTTPException: When the application does not exist or has no
            validation results to review.
    """
    return _service(db).get_review(application_id=application_id)


@router.post(
    "/applications/{application_id}/human-review",
    response_model=ReviewSummary,
    summary="Submit the final review decision",
    description=(
        "Records the employee's final decision for an application. An approval "
        "requires the complete manual checklist, a correction requires at least "
        "one corrected value and a rejection requires a mandatory rejection "
        "reason. The application status is moved accordingly and the review, "
        "checklist, corrections and audit trail are persisted. An application "
        "can only be reviewed once."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_human_review_errors
def submit_human_review(
    application_id: int,
    request: HumanReviewRequest,
    db: _GET_DB,
    current_user: _REVIEWER,
) -> ReviewSummary:
    """Submit the reviewer's final decision for an application.

    Only users with the reviewer role may record a final decision; other roles
    receive ``403 Forbidden``.

    Args:
        application_id: Id of the application.
        request: Review payload with the reviewer's decision.
        db: Active database session.
        current_user: The authenticated reviewer, recorded as the reviewer.

    Returns:
        A summary of the recorded review.

    Raises:
        HTTPException: When the application does not exist, was already
            reviewed, has no validation results or the payload violates the
            decision rules.
    """
    return _service(db).submit_review(
        application_id=application_id,
        request=request,
        reviewer_name=current_user.name,
    )


@router.get(
    "/applications/{application_id}/human-review/history",
    response_model=ReviewHistory,
    summary="Get the final review history",
    description=(
        "Returns the final reviews recorded for an application, most recent "
        "first, together with their corrections and checklist state."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_human_review_errors
def get_human_review_history(
    application_id: int,
    db: _GET_DB,
) -> ReviewHistory:
    """Return the final review history for an application.

    Args:
        application_id: Id of the application.
        db: Active database session.

    Returns:
        The recorded reviews.

    Raises:
        HTTPException: When the application does not exist.
    """
    return _service(db).get_history(application_id=application_id)


_REVIEWER_COMMENTS_MAX_LEN = 5000


@router.get(
    "/applications/{application_id}/reviewer-comments",
    response_model=ReviewerCommentsResponse,
    summary="Get the reviewer comment",
    description=(
        "Returns the saved reviewer comment for an application. "
        "When no comment has been saved, ``reviewer_comments`` is null."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_human_review_errors
def get_reviewer_comments(
    application_id: int,
    db: _GET_DB,
) -> ReviewerCommentsResponse:
    """Return the saved reviewer comment for an application.

    Args:
        application_id: Id of the application.
        db: Active database session.

    Returns:
        The reviewer comment response.

    Raises:
        HTTPException: When the application does not exist.
    """
    repo = ApplicationRepository(db)
    comments = repo.get_reviewer_comments(application_id)
    if comments is None:
        raise ApplicationNotFound("Application not found.")
    return ReviewerCommentsResponse(
        application_id=application_id,
        reviewer_comments=comments,
    )


@router.put(
    "/applications/{application_id}/reviewer-comments",
    response_model=ReviewerCommentsResponse,
    summary="Save the reviewer comment",
    description=(
        "Saves or clears the reviewer comment for an application. "
        "Empty or whitespace-only values are stored as null. "
        "Maximum length is 5,000 characters."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_human_review_errors
def save_reviewer_comments(
    application_id: int,
    request: ReviewerCommentsRequest,
    db: _GET_DB,
    current_user: _REVIEWER,
) -> ReviewerCommentsResponse:
    """Save the reviewer comment for an application.

    Only users with the reviewer role may save comments; other roles
    receive ``403 Forbidden``.

    Args:
        application_id: Id of the application.
        request: Payload with the reviewer comment text.
        db: Active database session.
        current_user: The authenticated reviewer.

    Returns:
        The saved reviewer comment response.

    Raises:
        HTTPException: When the application does not exist or the
            comment exceeds the maximum length.
    """
    repo = ApplicationRepository(db)
    if repo.get_by_id(application_id) is None:
        raise ApplicationNotFound("Application not found.")
    text = request.reviewer_comments
    if text is not None and len(text) > _REVIEWER_COMMENTS_MAX_LEN:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Reviewer comment exceeds maximum length of "
                f"{_REVIEWER_COMMENTS_MAX_LEN} characters."
            ),
        )
    saved = repo.save_reviewer_comments(application_id, text)
    return ReviewerCommentsResponse(
        application_id=application_id,
        reviewer_comments=saved,
    )


#: A full rendered report page (styles, tables, boilerplate) is comfortably
#: under this even for a large application -- guards against a pathological
#: payload, not a real report's own size.
_EDITED_REPORT_MAX_LEN = 2_000_000


@router.get(
    "/applications/{application_id}/edited-report",
    response_model=EditedReportResponse,
    summary="Get the saved edited report HTML",
    description=(
        "Returns the reviewer-saved edited copy of the printable validation "
        "report for an application. When no edit has been saved, ``html`` "
        "is null and the report view/PDF download regenerate fresh from "
        "live pipeline data instead."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_human_review_errors
def get_edited_report(
    application_id: int,
    db: _GET_DB,
) -> EditedReportResponse:
    """Return the saved edited report HTML for an application.

    Args:
        application_id: Id of the application.
        db: Active database session.

    Returns:
        The edited report response.

    Raises:
        HTTPException: When the application does not exist.
    """
    repo = ApplicationRepository(db)
    if repo.get_by_id(application_id) is None:
        raise ApplicationNotFound("Application not found.")
    return EditedReportResponse(
        application_id=application_id,
        html=repo.get_edited_report_html(application_id),
    )


@router.put(
    "/applications/{application_id}/edited-report",
    response_model=EditedReportResponse,
    summary="Save an edited copy of the printable report",
    description=(
        "Saves or clears the edited report HTML for an application. Once "
        "saved, this exact HTML is what the report view and PDF download "
        "both serve, instead of the report regenerating fresh from live "
        "pipeline data -- an explicit, reviewer-initiated override. Empty "
        "or whitespace-only values clear the override."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_human_review_errors
def save_edited_report(
    application_id: int,
    request: EditedReportRequest,
    db: _GET_DB,
    current_user: _REVIEWER,
) -> EditedReportResponse:
    """Save the edited report HTML for an application.

    Only users with the reviewer role may save an edited report; other
    roles receive ``403 Forbidden``.

    Args:
        application_id: Id of the application.
        request: Payload with the edited report HTML.
        db: Active database session.
        current_user: The authenticated reviewer.

    Returns:
        The saved edited report response.

    Raises:
        HTTPException: When the application does not exist or the HTML
            exceeds the maximum length.
    """
    repo = ApplicationRepository(db)
    if repo.get_by_id(application_id) is None:
        raise ApplicationNotFound("Application not found.")
    html = request.html
    if html is not None and len(html) > _EDITED_REPORT_MAX_LEN:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Edited report exceeds maximum length of "
                f"{_EDITED_REPORT_MAX_LEN} characters."
            ),
        )
    saved = repo.save_edited_report_html(application_id, html)
    return EditedReportResponse(
        application_id=application_id,
        html=saved,
    )

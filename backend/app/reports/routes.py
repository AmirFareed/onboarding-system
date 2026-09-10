"""HTTP endpoints for the validation report module.

Exposes the report (``GET``), printable HTML report (``GET``) and condensed
summary (``GET``) endpoints. Routes stay thin: they build the service per
request and translate the module's domain exceptions into documented HTTP
errors.
"""

import logging
from functools import wraps
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.auth.roles import ROLE_REVIEWER
from app.database.connection import get_db
from app.database.models.user import User
from app.reports.exceptions import ReportError
from app.reports.schemas import (
    ErrorResponse,
    ValidationReport,
    ValidationSummary,
)
from app.reports.services import ValidationReportService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reports"])

_GET_DB = Annotated[Session, Depends(get_db)]
_REVIEWER = Annotated[User, Depends(require_role(ROLE_REVIEWER))]

#: Shared OpenAPI error-response documentation reused by every endpoint.
_ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Application not found."},
    500: {"model": ErrorResponse, "description": "Report generation failed."},
}


def _handle_report_errors(func):
    """Translate :class:`ReportError` into HTTP error responses.

    Keeps the error mapping inside the reports module while remaining
    compatible with FastAPI versions that do not expose router-level exception
    handlers.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ReportError as exc:
            logger.error(
                "Report error %s: %s",
                exc.__class__.__name__,
                exc.detail,
            )
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return wrapper


def _service(db: Session) -> ValidationReportService:
    """Build the validation report service bound to the request session."""
    return ValidationReportService(db)


@router.get(
    "/applications/{application_id}/validation-report",
    response_model=ValidationReport,
    summary="Generate validation report",
    description=(
        "Aggregates the application's stored pipeline results -- documents, "
        "OCR, extracted fields, business and technical validation results and "
        "visual detections -- into a structured report for employee review. "
        "No validation or detection is re-run. The report is generated "
        "deterministically and can be regenerated at any time."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_report_errors
def get_validation_report(
    application_id: int,
    db: _GET_DB,
    _current_user: _REVIEWER,
) -> ValidationReport:
    """Generate the full validation report for an application.

    Args:
        application_id: Id of the application.
        db: Active database session.

    Returns:
        The structured validation report.

    Raises:
        HTTPException: When the application does not exist or has no
            validation results.
    """
    return _service(db).get_report(application_id=application_id)


@router.get(
    "/applications/{application_id}/validation-report/html",
    response_class=HTMLResponse,
    summary="Generate printable HTML validation report",
    description=(
        "Returns the same validation report rendered as a printable HTML "
        "document from a Jinja2 template, suitable for employee review and "
        "printing."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_report_errors
def get_validation_report_html(
    application_id: int,
    db: _GET_DB,
    _current_user: _REVIEWER,
) -> HTMLResponse:
    """Render the printable HTML validation report for an application.

    Args:
        application_id: Id of the application.
        db: Active database session.

    Returns:
        The rendered HTML document.

    Raises:
        HTTPException: When the application does not exist or has no
            validation results.
    """
    html = _service(db).render_html(application_id=application_id)
    return HTMLResponse(content=html, media_type="text/html")


@router.get(
    "/applications/{application_id}/validation-report/pdf",
    summary="Download printable PDF validation report",
    description=(
        "Returns the same validation report rendered as a PDF document. "
        "Uses the identical Jinja2 template as the HTML version so both "
        "formats are always consistent. The PDF filename includes the "
        "application name and id."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_report_errors
def get_validation_report_pdf(
    application_id: int,
    db: _GET_DB,
    _current_user: _REVIEWER,
) -> Response:
    """Render and return the printable PDF validation report.

    Args:
        application_id: Id of the application.
        db: Active database session.

    Returns:
        The PDF document as a streaming response with a human-readable
        filename.

    Raises:
        HTTPException: When the application does not exist or has no
            validation results.
    """
    service = _service(db)
    application = service._get_application(application_id)
    pdf_bytes = service.render_pdf(application_id=application_id)

    app_name = (application.name or f"Application-{application_id}").replace(
        " ", "-"
    )
    filename = f"{app_name}-Validation-Report-{application_id}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/applications/{application_id}/validation-summary",
    response_model=ValidationSummary,
    summary="Generate validation summary",
    description=(
        "Returns a condensed version of the validation report with the "
        "headline totals and the overall status, for dashboards and list "
        "views."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_report_errors
def get_validation_summary(
    application_id: int,
    db: _GET_DB,
) -> ValidationSummary:
    """Generate the condensed validation summary for an application.

    Args:
        application_id: Id of the application.
        db: Active database session.

    Returns:
        The condensed report.

    Raises:
        HTTPException: When the application does not exist or has no
            validation results.
    """
    return _service(db).get_summary(application_id=application_id)

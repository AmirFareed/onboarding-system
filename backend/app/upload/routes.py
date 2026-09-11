"""HTTP endpoints for application and document management.

Exposes the upload, replace, delete, list, metadata and download operations.
Routes stay thin: they parse the multipart payload, delegate to
:class:`app.upload.services.UploadService` and translate the module's domain
exceptions into documented HTTP error responses.
"""

import logging
from functools import wraps
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.auth.roles import ROLE_EMPLOYEE, ROLE_OPERATOR
from app.database.connection import get_db
from app.database.models.enums import ApplicationStatus, DocumentType
from app.database.models.user import User
from app.upload.exceptions import MissingFileException, UploadError
from app.upload.schemas import (
    ApplicationCreateRequest,
    ApplicationCreateResponse,
    ApplicationDeleteResponse,
    ApplicationDetailResponse,
    ApplicationListResponse,
    ApplicationsClearedResponse,
    BulkUploadResponse,
    BulkUploadSplitItem,
    DocumentDeleteResponse,
    DocumentListResponse,
    DocumentMetadata,
    DocumentReplaceResponse,
    DocumentUploadResponse,
    ErrorResponse,
)
from app.upload.services import UploadService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])

_GET_DB = Annotated[Session, Depends(get_db)]

#: Shared OpenAPI error-response documentation reused across endpoints.
_ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Missing file or invalid file type/content."},
    404: {"model": ErrorResponse, "description": "Application or document not found."},
    409: {"model": ErrorResponse, "description": "A document of this type already exists."},
    413: {"model": ErrorResponse, "description": "File exceeds the maximum allowed size."},
    422: {"model": ErrorResponse, "description": "Validation failed or unsupported document type."},
    500: {"model": ErrorResponse, "description": "Storage operation failed."},
}


def _handle_upload_errors(func):
    """Translate :class:`UploadError` exceptions into HTTP responses.

    Keeps the error mapping inside the upload module while remaining compatible
    with FastAPI versions that do not expose router-level exception handlers.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except UploadError as exc:
            logger.error(
                "Upload error %s: %s",
                exc.__class__.__name__,
                exc.detail,
            )
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return wrapper


def _service(db: Session) -> UploadService:
    """Build the upload service bound to the request session."""
    return UploadService(db)


@router.post(
    "/applications",
    response_model=ApplicationCreateResponse,
    status_code=201,
    summary="Create an application",
    description="Creates a new application that will own uploaded documents.",
    responses={422: _ERROR_RESPONSES[422]},
)
@_handle_upload_errors
def create_application(
    payload: ApplicationCreateRequest,
    db: _GET_DB,
    current_user: User = Depends(require_role(ROLE_OPERATOR)),
) -> ApplicationCreateResponse:
    """Create a new application.

    Args:
        payload: Application creation payload.
        db: Active database session.
        current_user: The authenticated employee, recorded as the creator.

    Returns:
        The created application wrapped in a confirmation message.
    """
    service = _service(db)
    application = service.create_application(
        created_by=current_user.name,
        notes=payload.notes,
    )
    return ApplicationCreateResponse(
        message="Application created successfully",
        application=application,
    )


@router.get(
    "/applications",
    response_model=ApplicationListResponse,
    summary="List applications",
    description=(
        "Lists applications ordered by submission date, optionally filtered by "
        "status and paginated with offset/limit."
    ),
    responses={422: _ERROR_RESPONSES[422]},
)
@_handle_upload_errors
def list_applications(
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    status: ApplicationStatus | None = Query(
        default=None,
        description="When given, only return applications in this status.",
    ),
    db: _GET_DB = ...,
) -> ApplicationListResponse:
    """List applications, optionally filtered by status.

    Args:
        offset: Number of applications to skip.
        limit: Maximum number of applications to return.
        status: Optional status filter.
        db: Active database session.

    Returns:
        The matching applications and the unpaginated total.
    """
    service = _service(db)
    applications, total = service.list_applications(
        offset=offset,
        limit=limit,
        status=status,
    )
    return ApplicationListResponse(items=applications, total=total)


@router.get(
    "/applications/{application_id}",
    response_model=ApplicationDetailResponse,
    summary="Get an application",
    description="Fetches the details of a single application.",
    responses={404: _ERROR_RESPONSES[404]},
)
@_handle_upload_errors
def get_application(
    application_id: int,
    db: _GET_DB = ...,
) -> ApplicationDetailResponse:
    """Fetch a single application by id.

    Args:
        application_id: Id of the application to fetch.
        db: Active database session.

    Returns:
        The application wrapped in a confirmation message.

    Raises:
        HTTPException: 404 when the application does not exist.
    """
    service = _service(db)
    application = service.get_application(application_id)
    return ApplicationDetailResponse(
        message="Application found",
        application=application,
    )


@router.delete(
    "/applications/clear-history",
    response_model=ApplicationsClearedResponse,
    summary="Clear all application history",
    description=(
        "Permanently deletes every application and all of its data, then "
        "resets the application id sequence so the next created application "
        "starts again from 1. Same cascade as deleting one application "
        "(documents, OCR/analysis results, validation results, human "
        "reviews, checklist items, queue jobs, validation history), applied "
        "to every row at once. Audit log and feedback dataset entries "
        "survive with their application reference cleared. EMPLOYEE-only: "
        "this is a destructive, irreversible, whole-system action, not an "
        "everyday operator/reviewer capability. Registered ahead of the "
        "single-application delete route below so this literal path is "
        "matched first, not swallowed by that route's {application_id} "
        "int-typed path parameter."
    ),
)
@_handle_upload_errors
def clear_application_history(
    db: _GET_DB,
    current_user: User = Depends(require_role(ROLE_EMPLOYEE)),
) -> ApplicationsClearedResponse:
    """Delete every application and reset the id sequence back to 1.

    Args:
        db: Active database session.
        current_user: The authenticated EMPLOYEE, recorded as the actor.

    Returns:
        A confirmation message with the number of applications deleted.
    """
    deleted_count = _service(db).clear_all_applications(user=current_user)
    return ApplicationsClearedResponse(
        message="All application history cleared successfully",
        deleted_count=deleted_count,
    )


@router.delete(
    "/applications/{application_id}",
    response_model=ApplicationDeleteResponse,
    summary="Delete an application",
    description=(
        "Permanently deletes an application and all of its data (documents, "
        "OCR/analysis results, validation results, human reviews, checklist "
        "items, queue jobs, validation history) plus the documents' stored "
        "files. Audit log and feedback dataset entries survive with their "
        "application reference cleared. EMPLOYEE-only: this is a destructive, "
        "irreversible action, not an everyday operator/reviewer capability."
    ),
    responses={404: _ERROR_RESPONSES[404]},
)
@_handle_upload_errors
def delete_application(
    application_id: int,
    db: _GET_DB,
    current_user: User = Depends(require_role(ROLE_EMPLOYEE)),
) -> ApplicationDeleteResponse:
    """Delete an application and all of its data.

    Args:
        application_id: Id of the application to delete.
        db: Active database session.
        current_user: The authenticated EMPLOYEE, recorded as the actor.

    Returns:
        A confirmation message.

    Raises:
        HTTPException: 404 when the application does not exist.
    """
    _service(db).delete_application(application_id=application_id, user=current_user)
    return ApplicationDeleteResponse(message="Application deleted successfully")


@router.post(
    "/applications/{application_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=201,
    summary="Upload a document",
    description=(
        "Uploads a single document for an application. The file is validated "
        "(extension, content, size), stored outside the source tree and its "
        "metadata persisted with UPLOADED status."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_upload_errors
def upload_document(
    application_id: int,
    file: Annotated[UploadFile | None, File(description="The document file.")] = None,
    document_type: Annotated[DocumentType, Form(description="Category of the document.")] = ...,
    copy_number: Annotated[
        int | None,
        Form(ge=1, description="1-based copy slot within the type (defaults to 1)."),
    ] = None,
    db: _GET_DB = ...,
    current_user: User = Depends(require_role(ROLE_OPERATOR)),
) -> DocumentUploadResponse:
    """Upload a document for an application.

    Args:
        application_id: Id of the owning application.
        file: Multipart file payload.
        document_type: Document category (multipart form field).
        copy_number: Optional 1-based copy slot for this document within the
            type. When omitted the upload targets the first available slot,
            which the service treats as copy 1.
        db: Active database session.
        current_user: The authenticated employee, recorded as the actor when
            the upload satisfies a pending document request.

    Returns:
        The persisted document metadata.

    Raises:
        HTTPException: When the file is missing or any upload check fails.
    """
    if file is None:
        raise MissingFileException()
    document = _service(db).upload(
        application_id=application_id,
        document_type=document_type,
        copy_number=copy_number or 1,
        filename=file.filename or "",
        content_type=file.content_type or "",
        file=file.file,
        user=current_user,
    )
    return DocumentUploadResponse(
        message="Document uploaded successfully",
        document=document,
    )


@router.put(
    "/applications/{application_id}/documents/{document_id}",
    response_model=DocumentReplaceResponse,
    summary="Replace a document",
    description=(
        "Replaces an existing document's file and metadata. The new file is "
        "stored before the old one is removed, so a failure never loses the "
        "previous version."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_upload_errors
def replace_document(
    application_id: int,
    document_id: int,
    file: Annotated[UploadFile | None, File(description="The replacement file.")] = None,
    document_type: Annotated[DocumentType, Form(description="Category of the document.")] = ...,
    db: _GET_DB = ...,
    current_user: User = Depends(require_role(ROLE_OPERATOR)),
) -> DocumentReplaceResponse:
    """Replace an existing document.

    Args:
        application_id: Id of the owning application.
        document_id: Id of the document to replace.
        file: Multipart replacement file.
        document_type: Document category (multipart form field).
        db: Active database session.

    Returns:
        The updated document metadata.

    Raises:
        HTTPException: When the file is missing or any upload check fails.
    """
    if file is None:
        raise MissingFileException()
    document = _service(db).replace(
        application_id=application_id,
        document_id=document_id,
        document_type=document_type,
        filename=file.filename or "",
        content_type=file.content_type or "",
        file=file.file,
    )
    return DocumentReplaceResponse(
        message="Document replaced successfully",
        document=document,
    )


@router.delete(
    "/applications/{application_id}/documents/{document_id}",
    response_model=DocumentDeleteResponse,
    summary="Delete a document",
    description="Deletes a document's metadata and its stored file.",
    responses={404: _ERROR_RESPONSES[404], 500: _ERROR_RESPONSES[500]},
)
@_handle_upload_errors
def delete_document(
    application_id: int,
    document_id: int,
    db: _GET_DB = ...,
    current_user: User = Depends(require_role(ROLE_OPERATOR)),
) -> DocumentDeleteResponse:
    """Delete a document owned by an application.

    Args:
        application_id: Id of the owning application.
        document_id: Id of the document to delete.
        db: Active database session.

    Returns:
        A confirmation message.
    """
    _service(db).delete(application_id=application_id, document_id=document_id)
    return DocumentDeleteResponse(message="Document deleted successfully")


@router.get(
    "/applications/{application_id}/documents",
    response_model=DocumentListResponse,
    summary="List documents",
    description="Lists an application's documents, newest first.",
    responses={404: _ERROR_RESPONSES[404]},
)
@_handle_upload_errors
def list_documents(
    application_id: int,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    db: _GET_DB = ...,
) -> DocumentListResponse:
    """List an application's documents with pagination.

    Args:
        application_id: Id of the owning application.
        offset: Number of rows to skip.
        limit: Maximum number of rows to return.
        db: Active database session.

    Returns:
        The matching documents and the total count.
    """
    documents, total = _service(db).list_documents(
        application_id=application_id,
        offset=offset,
        limit=limit,
    )
    return DocumentListResponse(items=documents, total=total)


@router.get(
    "/documents/{document_id}",
    response_model=DocumentUploadResponse,
    summary="Get document metadata",
    description="Returns the metadata of a single document.",
    responses={404: _ERROR_RESPONSES[404]},
)
@_handle_upload_errors
def get_document(
    document_id: int,
    db: _GET_DB = ...,
) -> DocumentUploadResponse:
    """Return a single document's metadata.

    Args:
        document_id: Id of the document.
        db: Active database session.

    Returns:
        The document metadata wrapped in a confirmation message.
    """
    document = _service(db).get_document(document_id=document_id)
    return DocumentUploadResponse(
        message="Document found",
        document=document,
    )


@router.get(
    "/applications/{application_id}/documents/{document_id}/download",
    response_class=FileResponse,
    summary="Download a document",
    description=(
        "Streams the stored file using its original filename. Internal storage "
        "paths are never exposed to the client."
    ),
    responses={404: _ERROR_RESPONSES[404]},
)
@_handle_upload_errors
def download_document(
    application_id: int,
    document_id: int,
    db: _GET_DB = ...,
) -> FileResponse:
    """Download a document's stored file.

    Args:
        application_id: Id of the owning application.
        document_id: Id of the document.
        db: Active database session.

    Returns:
        The file as a download attachment.
    """
    service = _service(db)
    document, path = service.download(application_id=application_id, document_id=document_id)
    return FileResponse(
        path=path,
        media_type=document.file_type,
        filename=document.original_filename,
    )


@router.get(
    "/applications/{application_id}/documents/{document_id}/view",
    response_class=FileResponse,
    summary="View a document inline in the browser",
    description=(
        "Streams the stored file with Content-Disposition: inline so the "
        "browser renders it (e.g. PDF viewer) instead of downloading."
    ),
    responses={404: _ERROR_RESPONSES[404]},
)
@_handle_upload_errors
def view_document(
    application_id: int,
    document_id: int,
    db: _GET_DB = ...,
) -> FileResponse:
    """View a document inline in the browser.

    Args:
        application_id: Id of the owning application.
        document_id: Id of the document.
        db: Active database session.

    Returns:
        The file rendered inline by the browser.
    """
    service = _service(db)
    document, path = service.download(application_id=application_id, document_id=document_id)
    return FileResponse(
        path=path,
        media_type=document.file_type,
        content_disposition_type="inline",
    )


@router.post(
    "/applications/{application_id}/bulk-upload",
    response_model=BulkUploadResponse,
    status_code=201,
    summary="Upload a bulk PDF containing all onboarding documents",
    description=(
        "Accepts a single PDF that contains all the organization's onboarding documents "
        "combined. The file is automatically split into individual documents using "
        "text-based heuristics and each is stored separately with the detected "
        "DocumentType. Useful when organizations provide a single combined onboarding file."
    ),
    responses=_ERROR_RESPONSES,
)
@_handle_upload_errors
def upload_bulk_document(
    application_id: int,
    file: Annotated[UploadFile | None, File(description="The combined bulk PDF file.")] = None,
    db: _GET_DB = ...,
    current_user: User = Depends(require_role(ROLE_OPERATOR)),
) -> BulkUploadResponse:
    """Upload a single bulk PDF and auto-split it into individual categorized documents.

    Args:
        application_id: Id of the owning application.
        file: Multipart bulk PDF file.
        db: Active database session.
        current_user: The authenticated employee, recorded as the actor when
            the upload satisfies a pending document request.

    Returns:
        A list of all persisted documents extracted from the bulk file.

    Raises:
        HTTPException: When the file is missing, not a PDF, or splitting fails.
    """
    if file is None:
        raise MissingFileException()
    documents = _service(db).upload_bulk(
        application_id=application_id,
        filename=file.filename or "",
        content_type=file.content_type or "",
        file=file.file,
        user=current_user,
    )
    split_items = [
        BulkUploadSplitItem(
            document_type=doc.document_type,
            document=DocumentMetadata.model_validate(doc),
        )
        for doc in documents
    ]
    return BulkUploadResponse(
        message=f"Bulk PDF split into {len(documents)} documents successfully",
        documents_created=len(documents),
        documents=split_items,
    )

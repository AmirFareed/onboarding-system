"""Upload service: orchestrates validation, storage and persistence.

Keeps the route layer thin: routes parse and document HTTP concerns, the service
implements the actual upload workflow (validate -> store -> persist metadata),
replacement, deletion and retrieval. Every public method is a self-contained
transaction that raises the module's domain exceptions, which the route layer
converts into HTTP responses.
"""

import logging
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.models.application import Application
from app.database.models.document import Document
from app.database.models.enums import (
    ApplicationStatus,
    DocumentProcessingStatus,
    DocumentType,
    ValidationEventType,
)
from app.database.repositories.application_repository import ApplicationRepository
from app.database.repositories.audit_log_repository import AuditLogRepository
from app.database.repositories.document_repository import DocumentRepository
from app.database.repositories.validation_history_repository import (
    ValidationHistoryRepository,
)
from app.upload.constants import MAX_COPIES_BY_DOCUMENT_TYPE, READ_CHUNK_BYTES
from app.upload.exceptions import (
    ApplicationNotFoundException,
    DocumentNotFoundException,
    DuplicateDocumentException,
    FileTooLargeException,
    InvalidFileTypeException,
    StorageException,
)
from app.upload.storage import StorageService
from app.upload.validators import sanitize_filename, validate_file_content

logger = logging.getLogger(__name__)


class UploadService:
    """Implements the document upload and management workflows.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._storage = StorageService(get_settings().upload_storage_root)
        self._applications = ApplicationRepository(db)
        self._documents = DocumentRepository(db)
        self._max_bytes = get_settings().max_upload_size_mb * 1024 * 1024

    def create_application(
        self,
        *,
        created_by: str,
        notes: str | None = None,
    ) -> Application:
        """Create a new application to own uploaded documents.

        Args:
            created_by: Identifier of the submitting user.
            notes: Optional free-form notes.

        Returns:
            The persisted application.
        """
        application = self._applications.create(created_by=created_by, notes=notes)
        logger.info("Created application id=%s by %r", application.id, created_by)
        return application

    def list_applications(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        status: ApplicationStatus | None = None,
    ) -> tuple[list[Application], int]:
        """List applications, optionally filtered by status.

        Args:
            offset: Number of applications to skip.
            limit: Maximum number of applications to return.
            status: When given, only return applications in this status.

        Returns:
            A tuple of ``(applications, total)`` where ``total`` is the
            unpaginated count for the current filter.
        """
        applications = self._applications.list(offset=offset, limit=limit, status=status)
        statement = select(func.count()).select_from(Application)
        if status is not None:
            statement = statement.where(Application.status == status)
        total = self._db.scalar(statement) or 0
        logger.info("Listed %s applications (total=%s)", len(applications), total)
        return list(applications), total

    def get_application(self, application_id: int) -> Application:
        """Return an application or raise ``ApplicationNotFoundException``.

        Args:
            application_id: Id of the application to fetch.

        Returns:
            The matching application.
        """
        return self._get_application(application_id)

    def upload(
        self,
        *,
        application_id: int,
        document_type: DocumentType,
        filename: str,
        content_type: str,
        file: BinaryIO,
        copy_number: int = 1,
        user=None,
    ) -> Document:
        """Validate and persist a newly uploaded document.

        Args:
            application_id: Id of the owning application.
            document_type: Category of the document.
            filename: Raw client-supplied filename.
            content_type: Declared media type.
            file: Stream to read the file content from.
            copy_number: 1-based slot index for this copy within the type,
                e.g. ``3`` for the third 1-Link form.
            user: The authenticated user, recorded as the actor when the
                upload satisfies a pending document request.

        Returns:
            The persisted document metadata with ``UPLOADED`` status.

        Raises:
            ApplicationNotFoundException: When the application does not exist.
            DuplicateDocumentException: When ``copy_number`` is not a positive
                slot, or the requested copy slot is already occupied. Exceeding
                ``MAX_COPIES_BY_DOCUMENT_TYPE`` no longer raises -- the
                document is accepted and the application is flagged for
                manual review instead (see ``_ensure_slot_available``).
            MissingFileException / InvalidFileTypeException /
                FileTooLargeException: When the file fails validation.
        """
        application = self._get_application(application_id)
        self._ensure_slot_available(application_id, document_type, copy_number)

        content = self._read_with_limit(file)
        extension = validate_file_content(filename, content_type, content)
        safe_filename = sanitize_filename(filename)

        # The first uploaded document names the application so operators can
        # find it by the PDF they uploaded. Later uploads never overwrite it.
        if application.name is None:
            application.name = _display_name_from(safe_filename)

        stored_path = self._storage.save(application.id, document_type, content, extension)
        try:
            document = self._documents.create(
                application_id=application.id,
                document_type=document_type,
                copy_number=copy_number,
                original_filename=safe_filename,
                stored_file_path=stored_path,
                file_type=_content_type_for(extension),
                processing_status=DocumentProcessingStatus.UPLOADED,
            )
        except Exception:
            # Roll back the persisted metadata and clean up the orphaned file.
            self._db.rollback()
            self._storage.delete(stored_path)
            raise

        self._record_documents_received(application, user)
        logger.info(
            "Uploaded document id=%s type=%s copy=%s for application id=%s stored=%s",
            document.id,
            document_type.value,
            copy_number,
            application.id,
            stored_path,
        )
        return document

    def upload_bulk(
        self,
        *,
        application_id: int,
        filename: str,
        content_type: str,
        file: BinaryIO,
        user=None,
    ) -> list[Document]:
        """Accept a single bulk PDF, store it, and queue it for background splitting.

        The stream is read within the configured size limit, validated through
        the shared upload validators (extension, MIME type, magic bytes, empty
        content) plus a cheap structural check (readable, non-zero pages), then
        stored as a single ``BULK_UPLOAD`` placeholder document and enqueued on
        the bulk processing queue. The actual page classification/split (and
        any OCR fallback for scanned pages) happens later in the background
        worker (see :meth:`app.preprocessing.splitter.DocumentSplitter.split_bulk_pdf`
        via ``document_processing.services``) so the HTTP request never blocks
        on OCR.

        On any failure nothing is left behind: the stored file is removed and
        the transaction rolled back, so no orphan database row or file can
        survive a partial persist.

        Args:
            application_id: Id of the owning application.
            filename: Raw client-supplied filename.
            content_type: Declared media type.
            file: Stream of the bulk PDF.
            user: The authenticated user, recorded as the actor when the
                upload satisfies a pending document request.

        Returns:
            A single-element list containing the persisted ``BULK_UPLOAD``
            placeholder document, ``UPLOADED`` and queued for splitting.

        Raises:
            ApplicationNotFoundException: When the application does not exist.
            DuplicateDocumentException: When a bulk upload has already been
                submitted for this application -- the ``BULK_UPLOAD``
                placeholder is never deleted, even after its split completes,
                so a second attempt would otherwise crash on the underlying
                unique-slot constraint instead of failing cleanly.
            InvalidFileTypeException / FileTooLargeException: When the file
                fails validation or is not a readable, non-empty PDF.
        """
        from app.preprocessing.splitter import DocumentSplitter

        application = self._get_application(application_id)
        self._ensure_slot_available(
            application_id,
            DocumentType.BULK_UPLOAD,
            1,
            occupied_message="A bulk upload has already been submitted for this application",
        )

        content = self._read_with_limit(file)
        extension = validate_file_content(filename, content_type, content)
        if extension != ".pdf":
            raise InvalidFileTypeException("Bulk upload accepts only PDF files")
        DocumentSplitter.validate_structure(content)

        safe_filename = sanitize_filename(filename)
        # The bulk PDF is the application's primary file, so its name (minus
        # the extension) becomes the application's display name.
        if application.name is None:
            application.name = _display_name_from(safe_filename)
        stored_path = self._storage.save(application.id, DocumentType.BULK_UPLOAD, content, ".pdf")

        # `DocumentRepository.create` commits immediately (see
        # `BaseRepository._commit_and_refresh`), so a failure in the enqueue
        # step below cannot be undone by `db.rollback()` alone -- the document
        # row is already durable. Track it so the except branch can issue a
        # compensating delete and keep the whole method atomic from the
        # caller's perspective.
        document: Document | None = None
        try:
            document = self._documents.create(
                application_id=application.id,
                document_type=DocumentType.BULK_UPLOAD,
                copy_number=1,
                original_filename=safe_filename,
                stored_file_path=stored_path,
                file_type="application/pdf",
                processing_status=DocumentProcessingStatus.UPLOADED,
            )

            # Record DOCUMENTS_RECEIVED *before* the status update below:
            # ApplicationRepository.update() mutates the application object
            # in-place, so after the status changes to PROCESSING the guard
            # inside _record_documents_received() would see PROCESSING instead
            # of NEEDS_DOCUMENTS and skip recording the receipt.
            self._record_documents_received(application, user)

            from app.database.repositories.queue_job_repository import QueueJobRepository
            QueueJobRepository(self._db).enqueue_uploaded_documents(
                application_id=application.id,
                max_attempts=get_settings().bulk_queue_max_attempts,
            )
            # Do NOT transition to PROCESSING here.  The BULK_UPLOAD
            # placeholder is enqueued for splitting; the actual document
            # count is only known after the queue worker runs
            # _process_bulk_upload(), which checks completeness and
            # transitions to NEEDS_DOCUMENTS when documents are missing.
            # Leaving the status unchanged (SUBMITTED or NEEDS_DOCUMENTS)
            # keeps the operator workflow unblocked.

        except Exception:
            self._db.rollback()
            if document is not None:
                self._documents.delete(document)
            self._delete_file(stored_path)
            raise

        logger.info(
            "Bulk upload queued: created BULK_UPLOAD document id=%s for application id=%s",
            document.id,
            application_id,
        )
        return [document]

    def _record_documents_received(self, application: Application, user) -> None:
        """Record a DOCUMENTS_RECEIVED history event after an upload.

        Only fires for an application that was awaiting documents
        (NEEDS_DOCUMENTS) and only when a user is available to record as the
        actor. Records both the immutable validation history entry and the
        shared audit log so the pending-document loop (request -> upload ->
        submit) is fully traceable. Best effort: a failure here must not
        fail the upload itself, so errors are logged, not raised.
        """
        if application.status is not ApplicationStatus.NEEDS_DOCUMENTS or user is None:
            return
        try:
            history = ValidationHistoryRepository(self._db)
            audit = AuditLogRepository(self._db)
            previous = ApplicationStatus.NEEDS_DOCUMENTS
            entry = history.create(
                application_id=application.id,
                event_type=ValidationEventType.DOCUMENTS_RECEIVED,
                actor_id=getattr(user, "id", None),
                actor_name=getattr(user, "name", "Unknown"),
                actor_role=getattr(user, "role", None),
                previous_status=previous.value,
                new_status=application.status.value,
            )
            audit.create(
                application_id=application.id,
                username=getattr(user, "name", "Unknown"),
                action="DOCUMENTS_RECEIVED",
                details={},
                actor_id=getattr(user, "id", None),
                actor_role=getattr(user, "role", None),
                severity="INFO",
                previous_status=previous.value,
                new_status=application.status.value,
            )
            logger.info(
                "Recorded DOCUMENTS_RECEIVED for application id=%s (history entry id=%s)",
                application.id,
                entry.id,
            )
        except Exception:  # pragma: no cover - defensive; must not break uploads
            logger.exception("Failed to record DOCUMENTS_RECEIVED for application id=%s", application.id)

    def replace(
        self,
        *,
        application_id: int,
        document_id: int,
        document_type: DocumentType,
        filename: str,
        content_type: str,
        file: BinaryIO,
    ) -> Document:
        """Replace an existing document's file and metadata.

        The new file is persisted first; only after the database row is updated
        is the previous file removed, so a failure never loses the old version.

        Args:
            application_id: Id of the owning application.
            document_id: Id of the document to replace.
            document_type: Category for the replacement document.
            filename: Raw client-supplied filename.
            content_type: Declared media type.
            file: Stream to read the new file content from.

        Returns:
            The updated document metadata.

        Raises:
            ApplicationNotFoundException: When the application does not exist.
            DocumentNotFoundException: When the document does not exist or does
                not belong to the application.
            MissingFileException / InvalidFileTypeException /
                FileTooLargeException: When the new file fails validation.
        """
        self._get_application(application_id)
        document = self._get_document_for_application(application_id, document_id)
        previous_path = document.stored_file_path

        content = self._read_with_limit(file)
        extension = validate_file_content(filename, content_type, content)
        safe_filename = sanitize_filename(filename)

        new_path = self._storage.save(application_id, document_type, content, extension)
        try:
            document.document_type = document_type
            document.original_filename = safe_filename
            document.file_type = _content_type_for(extension)
            document.stored_file_path = new_path
            document.processing_status = DocumentProcessingStatus.UPLOADED
            self._db.add(document)
            self._db.commit()
            self._db.refresh(document)
        except Exception:
            self._db.rollback()
            self._storage.delete(new_path)
            raise

        self._delete_file(previous_path)
        logger.info(
            "Replaced document id=%s (application id=%s) stored=%s",
            document.id,
            application_id,
            new_path,
        )
        return document

    def delete(self, *, application_id: int, document_id: int) -> None:
        """Delete a document's metadata and its stored file.

        Args:
            application_id: Id of the owning application.
            document_id: Id of the document to delete.

        Raises:
            ApplicationNotFoundException: When the application does not exist.
            DocumentNotFoundException: When the document does not exist or does
                not belong to the application.
        """
        self._get_application(application_id)
        document = self._get_document_for_application(application_id, document_id)
        stored_path = document.stored_file_path

        self._documents.delete(document)
        self._delete_file(stored_path)
        logger.info(
            "Deleted document id=%s (application id=%s)",
            document_id,
            application_id,
        )

    def delete_application(self, *, application_id: int, user=None) -> None:
        """Delete an application and all of its data.

        Cascades at the database level to every child record (documents,
        OCR/analysis results, validation results, human reviews, checklist
        items, queue jobs, validation history) per the ``ON DELETE CASCADE``
        FK rules on :class:`~app.database.models.application.Application`.
        ``audit_logs``/``feedback_dataset`` rows use ``ON DELETE SET NULL``
        instead and deliberately survive with their ``application_id``
        cleared -- preserving the audit trail and the curated ML dataset
        after the source application is gone, same as every other action
        that touches this table. Stored document files on disk are not
        covered by any DB cascade and are removed explicitly after the
        commit, same pattern as :meth:`delete`.

        The audit entry is written *before* the delete so it captures a
        real ``application_id`` in its own row at insert time; the FK's
        ``ON DELETE SET NULL`` then clears it automatically once the
        application is gone, which is the intended, already-established
        behavior for this column (see :meth:`AuditLogRepository.search`'s
        ``include_orphaned`` parameter).

        Args:
            application_id: Id of the application to delete.
            user: The authenticated user, recorded as the actor in the audit
                log. Not authorization -- the route layer's EMPLOYEE-only
                guard is what actually restricts this action.

        Raises:
            ApplicationNotFoundException: When the application does not exist.
        """
        application = self._get_application(application_id)
        stored_paths = [document.stored_file_path for document in application.documents]

        AuditLogRepository(self._db).create(
            application_id=application.id,
            username=getattr(user, "name", "Unknown"),
            action="APPLICATION_DELETED",
            details={
                "application_name": application.name,
                "document_count": len(stored_paths),
            },
            actor_id=getattr(user, "id", None),
            actor_role=getattr(user, "role", None),
            severity="WARNING",
            previous_status=application.status.value,
        )

        self._applications.delete(application)

        for stored_path in stored_paths:
            self._delete_file(stored_path)

        logger.info(
            "Deleted application id=%s (%s documents) by %r",
            application_id,
            len(stored_paths),
            getattr(user, "name", "Unknown"),
        )

    def list_documents(
        self,
        *,
        application_id: int,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Document], int]:
        """Return an application's documents ordered by upload time.

        Args:
            application_id: Id of the owning application.
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.

        Returns:
            A tuple of ``(documents, total)`` where ``total`` ignores pagination.

        Raises:
            ApplicationNotFoundException: When the application does not exist.
        """
        self._get_application(application_id)
        documents = list(
            self._documents.get_by_application(application_id, offset=offset, limit=limit)
        )
        total = self._db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.application_id == application_id)
        )
        return documents, int(total or 0)

    def get_document(self, *, document_id: int) -> Document:
        """Return a single document's metadata.

        Args:
            document_id: Id of the document.

        Returns:
            The matching document.

        Raises:
            DocumentNotFoundException: When the document does not exist.
        """
        document = self._documents.get_by_id(document_id)
        if document is None:
            raise DocumentNotFoundException()
        return document

    def download(self, *, application_id: int, document_id: int) -> tuple[Document, Path]:
        """Resolve a document's stored file for download.

        Args:
            application_id: Id of the owning application.
            document_id: Id of the document.

        Returns:
            A tuple of ``(document, absolute_file_path)`` so the caller can
            stream the file with the document's media type and original name.

        Raises:
            ApplicationNotFoundException: When the application does not exist.
            DocumentNotFoundException: When the document does not exist or does
                not belong to the application.
        """
        self._get_application(application_id)
        document = self._get_document_for_application(application_id, document_id)
        path = self._storage.resolve(document.stored_file_path)
        logger.info(
            "Download requested for document id=%s (application id=%s)",
            document.id,
            document.application_id,
        )
        return document, path

    def _get_application(self, application_id: int) -> Application:
        """Return an application or raise ``ApplicationNotFoundException``."""
        application = self._applications.get_by_id(application_id)
        if application is None:
            raise ApplicationNotFoundException()
        return application

    def _get_document_for_application(
        self,
        application_id: int,
        document_id: int,
    ) -> Document:
        """Return a document owned by the application, or raise a 404."""
        document = self._documents.get_by_id(document_id)
        if document is None or document.application_id != application_id:
            raise DocumentNotFoundException()
        return document

    def _existing_copy_maxes(self, application_id: int) -> dict[DocumentType, int]:
        """Return the highest persisted copy number per document type.

        Copy numbering for bulk uploads must continue from records that already
        exist in the database, never solely from the current batch.

        Args:
            application_id: Id of the owning application.

        Returns:
            A mapping of document type to its largest existing copy number
            (or 0 when the application holds no copy of that type).
        """
        statement = (
            select(Document.document_type, func.max(Document.copy_number))
            .where(Document.application_id == application_id)
            .group_by(Document.document_type)
        )
        return {
            document_type: int(max_copy or 0)
            for document_type, max_copy in self._db.execute(statement)
        }

    def _ensure_slot_available(
        self,
        application_id: int,
        document_type: DocumentType,
        copy_number: int,
        *,
        occupied_message: str | None = None,
    ) -> None:
        """Raise ``DuplicateDocumentException`` only when the slot itself is unusable.

        ``copy_number`` must still be a positive, not-already-occupied slot --
        those are structural invariants, not a policy choice. Exceeding
        ``MAX_COPIES_BY_DOCUMENT_TYPE`` is no longer a hard rejection (see
        the department decision recorded in CONTEXT.md, 2026-08-19): a real
        bulk file can legitimately produce more copies of a type than the
        configured threshold when the splitter mis-slices unrelated content
        into that type's boundary (see the GDA Abbotabad findings in
        CONTEXT.md) -- rejecting the whole upload over a count doesn't fix
        that document-boundary problem, it just blocks the operator from
        ever seeing the file. Over-threshold uploads are now accepted and
        flagged for manual review instead.

        ``occupied_message`` overrides the default already-occupied detail
        text -- used by ``upload_bulk`` so its 409 never leaks the internal
        ``BULK_UPLOAD`` placeholder type name to an end user.
        """
        if copy_number < 1:
            raise DuplicateDocumentException(
                f"Invalid copy number {copy_number} for {document_type.value}"
            )

        max_copies = MAX_COPIES_BY_DOCUMENT_TYPE.get(document_type, 1)
        if copy_number > max_copies:
            logger.warning(
                "Application id=%s: copy %s of %s exceeds the configured "
                "threshold of %s -- accepting and flagging for manual review "
                "instead of rejecting.",
                application_id,
                copy_number,
                document_type.value,
                max_copies,
            )
            self._flag_for_manual_review(
                application_id,
                f"{document_type.value} has {copy_number} copies, exceeding the "
                f"configured threshold of {max_copies}. Flagged for manual review.",
            )

        statement = select(Document).where(
            Document.application_id == application_id,
            Document.document_type == document_type,
            Document.copy_number == copy_number,
        )
        if self._db.scalar(statement) is not None:
            raise DuplicateDocumentException(
                occupied_message
                or f"Copy {copy_number} of {document_type.value} already exists "
                "for this application"
            )

    def _flag_for_manual_review(self, application_id: int, message: str) -> None:
        """Best-effort, additive note that an application needs manual review.

        No dedicated review-flag column/status exists on ``main`` yet, so
        this appends an operator-visible note rather than introducing a new
        migration -- keeps this change narrow, per the department decision's
        own scope (stop the hard rejection; the splitter's document-boundary
        bug behind the over-threshold count is separate, larger work).
        """
        application = self._applications.get_by_id(application_id)
        if application is None:
            return
        stamped = f"[SYSTEM] {message}"
        application.notes = (
            f"{application.notes}\n{stamped}" if application.notes else stamped
        )

    def _read_with_limit(self, file: BinaryIO) -> bytes:
        """Stream the file, enforcing the configured maximum size.

        Args:
            file: Stream to read from.

        Returns:
            The complete file content, or ``b""`` for an empty file (empty
            content is rejected later during content validation).

        Raises:
            FileTooLargeException: When the content exceeds the size limit.
        """
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = file.read(READ_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > self._max_bytes:
                raise FileTooLargeException(
                    f"File exceeds the maximum allowed size of "
                    f"{self._max_bytes // (1024 * 1024)} MB"
                )
            chunks.append(chunk)
        return b"".join(chunks)

    def _delete_file(self, stored_file_path: str) -> None:
        """Remove a stored file, logging but swallowing storage errors.

        A failure here must not fail the request after the database has already
        committed; the orphaned file is reported through the logs instead.
        """
        try:
            self._storage.delete(stored_file_path)
        except StorageException:
            logger.exception(
                "Could not remove stored file %r; manual cleanup required",
                stored_file_path,
            )


def _content_type_for(extension: str) -> str:
    """Return the canonical media type for a validated extension."""
    from app.upload.constants import MIME_TYPES_BY_EXTENSION

    types = MIME_TYPES_BY_EXTENSION.get(extension)
    return next(iter(types)) if types else "application/octet-stream"


def _display_name_from(filename: str) -> str:
    """Return the filename without its extension, for use as an application name.

    ``TMA Khal Dir Lower.pdf`` becomes ``TMA Khal Dir Lower``. Falls back to
    the original filename when stripping leaves nothing (e.g. ``.pdf``).
    """
    return Path(filename).stem or filename

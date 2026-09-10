"""Repository for the Document entity."""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models.document import Document
from app.database.models.enums import DocumentProcessingStatus, DocumentType
from app.database.repositories.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    """Persistence operations for :class:`Document`.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        super().__init__(db)

    @property
    def _model(self) -> type[Document]:
        return Document

    def create(
        self,
        *,
        application_id: int,
        document_type: DocumentType,
        copy_number: int | None = None,
        original_filename: str,
        stored_file_path: str,
        file_type: str,
        processing_status: DocumentProcessingStatus = DocumentProcessingStatus.PENDING,
    ) -> Document:
        """Create and persist a new document record.

        Args:
            application_id: Owning application id.
            document_type: Category of the document.
            copy_number: 1-based slot index for this copy within the type. If
                omitted, the next available slot is allocated.
            original_filename: Filename supplied by the uploader.
            stored_file_path: Location of the file on the storage backend.
            file_type: Media type (MIME) of the stored file.
            processing_status: Initial processing status.

        Returns:
            The persisted document with server-generated fields loaded.
        """
        if copy_number is None:
            copy_number = int(
                self._db.scalar(
                    select(func.max(Document.copy_number)).where(
                        Document.application_id == application_id,
                        Document.document_type == document_type,
                    )
                )
                or 0
            ) + 1

        document = Document(
            application_id=application_id,
            document_type=document_type,
            copy_number=copy_number,
            original_filename=original_filename,
            stored_file_path=stored_file_path,
            file_type=file_type,
            processing_status=processing_status,
        )
        self._db.add(document)
        return self._commit_and_refresh(document)

    def create_many(self, *, documents: list[Document]) -> list[Document]:
        """Persist several documents in a single transaction.

        All rows are added and committed together so the batch is atomic:
        either every document is persisted or none is. Server-generated values
        (ids, timestamps) are reloaded before returning.

        Args:
            documents: Fully-populated :class:`Document` instances (without
                primary keys yet).

        Returns:
            The persisted documents with server-generated fields loaded.

        Raises:
            sqlalchemy.exc.IntegrityError: When any row violates a constraint
                (e.g. the unique copy-slot index). The caller rolls the session
                back and cleans up any files written for the batch.
        """
        self._db.add_all(documents)
        self._db.commit()
        for document in documents:
            self._db.refresh(document)
        return documents

    def get_by_application(
        self,
        application_id: int,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[Document]:
        """Return documents belonging to an application.

        Args:
            application_id: Owning application id.
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.

        Returns:
            A sequence of documents ordered by upload date.
        """
        statement = (
            select(Document)
            .where(Document.application_id == application_id)
            .order_by(Document.uploaded_at.desc(), Document.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return self._db.scalars(statement).all()

    def get_all_by_application(self, application_id: int) -> Sequence[Document]:
        """Return every document belonging to an application, unpaginated.

        Used by verification workflows that must reason over the complete
        document set (e.g. completeness checking) rather than a page of it.

        Args:
            application_id: Owning application id.

        Returns:
            All documents ordered by document type then upload date.
        """
        statement = (
            select(Document)
            .where(Document.application_id == application_id)
            .order_by(Document.document_type, Document.uploaded_at.desc(), Document.id.desc())
        )
        return self._db.scalars(statement).all()

    def update_status(
        self,
        document: Document,
        processing_status: DocumentProcessingStatus,
    ) -> Document:
        """Update a document's processing status.

        Args:
            document: Document instance to update.
            processing_status: New processing status.

        Returns:
            The updated document.
        """
        document.processing_status = processing_status
        self._db.add(document)
        return self._commit_and_refresh(document)

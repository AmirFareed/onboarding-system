"""Filesystem storage backend for uploaded documents.

Files are kept outside the source tree, under ``storage/applications/APP-xxxxxx/
<document-type-slug>/``. Internal filenames are random UUIDs so the client-supplied
name never reaches the disk; the original name is persisted separately in the
database. All reads/writes go through :class:`StorageService`, which guarantees
every resolved path stays inside the configured storage root (path-traversal
proof) and writes atomically via a temporary file + rename so a crash never
leaves a partially written document behind.
"""

import contextlib
import logging
import os
from pathlib import Path
from uuid import uuid4

from app.database.models.enums import DocumentType
from app.upload.constants import (
    APPLICATION_FOLDER_PREFIX,
    APPLICATIONS_DIRECTORY,
    DOCUMENT_TYPE_SLUGS,
)
from app.upload.exceptions import StorageException

logger = logging.getLogger(__name__)


class StorageService:
    """Persist and retrieve uploaded files under a single storage root.

    Args:
        root: Absolute path of the storage directory. Relative paths are
            resolved against the current working directory.
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root).resolve()
        self.ensure_ready()

    @property
    def root(self) -> Path:
        """The resolved absolute storage root."""
        return self._root

    def ensure_ready(self) -> None:
        """Create the storage root directory if it does not exist.

        Raises:
            StorageException: When the root cannot be created or is not a
                directory.
        """
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageException(f"Storage root is not writable: {exc}") from exc
        if not self._root.is_dir():
            raise StorageException("Storage root is not a directory")

    def application_directory(self, application_id: int) -> Path:
        """Absolute path of the storage directory for one application.

        Args:
            application_id: Id of the owning application.

        Returns:
            The application directory (may not exist yet).
        """
        return self._root / APPLICATIONS_DIRECTORY / f"{APPLICATION_FOLDER_PREFIX}{application_id:06d}"

    def save(
        self,
        application_id: int,
        document_type: DocumentType,
        content: bytes,
        extension: str,
    ) -> str:
        """Atomically persist a document and return its relative path.

        The file is written to a temporary sibling and renamed into place so
        concurrent readers never observe a partial document.

        Args:
            application_id: Id of the owning application.
            document_type: Category of the document (determines the sub-dir).
            content: Full file content to persist.
            extension: Validated extension including the leading dot.

        Returns:
            The storage path relative to the storage root (POSIX separators),
            e.g. ``applications/APP-000001/tripartite/ab12....pdf``.

        Raises:
            StorageException: When the directory cannot be created or the file
                cannot be written.
        """
        directory = self.application_directory(application_id) / DOCUMENT_TYPE_SLUGS[document_type]
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageException(f"Cannot create upload directory: {exc}") from exc

        storage_name = f"{uuid4().hex}{extension}"
        destination = directory / storage_name
        temporary = directory / f".{storage_name}.tmp"
        try:
            with temporary.open("wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        except OSError as exc:
            with contextlib.suppress(OSError):
                temporary.unlink(missing_ok=True)
            raise StorageException(f"Cannot store file: {exc}") from exc

        relative = destination.relative_to(self._root).as_posix()
        logger.debug("Stored document at %s", relative)
        return relative

    def delete(self, stored_file_path: str) -> None:
        """Remove a stored file.

        Deleting a missing file is a no-op so the storage layer stays
        idempotent.

        Args:
            stored_file_path: Storage path relative to the storage root.

        Raises:
            StorageException: When the path escapes the storage root.
        """
        target = self.resolve(stored_file_path)
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            raise StorageException(f"Cannot delete file: {exc}") from exc

    def resolve(self, stored_file_path: str) -> Path:
        """Resolve a relative storage path to an absolute, contained path.

        Rejects absolute paths, empty paths and any path that resolves outside
        the storage root, preventing path-traversal access to arbitrary files.

        Args:
            stored_file_path: Storage path relative to the storage root.

        Returns:
            The absolute path of the file.

        Raises:
            StorageException: When the path is empty, absolute or escapes the
                storage root.
        """
        if not stored_file_path:
            raise StorageException("Stored file path is empty")
        candidate = Path(stored_file_path)
        if candidate.is_absolute():
            raise StorageException("Stored file path must be relative")
        try:
            resolved = (self._root / candidate).resolve(strict=False)
        except OSError as exc:
            raise StorageException(f"Invalid stored file path: {exc}") from exc
        if resolved != self._root and self._root not in resolved.parents:
            raise StorageException("Stored file path escapes the storage root")
        return resolved

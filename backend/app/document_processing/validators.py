"""Input validation and routing checks for the document processing module.

Raises the module's domain exceptions so the service can route every document
without embedding error-handling in the extraction code: file resolution raises
:class:`CorruptedDocument`, source classification raises :class:`CorruptedDocument`
when a PDF cannot be probed, and :func:`assert_non_empty_text` guards against
silent empty extractions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from app.document_processing.constants import (
    MIN_DIGITAL_TEXT_CHARS_PER_PAGE,
    DocumentSource,
)
from app.document_processing.exceptions import (
    CorruptedDocument,
    EmptyExtraction,
    UnsupportedDocument,
)
from app.technical_validation.constants import SUPPORTED_EXTENSIONS, FileFormat
from app.upload.storage import StorageService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceDecision:
    """Outcome of classifying a document's text source.

    Attributes:
        source: The routing decision for the document.
        probed_text: Text extracted during the PDF probe for digital PDFs (the
            probe result is reused so the text is never extracted twice).
        page_count: Page count of a PDF, when the document is a PDF.
    """

    source: DocumentSource
    probed_text: str | None = None
    page_count: int | None = None


def resolve_document_file(storage: StorageService, stored_file_path: str) -> Path:
    """Resolve a document's stored path to an absolute, readable file.

    Args:
        storage: Storage backend used for path resolution.
        stored_file_path: Storage path relative to the storage root.

    Returns:
        The absolute path of the document file.

    Raises:
        CorruptedDocument: When the path is invalid or the file is missing or
            unreadable.
    """
    try:
        path = storage.resolve(stored_file_path)
    except Exception as exc:
        raise CorruptedDocument(f"Stored file path is invalid: {exc}") from exc
    if not path.is_file() or not path.exists():
        raise CorruptedDocument("Stored document file does not exist")
    return path


def detect_format(stored_file_path: str) -> FileFormat:
    """Return the normalized format of a document from its stored path.

    Args:
        stored_file_path: Storage path of the document.

    Returns:
        The normalized :class:`FileFormat`.

    Raises:
        UnsupportedDocument: When the extension is not a processable format.
    """
    suffix = Path(stored_file_path).suffix.lower()
    file_format = SUPPORTED_EXTENSIONS.get(suffix)
    if file_format is None:
        raise UnsupportedDocument(
            f"Unsupported file extension {suffix!r}; expected PDF, JPEG or PNG"
        )
    return file_format


def classify_document_source(path: Path, file_format: FileFormat) -> SourceDecision:
    """Determine how a document's text should be obtained.

    A PDF is probed with PyMuPDF: when it already carries selectable text
    averaging at least :data:`MIN_DIGITAL_TEXT_CHARS_PER_PAGE` per page, it is
    routed as a digital PDF (text extracted natively, no OCR); otherwise its
    pages are assumed to be scans. Non-PDF formats are routed as images.

    Args:
        path: Absolute path of the document file.
        file_format: Normalized format of the document.

    Returns:
        The routing decision, carrying the probed text and PDF page count.

    Raises:
        CorruptedDocument: When the PDF cannot be opened or is encrypted.
    """
    if file_format is not FileFormat.PDF:
        return SourceDecision(DocumentSource.IMAGE)
    try:
        with pymupdf.open(str(path)) as document:
            if document.needs_pass:
                raise CorruptedDocument("PDF is password protected")
            page_count = document.page_count
            text = "".join(page.get_text() for page in document)
    except CorruptedDocument:
        raise
    except Exception as exc:
        raise CorruptedDocument(f"Cannot read PDF: {exc}") from exc
    stripped_length = len(text.strip())
    average_chars_per_page = stripped_length / max(page_count, 1)
    if average_chars_per_page >= MIN_DIGITAL_TEXT_CHARS_PER_PAGE:
        logger.info(
            "PDF routed as digital: %s characters of selectable text across %s pages (%.1f/page)",
            stripped_length,
            page_count,
            average_chars_per_page,
        )
        return SourceDecision(DocumentSource.DIGITAL_PDF, text, page_count)
    return SourceDecision(DocumentSource.SCANNED_PDF, None, page_count)


def assert_non_empty_text(text: str) -> None:
    """Guard against a document producing no extracted text.

    Args:
        text: The extracted raw text.

    Raises:
        EmptyExtraction: When the text is empty or only whitespace.
    """
    if not text.strip():
        raise EmptyExtraction()

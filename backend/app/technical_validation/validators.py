"""File-level technical validation checks.

Each function validates one aspect of a stored document and raises a domain
exception when that aspect fails, so the service can turn failures into
per-document failed checks. Checks are deliberately isolated from each other:
the accessibility checks guard the file itself, the format check guards the
document type and the PDF/image checks guard the file structure. No check
inspects document meaning, extracts text or performs OCR.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import cv2
import pymupdf

from app.database.models.document import Document
from app.technical_validation.constants import (
    MIN_IMAGE_HEIGHT,
    MIN_IMAGE_WIDTH,
    SUPPORTED_EXTENSIONS,
    FileFormat,
)
from app.technical_validation.exceptions import (
    CorruptedPDF,
    EmptyFile,
    FileNotFound,
    FileUnreadable,
    InvalidImage,
    PasswordProtectedPDF,
    UnsupportedFileFormat,
)


@dataclass(frozen=True)
class PdfMetrics:
    """Structural measurements of a successfully opened PDF."""

    page_count: int
    dimensions_valid: bool


@dataclass(frozen=True)
class ImageMetrics:
    """Measurements of a successfully loaded image."""

    width: int
    height: int
    resolution_valid: bool


def validate_file_present(path: Path) -> None:
    """Ensure the stored file exists.

    Args:
        path: Absolute path of the stored file.

    Raises:
        FileNotFound: When the file does not exist on the storage backend.
    """
    if not path.exists():
        raise FileNotFound("The stored file does not exist")


def validate_file_readable(path: Path) -> None:
    """Ensure the stored file can be read.

    Args:
        path: Absolute path of the stored file.

    Raises:
        FileUnreadable: When the path is not a file or has no read permission.
    """
    if not path.is_file():
        raise FileUnreadable("The stored path is not a regular file")
    if not os.access(path, os.R_OK):
        raise FileUnreadable("The stored file cannot be read")


def validate_file_not_empty(path: Path) -> None:
    """Ensure the stored file contains data.

    Args:
        path: Absolute path of the stored file.

    Raises:
        EmptyFile: When the file is zero bytes long.
    """
    try:
        if path.stat().st_size == 0:
            raise EmptyFile("The stored file is empty")
    except OSError as exc:
        raise FileUnreadable(f"The stored file cannot be inspected: {exc}") from exc


def detect_format(document: Document) -> tuple[str, FileFormat]:
    """Determine a document's format from its stored file extension.

    The extension is authoritative because the upload module validates the
    content against it via magic bytes before persisting the file.

    Args:
        document: Document metadata whose stored path determines the format.

    Returns:
        A tuple of the display label (e.g. ``"PDF"``, ``"TIFF"``) and the
        normalized :class:`FileFormat` when supported.

    Raises:
        UnsupportedFileFormat: When the extension is not one of the accepted
            PDF/JPEG/PNG formats.
    """
    suffix = Path(document.stored_file_path).suffix.lower()
    file_format = SUPPORTED_EXTENSIONS.get(suffix)
    if file_format is None:
        label = suffix.lstrip(".").upper() or "UNKNOWN"
        raise UnsupportedFileFormat(
            f"File format {label} is not supported; provide a PDF, JPEG or PNG file"
        )
    return file_format.value, file_format


def validate_pdf(path: Path) -> PdfMetrics:
    """Validate a PDF's structure with PyMuPDF.

    Args:
        path: Absolute path of the PDF file.

    Returns:
        The page count and whether every page has positive dimensions.

    Raises:
        CorruptedPDF: When the file cannot be opened or contains no pages.
        PasswordProtectedPDF: When the PDF requires a password to be read.
    """
    try:
        document = pymupdf.open(str(path))
    except (pymupdf.EmptyFileError, pymupdf.FileDataError) as exc:
        raise CorruptedPDF(f"PDF cannot be opened: {exc}") from exc
    except Exception as exc:  # defensive: any open failure is a corrupt document
        raise CorruptedPDF(f"PDF cannot be opened: {exc}") from exc

    try:
        if document.needs_pass:
            raise PasswordProtectedPDF("PDF is password protected")
        page_count = document.page_count
        if page_count < 1:
            raise CorruptedPDF("PDF contains no pages")
        dimensions_valid = all(
            page.rect.width > 0 and page.rect.height > 0 for page in document
        )
    finally:
        document.close()
    return PdfMetrics(page_count=page_count, dimensions_valid=dimensions_valid)


def validate_image(path: Path) -> ImageMetrics:
    """Validate an image file with OpenCV.

    Args:
        path: Absolute path of the image file.

    Returns:
        The image dimensions and whether they meet the minimum resolution.

    Raises:
        InvalidImage: When the file cannot be loaded as an image.
    """
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise InvalidImage("The image cannot be loaded")
    height, width = image.shape[:2]
    if height <= 0 or width <= 0:
        raise InvalidImage("The image has invalid dimensions")
    resolution_valid = width >= MIN_IMAGE_WIDTH and height >= MIN_IMAGE_HEIGHT
    return ImageMetrics(width=width, height=height, resolution_valid=resolution_valid)

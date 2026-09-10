"""File and metadata validators for uploads.

Validation never trusts the client: the extension is extracted from the raw
filename, path separators and traversal sequences are stripped, the extension is
checked against an allow-list and the file content is sniffed via magic bytes to
confirm the declared media type. Any mismatch produces a domain-specific
exception that the routes map to an HTTP error.
"""

import os
import re

from app.upload.constants import (
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME_TYPES,
    EXTENSIONS_BY_MIME_TYPE,
    GENERIC_MIME_TYPES,
    MAGIC_BYTES,
    SNIFF_BYTES,
)
from app.upload.exceptions import InvalidFileTypeException

#: Characters that are never allowed inside a stored filename.
_UNSAFE_FILENAME_CHARS = re.compile(r"[^\w.\- ()]+")

#: Maximum length accepted for the sanitized filename (DB column is 255 chars).
_MAX_FILENAME_LENGTH = 255


def sanitize_filename(filename: str) -> str:
    """Return a safe base filename derived from the client-supplied name.

    Reduces the input to its basename (removing any path separators or parent
    directory references), strips unsafe characters, collapses whitespace and
    truncates to the database column limit.

    Args:
        filename: Raw filename supplied by the uploader.

    Returns:
        The sanitized basename, or an empty string when nothing remains.

    Raises:
        InvalidFileTypeException: When the filename is empty or collapses to an
            empty string.
    """
    if not filename or not filename.strip():
        raise InvalidFileTypeException("The file has no filename")

    # Backslashes are treated as path separators so Windows-style traversal
    # (``..\\x``) is neutralised even on POSIX hosts, where ``basename`` alone
    # would not split on them.
    normalized = filename.replace("\\", "/")
    base = os.path.basename(normalized.rstrip())
    if not base or base in {".", ".."}:
        raise InvalidFileTypeException("The file has no valid filename")

    sanitized = _UNSAFE_FILENAME_CHARS.sub(" ", base)
    sanitized = " ".join(sanitized.split())
    if not sanitized:
        raise InvalidFileTypeException("The file has no valid filename")
    return sanitized[:_MAX_FILENAME_LENGTH]


def extract_extension(filename: str) -> str:
    """Return the lower-cased extension (with dot) of a sanitized filename.

    Args:
        filename: Filename to inspect.

    Returns:
        The extension including the leading dot, or an empty string when the
        file has no extension.
    """
    root, ext = os.path.splitext(filename)
    if not root:
        return ""
    return ext.lower()


def validate_extension(extension: str) -> None:
    """Ensure the extension belongs to the allowed document formats.

    Args:
        extension: Extension including the leading dot.

    Raises:
        InvalidFileTypeException: When the extension is not allowed.
    """
    if extension not in ALLOWED_EXTENSIONS:
        raise InvalidFileTypeException(
            f"File extension {extension or '<none>'} is not supported"
        )


def sniff_extension(content: bytes) -> str | None:
    """Determine the file format from its magic bytes.

    Args:
        content: Leading bytes of the file.

    Returns:
        The extension of the recognised format, or ``None`` when the content
        cannot be identified.
    """
    head = content[:SNIFF_BYTES]
    for magic, extension in MAGIC_BYTES.items():
        if head.startswith(magic):
            return extension
    return None


def validate_file_content(
    filename: str,
    declared_content_type: str,
    content: bytes,
) -> str:
    """Validate an uploaded file end to end.

    Checks the sanitized filename, the extension allow-list, the sniffed magic
    bytes and the declared media type. Returns the authoritative extension so
    the storage layer can assign a matching internal filename.

    Args:
        filename: Raw filename supplied by the uploader.
        declared_content_type: Media type reported by the uploader.
        content: At least :data:`SNIFF_BYTES` bytes of the file content.

    Returns:
        The validated, lower-cased extension including the leading dot.

    Raises:
        InvalidFileTypeException: When any validation step fails, including
            empty files or content that cannot be recognised.
    """
    safe_name = sanitize_filename(filename)
    extension = extract_extension(safe_name)
    validate_extension(extension)

    if not content:
        raise InvalidFileTypeException("The uploaded file is empty")

    sniffed = sniff_extension(content)
    if sniffed is None:
        raise InvalidFileTypeException(
            "File content could not be recognised as a supported document type"
        )
    if sniffed != extension:
        raise InvalidFileTypeException(
            f"File content ({sniffed}) does not match its extension ({extension})"
        )

    declared = (declared_content_type or "").lower().split(";")[0].strip()
    if declared in GENERIC_MIME_TYPES:
        # A generic/absent declared type carries no format information; the
        # sniffed content is authoritative.
        return extension
    if declared in ALLOWED_MIME_TYPES:
        if extension not in EXTENSIONS_BY_MIME_TYPE.get(declared, frozenset()):
            raise InvalidFileTypeException(
                f"Declared media type ({declared}) does not match file content"
            )
        return extension
    raise InvalidFileTypeException(
        f"Declared media type ({declared}) is not supported"
    )

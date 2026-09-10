"""Unit tests for the upload validators (no database or filesystem needed)."""

import pytest

from app.upload.exceptions import InvalidFileTypeException
from app.upload.validators import (
    extract_extension,
    sanitize_filename,
    sniff_extension,
    validate_extension,
    validate_file_content,
)

PDF_BYTES = b"%PDF-1.4\n...%%EOF\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR..." + b"\x00" * 64


def test_sanitize_filename_strips_directories():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\scan.pdf") == "scan.pdf"
    assert sanitize_filename("a/b/c/report.pdf") == "report.pdf"


def test_sanitize_filename_rejects_empty():
    with pytest.raises(InvalidFileTypeException):
        sanitize_filename("")
    with pytest.raises(InvalidFileTypeException):
        sanitize_filename("   ")
    with pytest.raises(InvalidFileTypeException):
        sanitize_filename("..")


def test_sanitize_filename_truncates_long_names():
    long_name = "x" * 500 + ".pdf"
    assert len(sanitize_filename(long_name)) == 255


def test_extract_extension():
    assert extract_extension("scan.PDF") == ".pdf"
    assert extract_extension("scan") == ""


def test_validate_extension_allowlist():
    validate_extension(".pdf")
    validate_extension(".tiff")
    with pytest.raises(InvalidFileTypeException):
        validate_extension(".exe")
    with pytest.raises(InvalidFileTypeException):
        validate_extension("")


def test_sniff_extension():
    assert sniff_extension(PDF_BYTES) == ".pdf"
    assert sniff_extension(PNG_BYTES) == ".png"
    assert sniff_extension(b"plain text content here") is None
    assert sniff_extension(b"") is None


def test_validate_file_content_ok():
    assert validate_file_content("scan.pdf", "application/pdf", PDF_BYTES) == ".pdf"
    assert validate_file_content("scan.png", "image/png", PNG_BYTES) == ".png"


def test_validate_file_content_empty():
    with pytest.raises(InvalidFileTypeException, match="empty"):
        validate_file_content("scan.pdf", "application/pdf", b"")


def test_validate_file_content_unrecognized():
    with pytest.raises(InvalidFileTypeException, match="recognised"):
        validate_file_content("scan.pdf", "application/pdf", b"not a real file")


def test_validate_file_content_extension_mismatch():
    with pytest.raises(InvalidFileTypeException, match="does not match"):
        validate_file_content("scan.png", "image/png", PDF_BYTES)


def test_validate_file_content_declared_mime_mismatch():
    with pytest.raises(InvalidFileTypeException, match="not supported"):
        validate_file_content("scan.pdf", "text/plain", PDF_BYTES)


def test_validate_file_content_octet_stream_passes_sniffed_content():
    assert validate_file_content("scan.pdf", "application/octet-stream", PDF_BYTES) == ".pdf"


def test_validate_file_content_unsafe_filename():
    with pytest.raises(InvalidFileTypeException):
        validate_file_content("", "application/pdf", PDF_BYTES)

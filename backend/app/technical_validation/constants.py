"""Configuration for the technical file validation module.

Centralizes the accepted file formats, the numeric thresholds used by the
image/PDF analysis checks and the opaque identifiers of every technical check.
Verification logic consumes these constants, so tuning a threshold or adding a
check never requires touching the service, route or schema code.
"""

from enum import StrEnum

from app.database.models.enums import Severity


class FileFormat(StrEnum):
    """File formats accepted for downstream processing.

    Upload accepts more formats (e.g. Word, TIFF); technical validation only
    admits formats the OCR/preprocessing pipeline can actually consume.
    """

    PDF = "PDF"
    JPEG = "JPEG"
    PNG = "PNG"


class RotationStatus(StrEnum):
    """Whether a document's content appears rotated from the upright layout."""

    NOT_ROTATED = "NOT_ROTATED"
    ROTATED = "ROTATED"


class ReadabilityStatus(StrEnum):
    """Overall technical readability of a document, determined without OCR."""

    READABLE = "READABLE"
    PARTIALLY_READABLE = "PARTIALLY_READABLE"
    UNREADABLE = "UNREADABLE"


#: Category stored on every technical validation check row so the rule engine's
#: rows can be told apart from the technical validation module's rows.
TECHNICAL_VALIDATION_RULE_CATEGORY: str = "technical_validation"

#: File extensions accepted by technical validation, mapped to the normalized
#: format reported to clients.
SUPPORTED_EXTENSIONS: dict[str, FileFormat] = {
    ".pdf": FileFormat.PDF,
    ".jpg": FileFormat.JPEG,
    ".jpeg": FileFormat.JPEG,
    ".png": FileFormat.PNG,
}

#: Minimum image dimensions (pixels) for a document to be considered readable.
MIN_IMAGE_WIDTH: int = 800
MIN_IMAGE_HEIGHT: int = 800

#: Variance-of-Laplacian score below which an image is considered blurry.
BLUR_THRESHOLD: float = 100.0

#: Maximum absolute rotation (degrees) before a document is flagged as rotated.
ROTATION_TOLERANCE_DEGREES: float = 3.0

#: Gray value below which a pixel counts as ink when measuring page content.
BLANK_INK_GRAY_THRESHOLD: int = 200

#: Maximum fraction of ink pixels a page may have before it is considered blank.
#: A page with less than this share of non-background pixels has no usable
#: content and is flagged as blank.
BLANK_INK_RATIO: float = 0.005

#: Resolution used when rendering a PDF page for blur/rotation analysis.
PDF_RENDER_DPI: int = 150

#: Resolution used when rendering a PDF page (dots per inch -> pixels per point).
_DOTS_PER_POINT: float = PDF_RENDER_DPI / 72.0

# -- Technical check identifiers ---------------------------------------------

#: File accessibility checks.
CHECK_FILE_EXISTS: str = "TECH_FILE_EXISTS"
CHECK_FILE_READABLE: str = "TECH_FILE_READABLE"
CHECK_FILE_NOT_EMPTY: str = "TECH_FILE_NOT_EMPTY"

#: File type check.
CHECK_FILE_TYPE: str = "TECH_FILE_TYPE"

#: PDF structural checks.
CHECK_PDF_OPEN: str = "TECH_PDF_OPEN"
CHECK_PDF_PASSWORD: str = "TECH_PDF_PASSWORD"
CHECK_PDF_PAGES: str = "TECH_PDF_PAGES"
CHECK_PDF_DIMENSIONS: str = "TECH_PDF_DIMENSIONS"
CHECK_PDF_RENDER: str = "TECH_PDF_RENDER"

#: Image checks.
CHECK_IMAGE_LOAD: str = "TECH_IMAGE_LOAD"
CHECK_IMAGE_RESOLUTION: str = "TECH_IMAGE_RESOLUTION"

#: Visual content checks (apply to images and rendered PDF pages).
CHECK_BLUR: str = "TECH_BLUR"
CHECK_ROTATION: str = "TECH_ROTATION"
CHECK_BLANK_PAGE: str = "TECH_BLANK_PAGE"

#: Aggregate readability check.
CHECK_READABILITY: str = "TECH_READABILITY"

#: Severity assigned to a check that passed.
SEVERITY_PASS: Severity = Severity.INFO
#: Severity assigned to a check that produced a warning.
SEVERITY_WARNING: Severity = Severity.WARNING
#: Severity assigned to a check that failed.
SEVERITY_FAIL: Severity = Severity.ERROR

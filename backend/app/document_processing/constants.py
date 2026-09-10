"""Configuration for the document processing module.

Centralizes the document source classification, the processing methods and OCR
engine identifiers, and the thresholds that drive routing and timeout behaviour.
The service and processor code consume these constants, so tuning a threshold or
adding a processing method never requires touching the route or schema layers.
"""

from enum import StrEnum

from app.technical_validation.constants import FileFormat


class DocumentSource(StrEnum):
    """How a document's text is most reliably obtained.

    A PDF is ``DIGITAL_PDF`` when it already carries selectable text (extracted
    directly with PyMuPDF) and ``SCANNED_PDF`` when its pages are images that
    must be OCR'd. Non-PDF formats are ``IMAGE`` documents.
    """

    DIGITAL_PDF = "DIGITAL_PDF"
    SCANNED_PDF = "SCANNED_PDF"
    IMAGE = "IMAGE"


class ProcessingMethod(StrEnum):
    """How the raw text of a document was produced."""

    PYMUFPDF_TEXT_EXTRACTION = "PYMUFPDF_TEXT_EXTRACTION"
    PADDLE_OCR = "PADDLE_OCR"


#: Identifier stored for text extracted natively with PyMuPDF.
PYMUPDF_ENGINE: str = "pymupdf"

#: Identifier stored for text produced by the PaddleOCR engine.
PADDLE_OCR_ENGINE: str = "paddleocr"

#: Minimum average selectable-text characters per page for a PDF to be routed
#: as digital. Below this the pages are assumed to be scans and OCR is used
#: instead. A flat total (rather than per-page) threshold let scanner-app
#: exports slip through as "digital": apps like CamScanner stamp a short
#: watermark as real selectable text on every page (e.g. "CamScanner" x9
#: pages = 99 characters), which used to clear a flat 10-character bar despite
#: the actual page content being an untranscribed image.
MIN_DIGITAL_TEXT_CHARS_PER_PAGE: int = 40

#: Resolution used when rendering scanned PDF pages for OCR input (dots per inch).
SCANNED_PDF_RENDER_DPI: int = 200

#: Per-page wall-clock budget in seconds for PaddleOCR fallback, used to size
#: the extraction deadline once a scanned document's real page count is known.
#: A flat per-document budget doesn't scale: real uploads seen in this system
#: range from 1 to 21+ pages, and CPU-only PaddleOCR has measured 90-150s per
#: page, so a fixed total either times out large documents or wastes an
#: enormous idle budget on small ones.
PROCESSING_TIMEOUT_SECONDS_PER_PAGE: float = 180.0

#: Floor applied to the computed per-document deadline (page_count *
#: PROCESSING_TIMEOUT_SECONDS_PER_PAGE) so very short documents still get a
#: sane minimum budget for engine warm-up and per-page overhead.
MIN_PROCESSING_TIMEOUT_SECONDS: float = 180.0

#: Separator inserted between the text of consecutive pages so merged output
#: keeps page boundaries visible and page order preserved.
PAGE_SEPARATOR: str = "\n\n--- Page {page_index} ---\n\n"

#: Document sources whose text must be produced by an OCR engine.
OCR_SOURCES: frozenset[DocumentSource] = frozenset(
    {DocumentSource.SCANNED_PDF, DocumentSource.IMAGE}
)

#: File formats that are processed by the module (mirrors the formats admitted
#: by technical validation).
PROCESSABLE_FORMATS: frozenset[FileFormat] = frozenset(
    {FileFormat.PDF, FileFormat.JPEG, FileFormat.PNG}
)

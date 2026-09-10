"""Document text extractors and the OCR engine abstraction.

Encapsulates the three routing paths: digital PDFs are read natively with
PyMuPDF, while scanned PDFs and images are preprocessed and OCR'd. OCR engines
implement the :class:`OCREngine` protocol; the default production engine is
:class:`PaddleOCREngine`, and the module-level :data:`_create_ocr_engine`
factory is the dependency-injection seam tests use to substitute a fake engine.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from app.document_processing.constants import (
    PADDLE_OCR_ENGINE,
    PAGE_SEPARATOR,
    PYMUPDF_ENGINE,
    ProcessingMethod,
)
from app.document_processing.exceptions import (
    CorruptedDocument,
    OCRProcessingFailed,
    ProcessingTimeout,
)
from app.document_processing.utils import iter_pdf_pages, preprocess_image

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OCRExtraction:
    """Text and confidence produced by one OCR engine call over one image.

    Attributes:
        text: Recognized text lines joined by newlines.
        confidence: Mean recognition confidence in ``[0, 1]``, or ``None`` when
            the engine reports none.
    """

    text: str
    confidence: float | None


class OCREngine(Protocol):
    """Interface every OCR engine implements."""

    def extract(self, image: np.ndarray) -> OCRExtraction:
        """Recognize text in a preprocessed document image.

        Args:
            image: Preprocessed (binary) document image.

        Returns:
            The recognized text and its confidence.
        """


@dataclass(frozen=True)
class ExtractionResult:
    """Full outcome of processing one document.

    Attributes:
        text: Merged raw text across every page, in page order.
        ocr_engine: Identifier of the engine that produced the text.
        processing_method: How the text was produced.
        overall_confidence: Mean confidence, or ``None`` for native extraction.
        page_count: Number of pages that contributed to the text.
        character_count: Length of the merged text.
    """

    text: str
    ocr_engine: str
    processing_method: ProcessingMethod
    overall_confidence: float | None
    page_count: int
    character_count: int


def _join_pages(page_texts: list[str]) -> str:
    """Join per-page text with page separators, preserving page order."""
    merged: list[str] = []
    for index, page_text in enumerate(page_texts, start=1):
        if merged:
            merged.append(PAGE_SEPARATOR.format(page_index=index))
        merged.append(page_text)
    return "".join(merged)


class PaddleOCREngine:
    """OCR engine backed by PaddleOCR (PP-OCR models).

    The PaddleOCR instance is created once per process (module-level singleton)
    because constructing it downloads and loads the detection/recognition models,
    which is expensive. Document orientation classification, unwarping and
    textline orientation are disabled: the module performs its own preprocessing
    and only needs plain text recognition. MKLDNN is disabled because consecutive
    predictions over differently-sized images crash the Paddle predictor with a
    native ``std::exception`` (see PaddlePaddle/PaddleOCR#17787); inference runs
    on the plain CPU backend instead.

    A fresh ``PaddleOCREngine()`` is constructed per document (see
    ``ocr_engine_factory``), but every instance in the *same process* shares
    the one underlying predictor via ``_engine`` (a class attribute, not an
    instance one). Two worker threads sharing a process (the in-process dev
    convenience path, ``app.bulk_queue.workers.drain_queue``) can each hold a
    different ``PaddleOCREngine`` instance that both call ``predict()`` on
    that same shared predictor at the same time -- undefined behaviour for a
    native predictor already known to crash under milder concurrent-call
    conditions (see the MKLDNN note above). ``_predict_lock`` serializes
    every ``predict()`` call across every instance *within one process* so
    this can't happen.

    This is a non-issue across separate OS processes: each process gets its
    own module-level ``_engine`` (nothing is shared at the OS level), so
    separate processes never contend on the same native predictor and never
    need this lock to coordinate with each other. This is exactly why the
    dedicated worker entrypoint (``python -m app.bulk_queue``,
    ``app/bulk_queue/__main__.py``) runs each configured worker as its own
    process rather than a thread: that's genuine parallelism, whereas N
    worker threads in one process would still serialize through this same
    lock and OCR only one document at a time regardless of the configured
    worker count.
    """

    _engine: object | None = None
    #: Class attribute, not an instance one: every ``PaddleOCREngine()`` shares
    #: the same predictor via ``_engine``, so every instance must serialize
    #: through the same lock, not a fresh (and useless) per-instance lock.
    _predict_lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        self._engine = self._get_engine()

    @classmethod
    def _get_engine(cls) -> object:
        """Return the shared PaddleOCR instance, creating it on first use."""
        if cls._engine is None:
            try:
                from paddleocr import PaddleOCR
            except ImportError as exc:
                raise OCRProcessingFailed(
                    "PaddleOCR is not installed in this environment"
                ) from exc
            try:
                cls._engine = PaddleOCR(
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    lang="en",
                    enable_mkldnn=False,
                )
            except Exception as exc:
                raise OCRProcessingFailed(
                    f"Failed to initialise PaddleOCR: {exc}"
                ) from exc
        return cls._engine

    def extract(self, image: np.ndarray) -> OCRExtraction:
        """Run PaddleOCR over a preprocessed document image.

        Args:
            image: Preprocessed document image.

        Returns:
            Recognized text lines and their mean confidence.

        Raises:
            OCRProcessingFailed: When PaddleOCR fails to process the image.
        """
        try:
            predict_image = self._to_predict_image(image)
            # Serializes concurrent predict() calls across every worker thread
            # to avoid the PaddlePaddle native crash bug (see the class
            # docstring and PaddlePaddle/PaddleOCR#17787).
            with self._predict_lock:
                results = self._engine.predict(predict_image)
        except Exception as exc:
            raise OCRProcessingFailed(f"PaddleOCR failed to process the image: {exc}") from exc
        texts: list[str] = []
        scores: list[float] = []
        for page in results:
            page_texts, page_scores = _parse_ocr_page(page)
            texts.extend(page_texts)
            scores.extend(page_scores)
        text = "\n".join(texts)
        confidence = float(np.mean(scores)) if scores else None
        logger.info(
            "PaddleOCR recognized %s text lines with mean confidence %s",
            len(texts),
            confidence,
        )
        return OCRExtraction(text=text, confidence=confidence)

    @staticmethod
    def _to_predict_image(image: np.ndarray) -> np.ndarray:
        """Normalize the image into the shape the PaddleOCR predictor expects.

        The preprocessing pipeline hands the engine a binary grayscale image
        (2D), but the PaddleOCR predictor expects a three-channel image and
        raises on 2D input. Grayscale pages are expanded to three channels
        (identical channels carry no extra information) so the predictor accepts
        them unchanged.

        Args:
            image: Preprocessed document image (2D grayscale or 3-channel).

        Returns:
            An image the PaddleOCR predictor can consume.
        """
        if image.ndim == 2:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        return image


def _parse_ocr_page(page: object) -> tuple[list[str], list[float]]:
    """Extract recognized texts and scores from one PaddleOCR result page.

    PaddleOCR 3.x returns ``PaddleResult`` objects exposing a ``json`` mapping
    (``{"res": {"rec_texts": [...], "rec_scores": [...]}}``); the 2.x-style
    nested list shape (``[[box, (text, score)], ...]``) is supported as a
    defensive fallback.

    Args:
        page: One page of the OCR engine result.

    Returns:
        The recognized text lines and their confidence scores.
    """
    payload = page
    json_value = getattr(page, "json", None)
    if callable(json_value):
        payload = json_value()
    elif json_value is not None:
        payload = json_value
    if isinstance(payload, dict):
        res = payload.get("res", payload)
        if isinstance(res, dict):
            texts = [str(value) for value in (res.get("rec_texts") or [])]
            scores = [float(value) for value in (res.get("rec_scores") or [])]
            return texts, scores
    texts: list[str] = []
    scores: list[float] = []
    for line in payload if isinstance(payload, (list, tuple)) else [payload]:
        entries = line if isinstance(line, (list, tuple)) else [line]
        for entry in entries:
            if (
                isinstance(entry, (list, tuple))
                and len(entry) == 2
                and isinstance(entry[1], (list, tuple))
                and len(entry[1]) == 2
            ):
                texts.append(str(entry[1][0]))
                scores.append(float(entry[1][1]))
    return texts, scores


def _create_ocr_engine() -> OCREngine:
    """Build the default OCR engine used by the processing service.

    Tests substitute this factory (or the service-level factory) with a fake
    engine so the pipeline runs without downloading OCR models.
    """
    return PaddleOCREngine()


class DigitalPdfExtractor:
    """Extract text natively from a digital PDF with PyMuPDF.

    The text is already available from the routing probe, so no file re-read or
    OCR happens here.
    """

    def __init__(self, text: str, page_count: int) -> None:
        self._text = text
        self._page_count = page_count

    def extract(self) -> ExtractionResult:
        """Return the probed digital PDF text as the extraction result."""
        return ExtractionResult(
            text=self._text,
            ocr_engine=PYMUPDF_ENGINE,
            processing_method=ProcessingMethod.PYMUFPDF_TEXT_EXTRACTION,
            overall_confidence=None,
            page_count=self._page_count,
            character_count=len(self._text),
        )


class ScannedPdfExtractor:
    """OCR a scanned PDF page by page.

    Every page is rendered to an image, preprocessed and OCR'd independently;
    the per-page text is then merged in page order. The per-document deadline is
    checked between pages so a run that exceeds its budget stops early.
    """

    def __init__(
        self,
        ocr_engine: OCREngine,
        path: Path,
        deadline: float | None = None,
    ) -> None:
        self._ocr_engine = ocr_engine
        self._path = path
        self._deadline = deadline

    def extract(self) -> ExtractionResult:
        """OCR every page and merge the resulting text.

        Pages are rendered lazily one at a time so a multi-page scan never holds
        every page image in memory at once: each rendered page is preprocessed,
        OCR'd and then released before the next page is rendered. Render errors
        surface as ``CorruptedDocument`` while engine errors propagate as before.
        """
        pages = iter_pdf_pages(self._path)
        page_texts: list[str] = []
        scores: list[float] = []
        index = 0
        while True:
            try:
                page_image = next(pages)
            except StopIteration:
                break
            except Exception as exc:
                raise CorruptedDocument(f"Cannot render PDF pages: {exc}") from exc
            index += 1
            if self._deadline is not None and time.monotonic() > self._deadline:
                raise ProcessingTimeout()
            logger.info(
                "OCR started for page %s of PDF %r",
                index,
                str(self._path),
            )
            preprocessed = preprocess_image(page_image)
            extraction = self._ocr_engine.extract(preprocessed)
            if extraction.confidence is not None:
                scores.append(extraction.confidence)
            page_texts.append(extraction.text)
            logger.info(
                "OCR completed for page %s of PDF %r",
                index,
                str(self._path),
            )
        text = _join_pages(page_texts)
        confidence = float(np.mean(scores)) if scores else None
        return ExtractionResult(
            text=text,
            ocr_engine=PADDLE_OCR_ENGINE,
            processing_method=ProcessingMethod.PADDLE_OCR,
            overall_confidence=confidence,
            page_count=index,
            character_count=len(text),
        )


class ImageExtractor:
    """OCR a single image document."""

    def __init__(self, ocr_engine: OCREngine, path: Path) -> None:
        self._ocr_engine = ocr_engine
        self._path = path

    def extract(self) -> ExtractionResult:
        """Preprocess the image and OCR it."""
        image = cv2.imread(str(self._path), cv2.IMREAD_COLOR)
        if image is None:
            raise CorruptedDocument(f"Image cannot be loaded from {self._path}")
        logger.info("OCR started for image %r", str(self._path))
        preprocessed = preprocess_image(image)
        extraction = self._ocr_engine.extract(preprocessed)
        logger.info("OCR completed for image %r", str(self._path))
        return ExtractionResult(
            text=extraction.text,
            ocr_engine=PADDLE_OCR_ENGINE,
            processing_method=ProcessingMethod.PADDLE_OCR,
            overall_confidence=extraction.confidence,
            page_count=1,
            character_count=len(extraction.text),
        )

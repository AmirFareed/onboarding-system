"""Low-level document preprocessing helpers.

Pure, side-effect free OpenCV functions that prepare an image for OCR: deskew,
denoise, contrast enhancement and adaptive thresholding, combined into a single
:func:`preprocess_image` pipeline. Page rendering for scanned PDFs reuses
PyMuPDF through the lazy :func:`iter_pdf_pages` iterator (with the eager
:func:`render_pdf_pages` kept as a compatibility wrapper). These helpers never
raise the module's domain exceptions; exception-raising checks live in
:mod:`app.document_processing.validators`.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from pathlib import Path

import cv2
import numpy as np

from app.document_processing.constants import SCANNED_PDF_RENDER_DPI
from app.technical_validation.utils import estimate_rotation_angle

logger = logging.getLogger(__name__)

#: Edge-preserving denoise strength (diameter of each pixel neighbourhood).
_DENOISE_DIAMETER: int = 9
#: Colour filter sigma for the bilateral filter.
_DENOISE_SIGMA_COLOR: float = 75.0
#: Spatial sigma for the bilateral filter.
_DENOISE_SIGMA_SPACE: float = 75.0
#: CLAHE clip limit (contrast enhancement strength).
_CLAHE_CLIP_LIMIT: float = 2.0
#: CLAHE tile grid size used for local histogram equalization.
_CLAHE_TILE_GRID_SIZE: tuple[int, int] = (8, 8)
#: Adaptive threshold neighbourhood size (must be odd).
_ADAPTIVE_BLOCK_SIZE: int = 31
#: Constant subtracted from the adaptive mean.
_ADAPTIVE_C: float = 10.0
#: White border value used when deskewing rotates the image.
_DESKEW_BORDER_VALUE: int = 255


def to_grayscale(image: np.ndarray) -> np.ndarray:
    """Convert a BGR image to a single-channel grayscale image.

    Args:
        image: A BGR image as returned by OpenCV.

    Returns:
        The grayscale equivalent of ``image``.
    """
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def deskew_image(image: np.ndarray) -> np.ndarray:
    """Rotate an image so its content is aligned with the page axes.

    Estimates the dominant rotation via a Hough transform on the image's edges
    (reusing :func:`estimate_rotation_angle`) and rotates the image by the
    negative of that angle, filling the exposed background with white. Images
    that are already upright (or have no detectable line structure) pass through
    unmodified. Accepts BGR or grayscale input and preserves the channel count.

    Args:
        image: A BGR or grayscale image to deskew.

    Returns:
        The deskewed image, preserving the input channel count.
    """
    angle_source = image
    if image.ndim == 2:
        angle_source = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    angle = estimate_rotation_angle(angle_source)
    if abs(angle) < 0.5:
        return image
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle, 1.0)
    border_value = (
        (_DESKEW_BORDER_VALUE, _DESKEW_BORDER_VALUE, _DESKEW_BORDER_VALUE)
        if image.ndim == 3
        else _DESKEW_BORDER_VALUE
    )
    return cv2.warpAffine(
        image,
        matrix,
        (width, height),
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=border_value,
    )


def denoise_image(image: np.ndarray) -> np.ndarray:
    """Reduce sensor and compression noise while preserving edges.

    Uses an edge-preserving bilateral filter so text strokes stay sharp while
    flat scan noise is suppressed.

    Args:
        image: A grayscale image to denoise.

    Returns:
        The denoised grayscale image.
    """
    return cv2.bilateralFilter(
        image,
        _DENOISE_DIAMETER,
        _DENOISE_SIGMA_COLOR,
        _DENOISE_SIGMA_SPACE,
    )


def enhance_contrast(image: np.ndarray) -> np.ndarray:
    """Enhance local contrast with CLAHE.

    Applies Contrast Limited Adaptive Histogram Equalization on the grayscale
    image so faint printed text becomes more distinct without amplifying noise.

    Args:
        image: A grayscale image to enhance.

    Returns:
        The contrast-enhanced grayscale image.
    """
    clahe = cv2.createCLAHE(
        clipLimit=_CLAHE_CLIP_LIMIT,
        tileGridSize=_CLAHE_TILE_GRID_SIZE,
    )
    return clahe.apply(image)


def adaptive_threshold(image: np.ndarray) -> np.ndarray:
    """Binarize a grayscale image with adaptive thresholding.

    Uses a Gaussian-weighted local mean so uneven illumination across the scan
    does not wash out the text. Produces a binary image (white background, black
    text) suitable for OCR.

    Args:
        image: A grayscale image to binarize.

    Returns:
        The binary image.
    """
    return cv2.adaptiveThreshold(
        image,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        _ADAPTIVE_BLOCK_SIZE,
        _ADAPTIVE_C,
    )


def preprocess_image(image: np.ndarray) -> np.ndarray:
    """Run the full preprocessing pipeline on one document image.

    Order: grayscale conversion -> deskew -> denoise -> CLAHE contrast
    enhancement -> adaptive thresholding. The result is a binary image with
    upright, denoised, high-contrast text ready for OCR.

    Args:
        image: A BGR document image (rendered PDF page or decoded image).

    Returns:
        The preprocessed binary image.
    """
    gray = to_grayscale(image)
    gray = deskew_image(gray)
    gray = denoise_image(gray)
    gray = enhance_contrast(gray)
    return adaptive_threshold(gray)


def iter_pdf_pages(path: str | Path, dpi: int = SCANNED_PDF_RENDER_DPI) -> Generator[np.ndarray]:
    """Render a PDF's pages one at a time, in page order.

    Yielding pages lazily keeps only a single rendered page (plus its
    preprocessed derivative) in memory at any moment, so OCR of a large scanned
    PDF never materializes every page image at once. Errors surface on the first
    ``next()`` call that hits them (``ValueError`` when the PDF is empty,
    encrypted or a page cannot render).

    Args:
        path: Path of the PDF file.
        dpi: Resolution of the render (defaults to
            :data:`SCANNED_PDF_RENDER_DPI`).

    Yields:
        One BGR image per page, in page order.

    Raises:
        ValueError: When the PDF is empty, encrypted or a page cannot render.
    """
    import pymupdf

    scale = dpi / 72.0
    with pymupdf.open(str(path)) as document:
        if document.needs_pass:
            raise ValueError("PDF is password protected")
        if document.page_count == 0:
            raise ValueError("PDF contains no pages")
        for page in document:
            pixmap = page.get_pixmap(
                matrix=pymupdf.Matrix(scale, scale),
                alpha=False,
            )
            samples = np.frombuffer(pixmap.samples, dtype=np.uint8)
            yield samples.reshape(pixmap.height, pixmap.width, pixmap.n)


def render_pdf_pages(path: str | Path, dpi: int = SCANNED_PDF_RENDER_DPI) -> list[np.ndarray]:
    """Render every page of a PDF to a list of BGR images.

    Convenience wrapper around :func:`iter_pdf_pages` for callers that need the
    whole document at once; processing code should prefer the lazy iterator to
    bound peak memory.

    Args:
        path: Path of the PDF file.
        dpi: Resolution of the render (defaults to
            :data:`SCANNED_PDF_RENDER_DPI`).

    Returns:
        One BGR image per page, in page order.

    Raises:
        ValueError: When the PDF is empty, encrypted or a page cannot render.
    """
    return list(iter_pdf_pages(path, dpi))

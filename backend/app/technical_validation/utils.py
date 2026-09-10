"""Low-level technical analysis helpers.

Pure, side-effect free functions that measure document quality: sharpness
(Variance of Laplacian), rotation (Hough line estimation) and PDF page
rendering. They never raise the module's domain exceptions -- exception-raising
checks live in :mod:`app.technical_validation.validators` -- so the service can
treat a ``None`` return as "could not analyse" without coupling to error types.
"""

from __future__ import annotations

import logging
import math

import cv2
import numpy as np

from app.technical_validation.constants import (
    _DOTS_PER_POINT,
    BLANK_INK_GRAY_THRESHOLD,
    BLANK_INK_RATIO,
)

logger = logging.getLogger(__name__)


def variance_of_laplacian(image: np.ndarray) -> float:
    """Return the sharpness of an image using tiled Variance of Laplacian.

    A global Variance of Laplacian artificially lowers the score of sparse
    pages (mostly whitespace) because the variance is dominated by zero-edge
    background. Computing the 95th percentile of variance over a grid of tiles
    ensures that a sparse page with sharp text correctly scores high, while
    preventing localized noise (like a single sharp staple mark) from causing
    a completely blurry page to falsely pass. The result is compared against
    :data:`BLUR_THRESHOLD`.

    Args:
        image: An RGB (BGR) image as returned by OpenCV.

    Returns:
        The 95th percentile Variance of Laplacian across 256x256 tiles (``>= 0``).
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    
    tile_size = 256
    h, w = lap.shape
    
    variances = []
    for y in range(0, h, tile_size):
        for x in range(0, w, tile_size):
            variances.append(lap[y:y+tile_size, x:x+tile_size].var())
            
    if not variances:
        return 0.0
        
    return float(np.percentile(variances, 95))


def is_blank_image(image: np.ndarray) -> bool:
    """Return whether an image contains essentially no content (blank page).

    A blank page is a near-uniform background: the share of "ink" pixels
    (significantly darker than the background) falls below
    :data:`BLANK_INK_RATIO`. This is measured on the grayscale image so a
    colored background still reads as blank when it carries no text or shapes.

    Args:
        image: An RGB (BGR) image as returned by OpenCV.

    Returns:
        ``True`` when the image is blank, ``False`` otherwise.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    ink = float(np.count_nonzero(gray < BLANK_INK_GRAY_THRESHOLD))
    return ink / gray.size < BLANK_INK_RATIO


def estimate_rotation_angle(image: np.ndarray) -> float:
    """Estimate the dominant rotation of an image, in degrees.

    Detects long straight lines (text baselines, ruling lines, borders) via a
    probabilistic Hough transform on the Canny edges, folds each line's angle
    onto the nearest axis (0/90 degrees) and returns the length-weighted
    average deviation in ``[-45, 45)`` degrees. A value near zero means the
    content is aligned with the page axes; positive values indicate a clockwise
    rotation. Only detection is performed -- the image is never rotated.

    Args:
        image: An RGB (BGR) image as returned by OpenCV.

    Returns:
        The estimated rotation angle in degrees, or ``0.0`` when no usable
        line structure is present (e.g. a blank page).
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=math.pi / 180,
        threshold=100,
        minLineLength=100,
        maxLineGap=10,
    )
    if lines is None:
        return 0.0

    deviations: list[float] = []
    weights: list[float] = []
    for (x1, y1, x2, y2), in lines:
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
        deviation = angle % 90.0
        if deviation > 45.0:
            deviation -= 90.0
        deviations.append(deviation)
        weights.append(math.hypot(x2 - x1, y2 - y1))

    if not weights:
        return 0.0
    return float(np.average(deviations, weights=weights))


def render_pdf_first_page(path: str | object, dpi: int | None = None) -> np.ndarray | None:
    """Render the first page of a PDF to a BGR image.

    Rasterizes page one at the configured DPI so the blur and rotation analysis
    can run on PDF documents too. This is measurement only: the render is never
    stored or forwarded to any downstream stage.

    Args:
        path: Path of the PDF file (anything accepted by ``pymupdf.open``).
        dpi: Resolution of the render. Defaults to
            :data:`PDF_RENDER_DPI` via the module configuration.

    Returns:
        A BGR ``numpy`` image of the first page, or ``None`` when the PDF
        cannot be rendered (encrypted, empty or unrenderable page).
    """
    import pymupdf

    scale = _DOTS_PER_POINT if dpi is None else dpi / 72.0
    try:
        with pymupdf.open(str(path)) as document:
            if document.needs_pass or document.page_count == 0:
                return None
            page = document.load_page(0)
            pixmap = page.get_pixmap(
                matrix=pymupdf.Matrix(scale, scale),
                alpha=False,
            )
            samples = np.frombuffer(pixmap.samples, dtype=np.uint8)
            return samples.reshape(pixmap.height, pixmap.width, pixmap.n)
    except Exception:  # pragma: no cover - defensive, any render failure is reported
        logger.exception("Could not render first page of PDF %r", str(path))
        return None

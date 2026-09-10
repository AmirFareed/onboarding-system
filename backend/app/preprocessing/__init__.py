"""Preprocessing package: document splitting.

Image enhancement intentionally lives in :mod:`app.document_processing.utils`
(``deskew_image``, CLAHE, denoise) and is not duplicated here.
"""

from app.preprocessing.splitter import DocumentSplitter

__all__ = ["DocumentSplitter"]
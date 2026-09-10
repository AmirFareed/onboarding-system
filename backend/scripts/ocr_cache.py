"""Persistent OCR-text cache for real files in Confidential Data/.

OCR is the dominant cost of any real-file inspection or extractor-validation
task on this CPU-only machine (minutes per page) -- running an extractor's
regex against already-extracted text is instant by comparison. Every ad-hoc
inspection script up to now threw the OCR'd text away afterward, so the same
real file got OCR'd again from scratch for every new question asked about it.
This module makes that a one-time cost per (source file, document type, copy)
by caching each split document's OCR'd text on disk.

Cache location: ``Confidential Data/.ocr_cache/`` -- already covered by the
repo's existing ``/Confidential Data/`` gitignore rule (verified with
``git check-ignore``), so no separate ignore rule was needed. This directory
contains real extracted PII (names, CNICs, IBANs) and gets the exact same
treatment as the rest of Confidential Data/: local only, never committed,
never pasted verbatim into chat/logs/commits beyond what a task genuinely
needs.

Usage as a library::

    from scripts.ocr_cache import get_ocr_text
    from app.database.models.enums import DocumentType

    text = get_ocr_text("TMA Khal Dir Lower .pdf", DocumentType.AUTHORITY_LETTER, copy_number=1)

Usage from the command line, to pre-warm the cache for one real file (splits
and OCRs it once, caching every document type found, not just one)::

    .venv/Scripts/python.exe scripts/ocr_cache.py "TMA Khal Dir Lower .pdf"
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import pymupdf

from app.database.models.enums import DocumentType
from app.document_processing.processors import PaddleOCREngine
from app.preprocessing.splitter import DocumentSplitter

CONFIDENTIAL_DATA = BACKEND.parent / "Confidential Data"
CACHE_DIR = CONFIDENTIAL_DATA / ".ocr_cache"

#: Minimum native text before a page is trusted as real content; below this,
#: OCR runs. Mirrors preprocessing.splitter._MIN_NATIVE_TEXT_CHARS -- these
#: real files are 100% scanned, so this is expected to fire on every page.
_MIN_NATIVE_TEXT_CHARS = 40


def _slug(filename: str) -> str:
    """Filesystem-safe slug for a source filename."""
    stem = Path(filename).stem
    return re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_")


def _resolve(source_file: Path | str) -> Path:
    """Resolve `source_file` against Confidential Data/ if not already absolute."""
    path = Path(source_file)
    return path if path.is_absolute() else CONFIDENTIAL_DATA / path


def _ocr_page_text(page: pymupdf.Page, engine: PaddleOCREngine) -> str:
    """Return a page's text, falling back to OCR when native text is sparse."""
    text = page.get_text()
    if len(text.strip()) >= _MIN_NATIVE_TEXT_CHARS:
        return text
    import cv2
    import numpy as np

    pix = page.get_pixmap(dpi=150)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
    if pix.n == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
    return engine.extract(img).text


def _split_and_cache_all(
    source_file: Path, engine: PaddleOCREngine
) -> dict[tuple[DocumentType, int], Path]:
    """Split `source_file` once, OCR every resulting document, cache each.

    A single OCR pass populates the cache for every document type present in
    the file, not just the one a particular caller asked for -- so asking for
    one type from a file warms the cache for every other type in it too.

    Returns:
        Mapping of (document_type, copy_number) -> cache file path.
    """
    content = source_file.read_bytes()
    split_docs = DocumentSplitter.split_bulk_pdf(content, ocr_engine=engine).documents

    slug = _slug(source_file.name)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    seen: dict[DocumentType, int] = {}
    written: dict[tuple[DocumentType, int], Path] = {}
    for doc_type, pdf_bytes in split_docs:
        copy_number = seen.get(doc_type, 0) + 1
        seen[doc_type] = copy_number

        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        try:
            page_texts = [_ocr_page_text(page, engine) for page in doc]
        finally:
            doc.close()
        full_text = "\n--- page break ---\n".join(page_texts)

        cache_path = CACHE_DIR / f"{slug}__{doc_type.value}_copy{copy_number}.txt"
        cache_path.write_text(full_text, encoding="utf-8")
        written[(doc_type, copy_number)] = cache_path

    return written


def get_ocr_text(
    source_file: Path | str,
    document_type: DocumentType,
    copy_number: int = 1,
) -> str:
    """Return the OCR'd text of one split document, using the on-disk cache.

    On a cache hit, returns immediately with no OCR. On a miss, splits and
    OCRs the *entire* source file once (caching every resulting document),
    then returns the requested entry.

    Args:
        source_file: Filename within Confidential Data/, or an absolute path.
        document_type: The splitter's classification for the document wanted.
        copy_number: Which copy, in split order, when a type appears more
            than once in the file (1-indexed).

    Returns:
        The document's OCR'd (or native-extracted) text.

    Raises:
        FileNotFoundError: When the source file, or the requested
            (document_type, copy_number) after splitting, doesn't exist.
    """
    resolved = _resolve(source_file)
    if not resolved.exists():
        raise FileNotFoundError(f"No such file: {resolved}")

    slug = _slug(resolved.name)
    cache_path = CACHE_DIR / f"{slug}__{document_type.value}_copy{copy_number}.txt"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    engine = PaddleOCREngine()
    written = _split_and_cache_all(resolved, engine)
    key = (document_type, copy_number)
    if key not in written:
        available = sorted(f"{t.value} x{c}" for t, c in written)
        raise FileNotFoundError(
            f"{resolved.name} has no {document_type.value} copy {copy_number} "
            f"after splitting; available: {available}"
        )
    return written[key].read_text(encoding="utf-8")


def cached_types(source_file: Path | str) -> dict[str, int]:
    """Return ``{document_type_value: copies_cached}`` for `source_file`."""
    resolved = _resolve(source_file)
    slug = _slug(resolved.name)
    counts: dict[str, int] = {}
    if not CACHE_DIR.exists():
        return counts
    pattern = re.compile(rf"^{re.escape(slug)}__(.+)_copy(\d+)$")
    for path in CACHE_DIR.glob(f"{slug}__*.txt"):
        match = pattern.match(path.stem)
        if match:
            doc_type, copy = match.group(1), int(match.group(2))
            counts[doc_type] = max(counts.get(doc_type, 0), copy)
    return counts


def main() -> None:
    """CLI: split + OCR one real file, caching every document type found."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source_file", help="Filename within Confidential Data/, or an absolute path"
    )
    args = parser.parse_args()

    resolved = _resolve(args.source_file)
    already = cached_types(resolved)
    if already:
        print(f"Already cached for {resolved.name}: {already}")
        return

    engine = PaddleOCREngine()
    written = _split_and_cache_all(resolved, engine)
    print(f"Cached {len(written)} document(s) from {resolved.name}:")
    for (doc_type, copy_number), cache_path in sorted(
        written.items(), key=lambda kv: (kv[0][0].value, kv[0][1])
    ):
        print(f"  {doc_type.value} copy {copy_number} -> {cache_path.name}")


if __name__ == "__main__":
    main()

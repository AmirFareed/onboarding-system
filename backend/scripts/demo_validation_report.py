"""
Generate a temporary OCR extraction and validation report.
Reads the first 3 pages of the TMA Khal PDF and outputs the raw OCR text.
"""
import sys
import os
import pymupdf as fitz

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from app.preprocessing.splitter import DocumentSplitter

PDF_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "demo", "TMA Khal Dir Lower .pdf"
)

print("# Temporary Validation & OCR Report")
print(f"**Document**: `{os.path.basename(PDF_PATH)}`\n")

doc = fitz.open(PDF_PATH)
num_pages = min(3, len(doc)) # Only check first 3 pages for speed

for page_num in range(num_pages):
    page = doc.load_page(page_num)
    
    print(f"## Page {page_num + 1}")
    
    # Use the new PyMuPDF-based text extractor from Zarghuna's rewrite
    from app.preprocessing.splitter import _extract_lines
    lines = _extract_lines(page)
    text = " ".join(text for _, text in lines)
    
    print("### Extracted Text (First 1000 chars)")
    print("```text")
    print(text[:1000] if text else "[No text extracted]")
    print("```\n")
    
    detected_type, strong_evidence, _matched_phrase = DocumentSplitter._classify_page(page)
    print(f"**Classification Result**: `{detected_type.name if detected_type else 'OTHER_SUPPORTING_DOCUMENT'}` (Strong Evidence: {strong_evidence})\n")
    print("---")

doc.close()

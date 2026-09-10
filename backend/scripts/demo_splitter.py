"""
Quick demo script: Run the DocumentSplitter on the real DGAM onboarding PDF.
No database or server needed - just pure CV and PDF splitting.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from app.preprocessing.splitter import DocumentSplitter

PDF_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "demo", "TMA Khal Dir Lower .pdf"
)

print("=" * 60)
print("DOCUMENT SPLITTER - LIVE TEST")
print("=" * 60)
print(f"Input: {PDF_PATH}")
print()

with open(PDF_PATH, "rb") as f:
    content = f.read()

result = DocumentSplitter.split_bulk_pdf(content)

print(f"✅ Total documents detected: {len(result.documents)}")
print()
print("Breakdown:")
print("-" * 40)
for i, (doc_type, pdf_bytes) in enumerate(result.documents, 1):
    size_kb = len(pdf_bytes) / 1024
    print(f"  {i}. {doc_type.value:<45} ({size_kb:.1f} KB)")

if result.warnings:
    print()
    print(f"⚠️  {len(result.warnings)} possible cross-document absorption warning(s):")
    for warning in result.warnings:
        print(
            f"  - document #{warning.document_index + 1} "
            f"({warning.document_type.value}): page {warning.page_number + 1} "
            f"weakly matches {warning.weakly_matched_type.value}"
        )

print()
print("=" * 60)
print("Done!")

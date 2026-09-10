"""Unit tests for the DocumentSplitter module.

Tests that bulk PDFs are classified into logical document chunks. These tests
are fully self-contained and require no database.
"""

import io
from pathlib import Path

import pymupdf
import pytest

from app.database.models.enums import DocumentType
from app.preprocessing.splitter import DocumentSplitter
from app.upload.exceptions import FileTooLargeException, InvalidFileTypeException

#: Real cached OCR text, mirroring the guard/helper already established in
#: tests/test_document_analysis_engine.py -- gitignored, doesn't exist in CI
#: or on a fresh checkout.
_CONFIDENTIAL_DATA = Path(__file__).resolve().parents[3] / "Confidential Data"
_OCR_CACHE_DIR = _CONFIDENTIAL_DATA / ".ocr_cache"

requires_real_cache = pytest.mark.skipif(
    not _OCR_CACHE_DIR.is_dir(),
    reason="Confidential Data/.ocr_cache not present (gitignored, real-sample only)",
)


def _real_cache_text(filename: str) -> str:
    return (_OCR_CACHE_DIR / filename).read_text(encoding="utf-8")


def _make_pdf_with_text(pages: list[str]) -> bytes:
    """Create a minimal in-memory PDF with one text page per item."""
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((50, 50), text, fontsize=14)
    buffer = io.BytesIO(doc.tobytes())
    doc.close()
    return buffer.getvalue()


def _split(page_texts: list[str]) -> list[tuple[DocumentType, bytes]]:
    return DocumentSplitter.split_bulk_pdf(_make_pdf_with_text(page_texts)).documents


def _split_full(page_texts: list[str]):
    """Return the full ``SplitResult`` (documents + absorption warnings)."""
    return DocumentSplitter.split_bulk_pdf(_make_pdf_with_text(page_texts))


def _doc_types(page_texts: list[str]) -> list[DocumentType]:
    return [doc_type for doc_type, _ in _split(page_texts)]


# --- Classification ---------------------------------------------------------


def test_split_single_known_document():
    """A PDF with a clear header should return one categorized document."""
    result = _split(["TRIPARTITE AGREEMENT\nThis is an agreement."])
    assert len(result) == 1
    assert result[0][0] == DocumentType.TRIPARTITE_AGREEMENT


def test_split_multiple_known_documents():
    """A PDF with multiple distinct headers should yield multiple documents."""
    types = _doc_types([
        "TRIPARTITE AGREEMENT\nContent here.",
        "AUTHORITY LETTER\nContent here.",
        "ACCOUNT MAINTENANCE CERTIFICATE\nContent here.",
    ])
    assert types == [
        DocumentType.TRIPARTITE_AGREEMENT,
        DocumentType.AUTHORITY_LETTER,
        DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    ]


def test_split_unclassified_pages_become_other():
    """Pages with no matching keywords should be grouped as OTHER_SUPPORTING_DOCUMENT."""
    result = _split(["Random unrecognized document content."])
    assert len(result) == 1
    assert result[0][0] == DocumentType.OTHER_SUPPORTING_DOCUMENT


def test_split_repeated_same_type_copies():
    """Repeated copies of the same type must each become their own document."""
    types = _doc_types([
        "TRIPARTITE AGREEMENT\nCopy one body.",
        "TRIPARTITE AGREEMENT\nCopy two body.",
        "TRIPARTITE AGREEMENT\nCopy three body.",
    ])
    assert [t for t in types if t == DocumentType.TRIPARTITE_AGREEMENT] == [
        DocumentType.TRIPARTITE_AGREEMENT,
        DocumentType.TRIPARTITE_AGREEMENT,
        DocumentType.TRIPARTITE_AGREEMENT,
    ]


def test_split_mixed_repeated_copies_and_pairs():
    """Multiple copies of 1-Link, Schedule of Charges (now Bilateral -- see
    2026-08-25 department decision) and a CNIC pair."""
    types = _doc_types([
        "1LINK APPLICATION FORM\nFirst copy.",
        "1LINK APPLICATION FORM\nSecond copy.",
        "1LINK APPLICATION FORM\nThird copy.",
        "SCHEDULE OF CHARGES\nSix copies include this one.",
        "SCHEDULE OF CHARGES\nAnother.",
        "NATIONAL IDENTITY CARD\nIdentity Number: 42101-0000000-0\nFather Name: Ali",
        "ISLAMIC REPUBLIC OF PAKISTAN\nDate of Issue: 01-01-2010\nIssuing Authority: NADRA",
    ])
    assert types.count(DocumentType.ONE_LINK_LETTER) == 3
    assert types.count(DocumentType.BILATERAL_AGREEMENT) == 2
    assert types.count(DocumentType.CNIC_FRONT) == 1
    assert types.count(DocumentType.CNIC_BACK) == 1
    assert DocumentType.CNIC_BACK in types


def test_split_cnic_back_is_not_front():
    """A back face with issuing-authority fields must be CNIC_BACK, not FRONT."""
    types = _doc_types([
        "NATIONAL IDENTITY CARD\nIdentity Number: 42101-0000000-0\nFather Name: Ali",
        "NATIONAL IDENTITY CARD\nDate of Issue: 01-01-2010\nIssuing Authority: NADRA",
    ])
    assert types == [DocumentType.CNIC_FRONT, DocumentType.CNIC_BACK]


def test_split_continuation_page_does_not_split():
    """Body keywords on a continuation page must not start a new document."""
    types = _doc_types([
        "TRIPARTITE AGREEMENT\nPage 1.",
        "as per the 1LINK tripartite agreement and schedule of charges on page 2.",
        "continued agreement text on page 3.",
    ])
    assert types == [DocumentType.TRIPARTITE_AGREEMENT]


def test_split_consecutive_same_type_grouped():
    """A title page plus unclassified continuation pages stay one document."""
    result = _split([
        "SCHEDULE OF CHARGES\nPage 1.",
        "Continuation of the schedule on page 2.",
    ])
    assert len(result) == 1
    assert result[0][0] == DocumentType.BILATERAL_AGREEMENT


def test_split_checklist_cover_page_is_not_misclassified():
    """A checklist page listing required documents by name must not be
    mistaken for one of the documents it lists.

    Regression test for a real bug found 2026-08-16 on a real file in
    Confidential Data/: a checklist/manifest cover page's first table row
    ("Authority Letter of officer - Signed") fell inside the header zone and
    strong-matched AUTHORITY_LETTER, producing a spurious second copy of a
    document that only existed once for real -- confirmed by comparing the
    real page's actual OCR text (a checklist titled "CHECKLIST FOR
    ON-BOARDING...") against the real single genuine Authority Letter page
    later in the same file.
    """
    types = _doc_types([
        "CHECKLIST\nAuthority Letter of officer - Signed\n"
        "Account Maintenance Certificate from Bank",
        "AUTHORITY LETTER\nIt is hereby authorized that the officer may act "
        "on our behalf.",
    ])
    assert types == [
        DocumentType.OTHER_SUPPORTING_DOCUMENT,
        DocumentType.AUTHORITY_LETTER,
    ]


def test_split_master_checklist_cover_page_is_not_misclassified():
    """A "MASTER CHECKLIST" cover page must also be excluded, not just plain
    "CHECKLIST".

    Regression test for a second real file found 2026-08-16 with the exact
    same underlying bug but a different checklist title: a prefix
    (startswith) check on "CHECKLIST" caught a real file titled plain
    "CHECKLIST" but silently missed this real file's "MASTER CHECKLIST",
    whose own "Authority Letter" table row (this time with no trailing
    text) again strong-matched AUTHORITY_LETTER.
    """
    types = _doc_types([
        "MASTER CHECKLIST\nAuthority Letter\nAccount Maintenance Certificate",
        "AUTHORITY LETTER\nIt is hereby authorized that the officer may act "
        "on our behalf.",
    ])
    assert types == [
        DocumentType.OTHER_SUPPORTING_DOCUMENT,
        DocumentType.AUTHORITY_LETTER,
    ]


def test_split_genuine_application_form_title_is_one_link_letter():
    """The genuine 1-Link Application Form's own real title must start a new
    document, not be silently absorbed as an untyped continuation.

    Regression test for a real bug found 2026-08-18 on TMA Lal Dir Upper.pdf
    (Confidential Data/): docs/Master_Rules_Combined.md Section 4's real
    Application Form starts its own page with "Application Form (In-Direct
    Customer)" -- it never carries a "1LINK"/"ONE-LINK"/"ONELINK" brand
    prefix on the page itself, so none of the existing ONE_LINK_LETTER
    phrases (all brand-prefixed) ever matched it; the page was silently
    absorbed as a continuation of whichever unrelated document preceded it
    instead. The same real title, previously unidentified, was also found
    hiding in 3 other already-cached real samples from 2 other files.
    """
    types = _doc_types([
        "AUTHORITY LETTER\nUnrelated preceding document body.",
        "Application Form (In-Direct Customer)\nKnow Your Customer, Form A.",
    ])
    assert types == [DocumentType.AUTHORITY_LETTER, DocumentType.ONE_LINK_LETTER]


# --- Formal Request Letter structural fallback ------------------------------
#
# Regression tests for a real absorption bug found 2026-08-23: real Formal
# Request Letter subject lines vary in exact wording per department, so no
# phrase list can generalize the way _STRONG_TITLE_PHRASES does for other
# types. What's actually common across every real occurrence checked is
# structural: an "OFFICE OF THE..." letterhead line followed a few lines
# later by a "SUBJECT:" line, both inside the header zone. Confirmed against
# 6 independent real source files in Confidential Data/ -- one test below per
# file, matching that file's real gap/shape, not just the 3 originally
# scoped. Two of the six (Samarbagh, Lal Qilla) share the same real
# department template almost verbatim; kept as separate tests since they are
# two independent real files, not a synthetic duplicate.


def test_split_formal_request_letter_lal_dir_upper_shape():
    """TMA Lal Dir Upper's real shape: no salutation line, straight from the
    subject line into the body. Already caught by the existing
    "SUBJECT: REQUEST FOR DIGITAL ACCOUNT" phrase (test_document_splitter.py
    has no prior regression test for that phrase at all) -- this test also
    confirms the new structural fallback doesn't change that outcome.
    """
    types = _doc_types([
        "OFFICE OF THE TEHSIL MUNICIPAL OFFICER\n"
        "TEHSIL MUNICIPAL ADMINISTRATION LAL DIR UPPER\n"
        "No. 1414-16 /TMA/Dir\n"
        "Dated Dir(U) 13/07/2026\n"
        "TMA Dir\n"
        "PHONE #:0944-880119\n"
        "To\n"
        "The Managing Director\n"
        "KPIT Board, Hayatabad, Peshawar\n"
        "SUBJECT: REQUEST FOR DIGITAL ACCOUNT AND FOR ONLINE PAYMENTS.\n"
        "As per Regional Municipal Officer letter, it is requested to "
        "forward the case to 1 link for digital accounts.",
    ])
    assert types == [DocumentType.FORMAL_REQUEST_LETTER]


def test_split_formal_request_letter_samarbagh_shape():
    """TMA Samarbagh's real shape, previously silently absorbed as a
    continuation of a preceding Business Requirement Document: "Subject:" on
    its own line, subject text wraps onto the next line, then a "Dear Sir,"
    salutation before the body.
    """
    types = _doc_types([
        "BUSINESS REQUIREMENT DOCUMENT\nTMA Samarbagh intends to onboard KPITB.",
        "OFFICE OF THE TEHSIL MUNICIPAL OFFICER\n"
        "TEHSIL MUNICIPAL ADMINISTRATION\n"
        "SAMARBAGH DIR LOWER\n"
        "No: TMA SB/ Dated 7/07/2026\n"
        "To,\n"
        "The Director,\n"
        "KPITB, Peshawar.\n"
        "SUBJECT:\n"
        "APPLICATION FOR ONBOARDING ON 1LINK 1BILL SERVICES\n"
        "Dear Sir,\n"
        "With reference to the subject cited above, TMA Samarbagh intends "
        "to digitize its revenue collection.",
    ])
    assert types == [
        DocumentType.BUSINESS_REQUIREMENT_DOCUMENT,
        DocumentType.FORMAL_REQUEST_LETTER,
    ]


def test_split_formal_request_letter_gdc_alpurai_shangla_shape():
    """GDC Alpurai Shangla's real shape, previously silently absorbed into
    an OTHER_SUPPORTING_DOCUMENT group: subject text on the same line as
    "Subject:" with a dash separator, "Respected Sir," salutation.
    """
    types = _doc_types([
        "Random unrecognized cover content.",
        "OFFICE OF THE PRINCIPAL GOVT: DEGREE COLLEGE ALPURAI SHANGLA\n"
        "Phone# 0996850470, E-mail: gdcalpurai@gmail.com\n"
        "No: 849 /Alpurai-I\n"
        "Dated: 18-05-2026\n"
        "To\n"
        "The Managing Director,\n"
        "Khyber Pakhtunkhwa Information Technology Board\n"
        "SUBJECT: - ON-BOARDING AS A SUB-SELLER WITH KPITB\n"
        "Respected Sir,\n"
        "I am directed to refer to the subject cited above.",
    ])
    assert types == [
        DocumentType.OTHER_SUPPORTING_DOCUMENT,
        DocumentType.FORMAL_REQUEST_LETTER,
    ]


def test_split_formal_request_letter_khal_dir_lower_shape():
    """TMA Khal Dir Lower's real shape, previously silently absorbed as a
    continuation of a preceding Business Requirement Document -- found
    2026-08-23 during full-corpus validation, not part of the originally
    scoped 3 samples.
    """
    types = _doc_types([
        "BUSINESS REQUIREMENT DOCUMENT\nTMA Khall's revenue collection method.",
        "OFFICE OF THE\n"
        "TEHSIL MUNICIPAL OFFICER\n"
        "TEHSIL MUNICIPAL ADMINISTRATION\n"
        "KHAL DISTRICT DIR (LOWER)\n"
        "No. 420 /TMAK\n"
        "To\n"
        "The Managing Director,\n"
        "Khyber Pakhtunkhwa Information Technology Board (KPITB) Peshawar.\n"
        "SUBJECT:\n"
        "ON BOARDING AS A SUB-BILLER WITH KPITB.\n"
        "I am directed to refer to the subject cited above.",
    ])
    assert types == [
        DocumentType.BUSINESS_REQUIREMENT_DOCUMENT,
        DocumentType.FORMAL_REQUEST_LETTER,
    ]


def test_split_formal_request_letter_lal_qilla_shape():
    """TMA Lal Qilla Dir Lower's real shape -- same department template as
    Samarbagh, found on an independent real file 2026-08-23.
    """
    types = _doc_types([
        "BUSINESS REQUIREMENT DOCUMENT\nTMA Lal Qila intends to onboard KPITB.",
        "OFFICE OF THE TEHSIL MUNICIPAL OFFICE\n"
        "TEHSIL MUNICIPAL ADMINISTRATION\n"
        "LAL QILA DIR LOWER\n"
        "No 299-3o)/TMA/Lal Qila/\n"
        "To,\n"
        "The Director,\n"
        "KPITB, Peshawar.\n"
        "SUBJECT:\n"
        "APPLICATION FOR ONBOARDING ON 1LINK 1BILL SERVICES\n"
        "Dear Sir,\n"
        "With reference to the subject cited above, TMA Lal Qila intends "
        "to digitize its revenue collection.",
    ])
    assert types == [
        DocumentType.BUSINESS_REQUIREMENT_DOCUMENT,
        DocumentType.FORMAL_REQUEST_LETTER,
    ]


def test_split_formal_request_letter_thall_hangu_shape():
    """TMA Thall Hangu's real shape, previously silently absorbed into a
    ONE_LINK_LETTER group -- found 2026-08-23 during full-corpus validation.
    """
    types = _doc_types([
        "1LINK APPLICATION FORM\nFirst copy for Thall Hangu.",
        "OFFICE OF THE\n"
        "TEHSIL MUNICIPAL ADMINISTRATION\n"
        "HANGU\n"
        "No. 432 /TMA(H)\n"
        "The Managing Director,\n"
        "Khyber Pakhtunkhwa Information Technology Board (KPITB) Peshawar.\n"
        "SUBJECT:\n"
        "ON BOARDING AS A SUB-BILLER WITH KPITB.\n"
        "I am directed to refer to the subject cited above.",
    ])
    assert types == [
        DocumentType.ONE_LINK_LETTER,
        DocumentType.FORMAL_REQUEST_LETTER,
    ]


def test_split_formal_request_letter_stray_leading_punctuation_on_subject_line():
    """A real Formal Request Letter whose OCR misread the "Subject:" line as
    ".Subject:" (a stray leading period) must still hit the structural
    fallback, not fall through to OTHER_SUPPORTING_DOCUMENT/UNKNOWN.

    Regression test for a real bug found 2026-08-23/24 during a real-sample
    audit of Individual PDFs/on boarding sub biller.pdf (a genuine GPGC ->
    KPITB onboarding request letter, same real shape as the Khal Dir Lower/
    Thall Hangu samples above): PaddleOCR read the subject line's leading
    dot/colon as a literal "." before "Subject", which a strict
    ``text.startswith("SUBJECT:")`` has zero tolerance for. Fixed by
    stripping leading punctuation before the prefix check.
    """
    types = _doc_types([
        "OFFICE OF THE PRINCIPAL\n"
        "GOVT: POSTGRADUATE COLLEGE NO.1\n"
        "ABBOTTABAD\n"
        "No22.50\n"
        "To\n"
        "The Managing Director,\n"
        "Khyber Pakhtunkhwa Information\n"
        "Technology Board (KPITB), Peshawar.\n"
        ".Subject:\n"
        "ON BOARDING AS A SUB-BILLER WITH KPITB.\n"
        "Respected Sir,\n"
        "Refer to the subject cited above and to inform you that Government "
        "Postgraduate College No.1, Abbottabad is a prestigious public "
        "sector educational institution.",
    ])
    assert types == [DocumentType.FORMAL_REQUEST_LETTER]


def test_split_master_check_list_two_word_variant_is_not_misclassified():
    """A "MASTER CHECK LIST" (two words) cover page must be excluded the
    same way plain "CHECKLIST"/"MASTER CHECKLIST" already are.

    Regression test for a real bug found 2026-08-23 on
    TMA_Thall_Hangu__AUTHORITY_LETTER_copy1.txt (Confidential Data/) while
    validating the Formal Request Letter structural fallback above: this
    real checklist cover page spells it "MASTER CHECK LIST" / "CHECK LIST
    FOR ON BOARDING..." (two words throughout, no contiguous "CHECKLIST"
    substring anywhere), so the pre-existing single-string guard silently
    missed it -- its own "Authority Letter" checklist-table row then
    strong-matched AUTHORITY_LETTER (the same mislabeling already flagged in
    CONTEXT.md 2026-08-20), and -- newly, before this fix -- its letterhead
    plus its own "Subject:" line would also have satisfied the new
    structural fallback above. Widening the guard to also catch the
    two-word spelling fixes both.
    """
    types = _doc_types([
        "OFFICE OF THE\nTEHSIL MUNICPAL ADMINSTRATION THALL\n"
        "MASTER CHECK LIST\n"
        "SUBJECT:\n"
        "CHECK LIST FOR ON BOARDING NON-ACCOUNT 1 P2G\n"
        "Authority Letter\nYes\nA\n"
        "Account maintenance certificate\nYes\nB",
        "AUTHORITY LETTER\nIt is hereby authorized that the officer may act "
        "on our behalf.",
    ])
    assert types == [
        DocumentType.OTHER_SUPPORTING_DOCUMENT,
        DocumentType.AUTHORITY_LETTER,
    ]


def test_split_subject_to_boilerplate_does_not_false_match_formal_request():
    """Mid-sentence legal boilerplate starting "Subject to..." (no colon)
    must never be mistaken for a "SUBJECT:" header line, even on a page that
    also happens to carry an "OFFICE OF THE..." letterhead -- otherwise the
    two structural signals alone would misclassify it as a Formal Request
    Letter, which this page is not.

    Confirmed against the real corpus 2026-08-23: TMA_Thall_Agreement and
    GDA_Abbotabad both carry a real "Subject to arbitration, the courts at
    Peshawar shall have exclusive jurisdiction..." clause; requiring the
    colon in "SUBJECT:" is what keeps these from false-matching. No other
    strong phrase is present on this synthetic page, so a false match here
    would surface directly as FORMAL_REQUEST_LETTER instead of falling
    through to OTHER_SUPPORTING_DOCUMENT.
    """
    types = _doc_types([
        "OFFICE OF THE TEHSIL MUNICIPAL OFFICER\n"
        "TEHSIL MUNICIPAL ADMINISTRATION THALL\n"
        "This agreement is governed by the laws of Pakistan.\n"
        "Subject to arbitration, the courts at Peshawar shall have "
        "exclusive jurisdiction.",
    ])
    assert types == [DocumentType.OTHER_SUPPORTING_DOCUMENT]


def test_split_application_form_three_pages_group_into_one_document():
    """Corrects a wrong assumption from an earlier pass of this fix: the
    real Application Form's page count is NOT fixed at 3 -- checked against
    4 real cached samples 2026-08-18, 3 files show 3 pages, a 4th
    (GDA Abbotabad) shows 4. The form's own title repeats on every one of
    its pages regardless of count, so each page independently strong-
    matching used to produce N separate ONE_LINK_LETTER copies instead of
    one logical document -- silently over-fragmenting the real form and, in
    at least one real file, pushing the type past
    MAX_COPIES_BY_DOCUMENT_TYPE's cap of 3 and hard-failing the entire bulk
    upload (found the same day, TMA Khal Dir Lower.pdf: 3 form pages + 1
    pre-existing genuine ONE_LINK_LETTER sample = 4, over the cap).

    Fixed by _CONTINUATION_TITLE_PHRASES: a repeat of this exact phrase on
    the immediately following strong-matched page extends the current
    document instead of starting a new one. This is the 3-page case.
    """
    types = _doc_types([
        "Application Form (In-Direct Customer)\nForm A, company details.",
        "Application Form (In-Direct Customer)\nDirectors/partners table.",
        "Application Form (In-Direct Customer)\nForm B, business information.",
    ])
    assert types == [DocumentType.ONE_LINK_LETTER]


def test_split_application_form_four_pages_group_into_one_document():
    """Same fix, the 4-page case -- confirmed page-count-agnostic, not
    hardcoded to 3. Matches the real GDA Abbotabad.pdf sample's own shape
    (an extra page beyond the other 3 samples' 3-page structure).
    """
    types = _doc_types([
        "Application Form (In-Direct Customer)\nForm A, company details.",
        "Application Form (In-Direct Customer)\nDirectors/partners table.",
        "Application Form (In-Direct Customer)\nLicense status table.",
        "Application Form (In-Direct Customer)\nForm B, business information.",
    ])
    assert types == [DocumentType.ONE_LINK_LETTER]


def test_split_application_form_ends_before_a_genuinely_different_document():
    """The grouping above must stop cleanly once the repeating phrase
    stops, so a real, different document immediately following the form
    still starts its own document rather than being absorbed into it.
    """
    types = _doc_types([
        "Application Form (In-Direct Customer)\nForm A, company details.",
        "Application Form (In-Direct Customer)\nForm B, business information.",
        "AUTHORITY LETTER\nA separate, unrelated document right after.",
    ])
    assert types == [DocumentType.ONE_LINK_LETTER, DocumentType.AUTHORITY_LETTER]


def test_split_application_form_matches_despite_ocr_misread_of_last_word():
    """Real GDC Alpurai Shangla.pdf OCR's this title as "...Customex)" (a
    one-character misread of "Customer)") -- confirmed 2026-08-22 by
    reading the real cached OCR text directly. The exact-string match that
    fixed the other 3 real samples of this same title did not catch this
    one; the phrase was narrowed to a prefix (drops the last word) so any
    misread of it doesn't matter.
    """
    types = _doc_types([
        "AUTHORITY LETTER\nUnrelated preceding document.",
        "Application Form (In-Direct Customex)\nForm A, company details.",
    ])
    assert types == [DocumentType.AUTHORITY_LETTER, DocumentType.ONE_LINK_LETTER]


def test_split_application_form_ocr_misread_still_groups_multipage():
    """The prefix match must still support the multi-page continuation
    grouping (_CONTINUATION_TITLE_PHRASES) even when the repeated title is
    OCR-misread the same way on every page, matching GDC Alpurai Shangla's
    real 2-of-3 pages carrying the identical "...Customex)" misread.
    """
    types = _doc_types([
        "Application Form (In-Direct Customex)\nForm A, company details.",
        "Application Form (In-Direct Customex)\nDirectors/partners table.",
        "Application Form (In-Direct Customer)\nForm B, business information.",
    ])
    assert types == [DocumentType.ONE_LINK_LETTER]


def _stamp_paper_boilerplate(lines: int = 30) -> str:
    """Simulate the fixed verification/QR boilerplate block real e-stamp
    paper pages carry before their actual title -- see
    _FULL_PAGE_STRONG_PHRASES's docstring. 30 lines reliably pushes real
    rendered text past a real PDF page's header-zone cutoff (confirmed
    empirically: ~451pt vs. the ~278pt cutoff on an A4-sized page).
    """
    return "\n".join(f"Stamp paper boilerplate line {i}" for i in range(lines))


def test_split_participation_memorandum_starts_own_group_past_boilerplate():
    """A real Participation Memorandum's title sits well below the header
    zone, after a fixed stamp-paper boilerplate block -- it must still
    start its own new document (not be absorbed into a preceding,
    unrelated open group) and must be typed TRIPARTITE_AGREEMENT, not
    OTHER_SUPPORTING_DOCUMENT or misclassified via the bare "1LINK"
    mentions in its own body text.

    Regression test for a real bug found 2026-08-18 across 3 real samples
    (GDA Abbotabad, TMA Khal Dir Lower): this title was previously invisible
    to the splitter entirely (absent from _STRONG_TITLE_PHRASES) and, once
    a group happened to be open, silently absorbed into whatever document
    preceded it -- or, if no group was open, mistyped via the bare "1LINK"
    weak substring match rather than genuinely recognized.

    **Corrected 2026-08-25**: originally mapped to ONE_LINK_LETTER per a
    2026-08-19 department decision (the still-open "1-Link Letter
    checklist-meaning mismatch" question in CONTEXT.md). Department
    correction: a "PARTICIPATION MEMORANDUM FOR BILLER/SUB-BILLER/BILL
    AGGREGATOR MEMBERS" is the Tripartite Agreement -- identified by its
    three signing parties (1LINK, the department, KPITB), not by a literal
    "TRIPARTITE AGREEMENT" title. Confirmed against every real sample in
    Confidential Data/.ocr_cache/ carrying this phrase; see the
    _FULL_PAGE_STRONG_PHRASES comment for the full real-file list.
    """
    body = (
        _stamp_paper_boilerplate()
        + "\nPARTICIPATION MEMORANDUM FOR BILLER/SUB-BILLERS/BILL AGGREGATOR MEMBERS\n"
        + "This Participation Memorandum is supplemental to the Agreement "
        + "executed between 1LINK (Private) Limited and the Bill Aggregator."
    )
    types = _doc_types([
        "AUTHORITY LETTER\nAn unrelated, genuinely different document first.",
        body,
    ])
    assert types == [DocumentType.AUTHORITY_LETTER, DocumentType.TRIPARTITE_AGREEMENT]


def test_split_bilateral_agreement_title_starts_own_group_past_boilerplate():
    """A real Bilateral Agreement's title also sits below the header zone,
    behind the same fixed stamp-paper boilerplate block as the Tripartite
    case above, and must be typed BILATERAL_AGREEMENT rather than falling
    through to OTHER_SUPPORTING_DOCUMENT.

    Regression test for a real gap found 2026-08-23 and closed 2026-08-26:
    the literal word "BILATERAL" never appears anywhere on a real Bilateral
    Agreement's own page -- its actual title is "AGREEMENT" / "FOR DIGITAL
    PAYMENT COLLECTION VIA PAYMIR" / "BETWEEN" / ... -- so every existing
    _STRONG_TITLE_PHRASES entry for this type missed it. Confirmed against
    the full real corpus in Confidential Data/.ocr_cache/: this phrase
    appears in exactly 3 of 65 cached files (the two known standalone real
    Bilateral samples plus TMA_Thall_Agreement, see the test below) and
    zero of the other 62, including 10 genuine Tripartite-only samples that
    only mention "Paymir" as incidental body prose. See the
    _FULL_PAGE_STRONG_PHRASES comment for the full evidence.
    """
    body = (
        _stamp_paper_boilerplate()
        + "\nAGREEMENT\nFOR DIGITAL PAYMENT COLLECTION VIA PAYMIR\nBETWEEN\n"
        + "Khyber Pakhtunkhwa Information Technology Board\nAND\n"
        + "Director/Conservator Wildlife Peshawar Zoo"
    )
    types = _doc_types([
        "AUTHORITY LETTER\nAn unrelated, genuinely different document first.",
        body,
    ])
    assert types == [DocumentType.AUTHORITY_LETTER, DocumentType.BILATERAL_AGREEMENT]


def test_split_bundled_tripartite_and_bilateral_instruments_separate():
    """A single source file genuinely carrying both a Participation
    Memorandum (Tripartite) and its own separate Digital Payment Collection
    Agreement (Bilateral) must split into two distinct documents, not one
    merged Tripartite document with the Bilateral content silently absorbed.

    Modeled directly on the real TMA_Thall_Agreement source file
    (Confidential Data/): an Authority Letter, then a Participation
    Memorandum, then -- previously misread as an "embedded sub-section" of
    the same instrument, corrected 2026-08-26 -- a second, complete,
    independent Agreement with its own preamble and party definitions.
    Real onboarding packets do bundle multiple stamp-paper instruments into
    one combined file; the splitter's job is to pull them apart, which it
    could not do for this pairing until the Bilateral title match above
    existed.
    """
    types = _doc_types([
        "AUTHORITY LETTER\nAuthorizes correspondence with 1-Link and KPITB.",
        (
            _stamp_paper_boilerplate()
            + "\nPARTICIPATION MEMORANDUM FOR BILLER/SUB-BILLERS/BILL "
            "AGGREGATOR MEMBERS\nThis Participation Memorandum is "
            "supplemental to the Agreement executed between 1LINK "
            "(Private) Limited and the Bill Aggregator."
        ),
        (
            _stamp_paper_boilerplate()
            + "\nAGREEMENT\nFOR DIGITAL PAYMENT COLLECTION VIA PAYMIR\n"
            "BETWEEN\nKhyber Pakhtunkhwa Information Technology Board\n"
            "AND\nTehsil Municipal Administration THALL"
        ),
    ])
    assert types == [
        DocumentType.AUTHORITY_LETTER,
        DocumentType.TRIPARTITE_AGREEMENT,
        DocumentType.BILATERAL_AGREEMENT,
    ]


def test_split_bare_1link_mention_no_longer_weakly_misclassifies():
    """A page that merely *mentions* "1LINK" in prose, with no strong title
    evidence anywhere, must not be weakly typed ONE_LINK_LETTER anymore --
    it should fall through to OTHER_SUPPORTING_DOCUMENT like any other
    unrecognized page.

    Regression test for the narrowed weak-match: real Participation
    Memorandum documents mention "1LINK" throughout their own body (1LINK
    is the counterparty they're addressed to, not the document's subject),
    which previously caused _classify_text's unanchored substring check to
    mistype unrelated pages as ONE_LINK_LETTER. See
    _WEAK_MATCH_EXCLUDED_PHRASES.
    """
    types = _doc_types([
        "This memo references 1LINK services and ONELINK settlement rules "
        "in passing, but is not itself a 1-Link document of any kind.",
    ])
    assert types == [DocumentType.OTHER_SUPPORTING_DOCUMENT]


def test_split_bare_1link_still_strong_matches_as_its_own_header():
    """The narrowing only removes the bare brand phrases from *weak*
    whole-page matching -- a page whose own header-zone line genuinely
    starts with just "1LINK" (a real letterhead/logo shape) must still be
    recognized as strong evidence, unchanged.
    """
    types = _doc_types([
        "1LINK\nA genuine letterhead-only title page.",
    ])
    assert types == [DocumentType.ONE_LINK_LETTER]


def test_split_absorption_disagreement_is_logged_but_does_not_split(caplog):
    """Option B: when a weakly-classified continuation page disagrees with
    the currently-open group's type, that must be logged for visibility --
    but the split itself must not change as a result. Pure logging, no
    behavior change.
    """
    import logging

    caplog.set_level(logging.WARNING, logger="app.preprocessing.splitter")

    types = _doc_types([
        "TRIPARTITE AGREEMENT\nPage 1.",
        "This page mentions an authority letter in passing, deep in prose, "
        "not as its own header -- so it carries weak but not strong evidence.",
    ])

    assert types == [DocumentType.TRIPARTITE_AGREEMENT]
    assert len(types) == 1
    assert any(
        "possible cross-document absorption" in record.message
        for record in caplog.records
    )


def test_split_absorption_disagreement_is_returned_as_structured_warning():
    """The same disagreement must also be returned as an AbsorptionWarning,
    not just logged -- this is what a caller with a DB session (see
    document_processing/services.py) uses to flag the document for a human
    instead of relying on a console-only log line.
    """
    result = _split_full([
        "TRIPARTITE AGREEMENT\nPage 1.",
        "This page mentions an authority letter in passing, deep in prose, "
        "not as its own header -- so it carries weak but not strong evidence.",
    ])

    assert len(result.documents) == 1
    assert result.documents[0][0] == DocumentType.TRIPARTITE_AGREEMENT
    assert len(result.warnings) == 1
    warning = result.warnings[0]
    assert warning.document_index == 0
    assert warning.document_type == DocumentType.TRIPARTITE_AGREEMENT
    assert warning.page_number == 1
    assert warning.weakly_matched_type == DocumentType.AUTHORITY_LETTER


def test_split_no_warnings_when_every_document_matches_strongly():
    """The common, healthy case: no absorption disagreement anywhere must
    produce an empty warnings list, not just an absent log line.
    """
    result = _split_full([
        "TRIPARTITE AGREEMENT\nPage 1.",
        "AUTHORITY LETTER\nPage 2.",
    ])

    assert len(result.documents) == 2
    assert result.warnings == []


def test_split_multiple_absorbed_pages_in_one_group_produce_one_warning_each():
    """Several disagreeing pages absorbed into the same open group must each
    surface their own warning, all indexed to the same document.
    """
    result = _split_full([
        "TRIPARTITE AGREEMENT\nPage 1.",
        "This page mentions an authority letter in passing, deep in prose, "
        "not as its own header -- so it carries weak but not strong evidence.",
        "This page mentions a business requirement document in passing, deep "
        "in prose, not as its own header -- weak evidence only.",
    ])

    assert len(result.documents) == 1
    assert len(result.warnings) == 2
    assert {w.document_index for w in result.warnings} == {0}
    assert {w.weakly_matched_type for w in result.warnings} == {
        DocumentType.AUTHORITY_LETTER,
        DocumentType.BUSINESS_REQUIREMENT_DOCUMENT,
    }


def test_classify_text_authority_letter():
    """The classifier should detect AUTHORITY LETTER keyword."""
    doc_type = DocumentSplitter._classify_text("AUTHORITY LETTER\nFrom the CEO")
    assert doc_type == DocumentType.AUTHORITY_LETTER


def test_classify_text_none_for_unrecognized():
    """The classifier should return None for unrecognized text."""
    assert DocumentSplitter._classify_text("Random text with no match.") is None


# --- Validation / error handling -------------------------------------------


def test_split_empty_pdf_rejected():
    """An empty PDF must be rejected with an UploadError, not returned as []."""
    with pytest.raises(InvalidFileTypeException):
        DocumentSplitter.split_bulk_pdf(b"")


def test_split_zero_page_pdf_rejected():
    """A valid PDF with no pages must be rejected (no logical documents)."""
    zero_page_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Count 0 /Kids [] >>\nendobj\n"
        b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"
    )
    with pytest.raises(InvalidFileTypeException) as excinfo:
        DocumentSplitter.split_bulk_pdf(zero_page_pdf)
    assert "no documents" in excinfo.value.detail.lower()


def test_split_truncated_pdf_rejected():
    """A truncated PDF (valid header, corrupt body) must map to a 400 error."""
    with pytest.raises(InvalidFileTypeException):
        DocumentSplitter.split_bulk_pdf(b"%PDF-1.4\n%%EOF")


def test_split_non_pdf_bytes_rejected():
    """Garbage bytes that are not a PDF must map to a 400 error."""
    with pytest.raises(InvalidFileTypeException):
        DocumentSplitter.split_bulk_pdf(b"\xff\xd8\xff\xe0\x00\x10JFIF not a pdf")


def test_split_oversized_rejected():
    """Content over the enforced ceiling must raise FileTooLargeException."""
    content = _make_pdf_with_text(["TRIPARTITE AGREEMENT\nBody."])
    with pytest.raises(FileTooLargeException):
        DocumentSplitter.split_bulk_pdf(content, max_bytes=len(content) - 1)


# --- Output integrity ------------------------------------------------------


def test_split_output_is_valid_pdf():
    """Every split chunk must be a readable single-page PDF."""
    result = _split(["AUTHORITY LETTER\nBody.", "BILATERAL AGREEMENT\nBody."])
    assert len(result) == 2
    for doc_type, pdf_bytes in result:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            assert len(doc) == 1
        assert doc_type in (DocumentType.AUTHORITY_LETTER, DocumentType.BILATERAL_AGREEMENT)


# --- ID_DOCUMENT keyword-classifier collision (real-sample regressions) -----
#
# 2026-08-26: re-investigated a "detect_document_type's ID_DOCUMENT category
# collides with 2 real OTHER_SUPPORTING_DOCUMENT samples" gap that had been
# named repeatedly across sessions but never actually re-checked against the
# current corpus. Both originally-flagged files (GDC_Alpurai_Shangla,
# schdule_of_charges_or_bilateral) were real and harmful when first flagged
# (extract_fields(text, ID_DOCUMENT) on them produced garbage -- a full_name
# of "), late fees, fines, security deposits and applicant" for one, "&
# Contact," for the other) -- but both were resolved *incidentally*, by
# splitter title-match fixes landed earlier this same session for unrelated
# reasons (040b4f6, 35c0317), not by anything touching the ID_DOCUMENT
# keyword table itself. A full 66-file real-corpus scan (every file in
# Confidential Data/.ocr_cache/) confirms zero real samples currently reach
# detect_document_type's ID_DOCUMENT-colliding path at all -- see CONTEXT.md
# for the full investigation. `_DETECTION_KEYWORDS`'s ID_DOCUMENT weights
# themselves are UNCHANGED and, called directly, would still misclassify
# this exact text (confirmed, not assumed) -- these tests exist to catch a
# regression in the *splitter routing* that currently keeps that dormant
# fragility from ever being reached, not to claim the keyword table itself
# was fixed.


@requires_real_cache
def test_real_gdc_alpurai_shangla_no_longer_falls_to_other_supporting_document():
    """No longer unclassified -- would have reached detect_document_type's
    ID_DOCUMENT collision (confirmed: this text's literal "Passport" mentions
    score it ID_DOCUMENT if classified directly) before splitter fixes
    landed earlier this session gave it a real checklist-type title match.
    """
    text = _real_cache_text("GDC_Alpurai_Shangla__OTHER_SUPPORTING_DOCUMENT_copy1.txt")
    assert DocumentSplitter._classify_text(text) is DocumentType.TRIPARTITE_AGREEMENT


@requires_real_cache
def test_real_schdule_of_charges_or_bilateral_no_longer_falls_to_other_supporting_document():
    """No longer unclassified -- would have reached detect_document_type's
    ID_DOCUMENT collision (confirmed: this text's "expiry date" mention
    scores it ID_DOCUMENT if classified directly) before the 2026-08-26
    Bilateral Agreement title-match fix (35c0317) gave it a real
    checklist-type title match.
    """
    text = _real_cache_text("schdule_of_charges_or_bilateral__OTHER_SUPPORTING_DOCUMENT_copy1.txt")
    assert DocumentSplitter._classify_text(text) is DocumentType.BILATERAL_AGREEMENT
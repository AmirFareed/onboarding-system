"""Document Splitter Module.

Splits a single large PDF containing all onboarding documents into distinct,
conservatively classified PDF files using PyMuPDF and deterministic text
heuristics. The splitter never performs OCR, AI inference or any external call;
it only converts validated PDF bytes into logical document chunks carrying
:class:`DocumentType` metadata that the upload service persists as
queue-ready ``Document`` rows.
"""

import logging
import string
from typing import NamedTuple

import pymupdf as fitz

from app.database.models.enums import DocumentType
from app.upload.exceptions import (
    FileTooLargeException,
    InvalidFileTypeException,
)

logger = logging.getLogger(__name__)


class AbsorptionWarning(NamedTuple):
    """One page that weakly matched a different type than its open group.

    Surfaces the disagreement `split_bulk_pdf` already logs
    (``c236ba2``) as structured data instead of a console-only log line,
    so a caller with a database session can attach it to the resulting
    ``Document`` row for a human to actually see -- see the
    ``_flag_for_manual_review`` pattern in
    ``document_processing/services.py``/``upload/services.py``, which
    already does exactly this for the related "too many copies" case.
    """

    document_index: int
    document_type: DocumentType
    page_number: int
    weakly_matched_type: DocumentType


class SplitResult(NamedTuple):
    """Return shape of :meth:`DocumentSplitter.split_bulk_pdf`.

    ``documents`` keeps the original ``list[tuple[DocumentType, bytes]]``
    shape callers already rely on; ``warnings`` is additive.
    """

    documents: list[tuple[DocumentType, bytes]]
    warnings: list[AbsorptionWarning]

#: Fraction of the page height treated as the header (title) region. Matches
#: here are *strong* boundary evidence; matches deeper in the page are treated
#: as body text and never start a document.
_HEADER_ZONE_RATIO = 0.33

#: Minimum native selectable-text characters a page must carry before it's
#: trusted as real content; below this, OCR runs instead. Scanner-app exports
#: (e.g. CamScanner) stamp a short watermark as real selectable text on every
#: page -- confirmed directly on real files in Confidential Data/: exactly
#: ``"CamScanner\n"``, 10 characters stripped. The previous threshold here was
#: a flat ``< 10``, so a watermark-only page never cleared it and OCR never
#: ran during splitting -- every page of a real scanned bulk PDF read as just
#: its watermark, matched no title phrase, and the whole file collapsed into
#: one OTHER_SUPPORTING_DOCUMENT instead of splitting. This mirrors the exact
#: same failure mode already found and fixed once before in
#: document_processing.constants.MIN_DIGITAL_TEXT_CHARS_PER_PAGE (also 40,
#: also a CamScanner watermark defeating a flat text-length bar) -- reusing
#: that already-proven value here rather than picking a new number blind.
_MIN_NATIVE_TEXT_CHARS = 40

#: Real Account Maintenance Certificate pages are issued by the account-
#: holding bank on its own letterhead and essentially never carry the
#: literal phrase "ACCOUNT MAINTENANCE CERTIFICATE"/"ACCOUNT MAINTENANCE"
#: anywhere on the page -- confirmed 2026-09-02 on a real sample (TMA Khal
#: Dir Lower, "The Bank of Khyber" statement: Title of Account/Account No./
#: Account Status/Closing Balance fields, bank stamp, no "Account
#: Maintenance" text at all). Without this, the page carries no strong-
#: evidence title match and is silently absorbed into whichever document
#: group is still open (here, the preceding Authority Letter) with no
#: warning, since the weak _classify_text fallback also finds nothing to
#: disagree with -- the AMC checklist slot then reads as missing even
#: though the real document is present in the file.
#:
#: Sourced from 1LINK's own documented list of supported banks/payment
#: channels (KPITB onboarding context), not guessed. Only "Bank of Khyber"
#: is independently confirmed against a real sample in this codebase so
#: far; the remaining names are added defensively from the same closed,
#: finite domain (a real AAMC can only be issued by a 1LINK-supported
#: bank) but are not yet individually real-sample-validated -- treat as
#: candidates to confirm/prune once more real samples land in
#: Confidential Data/.ocr_cache/, same as any other not-yet-fully-verified
#: entry in this file. Full official names only, no bare 2-4 letter
#: abbreviations (HBL/UBL/MCB/NBP/...) -- real letterheads print the full
#: name, and a bare abbreviation anchored at a header-zone line start is a
#: needless extra false-positive surface with no confirmed real benefit.
_ACCOUNT_MAINTENANCE_BANK_NAMES: tuple[str, ...] = (
    "THE BANK OF KHYBER",
    "BANK OF KHYBER",
    "NATIONAL BANK OF PAKISTAN",
    "ABHI MICROFINANCE BANK",
    "FINCA MICROFINANCE BANK",
    "AL BARAKA BANK",
    "ALLIED BANK",
    "APNA MICROFINANCE BANK",
    "ASKARI BANK",
    "BANK AL HABIB",
    "BANK ALFALAH",
    "BANKISLAMI",
    "BANK MAKRAMAH",
    "SUMMIT BANK",
    "THE BANK OF PUNJAB",
    "BANK OF PUNJAB",
    "DUBAI ISLAMIC BANK",
    "EASYPAISA",
    "FAYSAL BANK",
    "FIRST WOMEN BANK",
    "HABIB BANK LIMITED",
    "HABIBMETRO BANK",
    "HABIB METRO BANK",
    "ICBC PAKISTAN",
    "JS BANK",
    "MCB ISLAMIC BANK",
    "MCB BANK",
    "MEEZAN BANK",
    "MOBILINK MICROFINANCE BANK",
    "JAZZCASH",
    "NRSP MICROFINANCE BANK",
    "SAMBA BANK",
    "SINDH BANK",
    "SONERI BANK",
    "STANDARD CHARTERED BANK",
    "UNITED BANK LIMITED",
)

#: Strong title phrases keyed in preference order. Iterated deterministically;
#: the first phrase found wins. These phrases are only ever treated as strong
#: evidence when anchored at the start of a line inside the header region.
_STRONG_TITLE_PHRASES: list[tuple[DocumentType, tuple[str, ...]]] = [
    (DocumentType.TRIPARTITE_AGREEMENT, ("TRIPARTITE AGREEMENT",)),
    (
        DocumentType.BILATERAL_AGREEMENT,
        (
            "BILATERAL AGREEMENT",
            "SERVICE LEVEL AGREEMENT",
            # Merged in 2026-08-25 (department decision): "Schedule of
            # Charges" is the real-world name for this same document, not a
            # distinct type -- SCHEDULE_OF_CHARGES previously had its own
            # entry below for exactly these phrases. Consistent with the
            # 2026-08-22 finding that its content overlaps Bilateral
            # Agreement's own Transaction Charges section, and with a real
            # source file in Confidential Data/ literally named
            # "schdule_of_charges_or_bilateral" -- direct evidence the two
            # names were already being used interchangeably in practice.
            "SUB-BILLER AGREEMENT",
            "SUBBILER AGREEMENT",
            "SUB BILLER AGREEMENT",
            "SCHEDULE OF CHARGES",
        ),
    ),
    (
        DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
        ("ACCOUNT MAINTENANCE CERTIFICATE", "ACCOUNT MAINTENANCE")
        + _ACCOUNT_MAINTENANCE_BANK_NAMES,
    ),
    (
        DocumentType.ONE_LINK_LETTER,
        (
            "1LINK APPLICATION FORM",
            "1-LINK APPLICATION FORM",
            "ONE-LINK APPLICATION FORM",
            "ONE LINK APPLICATION FORM",
            "ONELINK APPLICATION FORM",
            # The genuine Master_Rules_Combined.md Section 4 form's own real
            # title -- it never carries a "1LINK"/"ONE-LINK" brand prefix on
            # the page itself, so none of the phrases above ever matched it.
            # Found 2026-08-18 on a real file (Confidential Data/); the same
            # title was also confirmed present, previously unidentified,
            # inside 3 other already-cached real samples from 2 other files.
            # Deliberately truncated before the final word (originally
            # "...CUSTOMER)"): found 2026-08-22 on a 4th real file
            # (GDC Alpurai Shangla) that this exact title OCR's as
            # "...Customex)" -- a one-character misread past this file's
            # own real content, confirmed nowhere else in the ~9-file real
            # corpus that carries this phrase. A prefix match absorbs any
            # future misread of this one word instead of hardcoding a fix
            # for this specific typo. Verified zero false-positive risk:
            # grepped this shorter prefix against every file in
            # Confidential Data/.ocr_cache/ -- every real occurrence, in
            # every file, is this same genuine title.
            "APPLICATION FORM (IN-DIRECT",
            "ONELINK",
            "ONE-LINK",
            "1LINK",
        ),
    ),
    (DocumentType.AUTHORITY_LETTER, ("AUTHORITY LETTER",)),
    (
        DocumentType.BUSINESS_REQUIREMENT_DOCUMENT,
        ("BUSINESS REQUIREMENT DOCUMENT", "BUSINESS REQUIREMENT"),
    ),
    (
        DocumentType.FORMAL_REQUEST_LETTER,
        (
            "FORMAL REQUEST LETTER",
            "FORMAL REQUEST",
            # The one real sample on file (confirmed 2026-08-18, TMA Lal Dir
            # Upper) never carries either spec-guessed phrase above -- its
            # own subject line is the only reliable anchor found so far.
            # Sits at OCR line index ~11 within its page (well inside the
            # header zone), so no _FULL_PAGE_STRONG_PHRASES exemption is
            # needed here, unlike the Participation Memorandum case.
            # Without this, the page carried no strong-evidence title match
            # of any kind and was silently absorbed into whatever document
            # preceded it (here, a 1-Link Application Form) with no Option B
            # warning either, since the weak _classify_text fallback also
            # checks this same phrase table and found nothing to disagree
            # with.
            "SUBJECT: REQUEST FOR DIGITAL ACCOUNT",
        ),
    ),
]

#: Formal Request Letter structural fallback: real subject lines vary in
#: exact wording per department (confirmed 2026-08-23 on 6 independent real
#: source files -- TMA Lal Dir Upper, TMA Samarbagh, GDC Alpurai Shangla, TMA
#: Khal Dir Lower, TMA Lal Qilla Dir Lower, TMA Thall Hangu), so no phrase
#: list can generalize the way _STRONG_TITLE_PHRASES above does for other
#: types. What is common to all 6, with no exception, is structural: an
#: institutional letterhead line opening with "OFFICE OF THE", followed a few
#: lines later (after a No./Dated/To/addressee block) by a line starting
#: "SUBJECT:". Checked against the entire real OCR cache, not just these 6:
#: the colon is load-bearing -- a bare "SUBJECT" prefix without it false-
#: matches mid-sentence legal boilerplate ("Subject to arbitration...",
#: "Subject to anything hereinbefore contained...") on unrelated document
#: types. Both signals must appear within the header zone on the same page;
#: neither one alone is sufficient (a letterhead alone is just as likely to
#: open an Authority Letter or BRD, and a "SUBJECT:" line alone appears on
#: AMCs and checklist covers too -- see _CHECKLIST_PAGE_MARKERS above for the
#: latter). Evaluated only as a fallback after every existing header-zone
#: check in _classify_page has had a chance to match, so it never overrides
#: an existing phrase match (e.g. TMA Lal Dir Upper's own
#: "SUBJECT: REQUEST FOR DIGITAL ACCOUNT" phrase above still fires first,
#: unchanged) -- it only catches the cases that phrase list misses.
_FORMAL_REQUEST_LETTERHEAD_PREFIX = "OFFICE OF THE"
_FORMAL_REQUEST_SUBJECT_PREFIX = "SUBJECT:"

#: Strong-title phrases that mark a *continuation* of the same logical
#: document when the identical phrase repeats on the immediately following
#: strong-matched page, instead of starting a new copy (the default for
#: every other strong match, including repeated copies of the same type --
#: see the comment in split_bulk_pdf). Confirmed page-count-agnostic
#: 2026-08-18 against 4 real files in Confidential Data/: the genuine
#: Master_Rules_Combined.md Section 4 Application Form repeats this exact
#: header on every one of its own pages (3 pages in 3 samples, 4 in a
#: 4th), and no other real content has ever carried this phrase. Deliberately
#: does not include the brand-prefixed "1LINK APPLICATION FORM" phrase --
#: real repeated pages of that phrase are genuinely separate real forms per
#: MAX_COPIES_BY_DOCUMENT_TYPE's own documented intent ("three 1-Link forms
#: uploaded per application"), not sections of one form, and must keep
#: counting as separate copies (see test_split_mixed_repeated_copies_and_pairs).
#: Must match the exact (possibly truncated) string stored in
#: _STRONG_TITLE_PHRASES above, since split_bulk_pdf compares
#: `matched_phrase` (the literal phrase that matched, not the detected
#: type) against this set.
_CONTINUATION_TITLE_PHRASES: frozenset[str] = frozenset(
    {"APPLICATION FORM (IN-DIRECT"}
)

#: Strong title phrases exempted from the header-zone gate -- matched
#: anchored at the start of any line on the page, not just the top third.
#: Reserved for titles confirmed, across multiple real e-stamp-paper
#: samples, to sit reliably below the header zone because a fixed
#: verification/QR boilerplate block (STAMPING / "Verify Your Stamp
#: Paper" / payment & vendor fields / "Write Below This Line") always
#: precedes the real title on the same page. Confirmed 2026-08-18: this
#: exact title sits at OCR line index ~34-42 across 3 measured
#: occurrences from 2 independent real files (GDA Abbotabad copies 1 and
#: 2, TMA Khal Dir Lower) -- all past the header zone's ~28-line cutoff
#: (842pt real page height * 0.33 ratio, divided by the 10pt synthetic
#: OCR line spacing) -- so header-zone gating would silently never match
#: it.
#:
#: **Corrected 2026-08-25**: previously mapped to DocumentType.ONE_LINK_LETTER
#: per a 2026-08-19 department decision, on the (at-the-time-open) theory
#: that this checklist slot's real occupant is usually a Participation
#: Memorandum rather than the Master_Rules_Combined.md Section 4
#: Application Form -- see the still-open "1-Link Letter checklist-meaning
#: mismatch" entry in CONTEXT.md and OneLinkLetterExtractor's own docstring
#: for that history. Corrected by the department tonight: a "PARTICIPATION
#: MEMORANDUM FOR BILLER/SUB-BILLER/BILL AGGREGATOR MEMBERS" is the
#: Tripartite Agreement -- a stamp-paper instrument identified by its
#: three signing parties (1LINK, the department, KPITB), not by carrying
#: a literal "TRIPARTITE AGREEMENT" title anywhere on the page, which is
#: why _STRONG_TITLE_PHRASES's own header-zone TRIPARTITE_AGREEMENT entry
#: never caught it. Confirmed on every real sample in
#: Confidential Data/.ocr_cache/ that carries this phrase (GDA Abbotabad,
#: GDC Madyan Swat, TMA Khal Dir Lower, TMA Lal Dir Upper, TMA Lal Qilla
#: Dir Lower, TMA Samarbagh, TMA Thall Hangu, and a file literally named
#: "tripartite") -- all show the same "1- For & Behalf of / 2- / 3-"
#: three-party signature block, zero counterexamples found. Unlike
#: _CONTINUATION_TITLE_PHRASES, this title does not repeat per-page within
#: one real instance (confirmed on the same samples), so no continuation
#: handling is needed here -- the existing "absorb into the just-opened
#: group" behavior already correctly handles this document's own later
#: pages.
#:
#: **2026-08-26: Bilateral Agreement given its own title match, closing the
#: gap the "deliberately not attempted" note above used to describe.** That
#: note was about discriminating Tripartite from Bilateral by *party count*
#: (correctly rejected -- "First Party"/"Second Party" fields are generic
#: template text on every stamp paper, both types alike). This is a
#: different, much safer mechanism: matching the Bilateral document's own
#: real title text directly, the same approach already proven for
#: Tripartite above -- not a discriminator at all, just a title neither
#: type's page can spoof, since Tripartite's own title
#: ("PARTICIPATION MEMORANDUM...") is completely different text.
#: Confirmed against the full real corpus in Confidential Data/.ocr_cache/:
#: "FOR DIGITAL PAYMENT COLLECTION VIA PAYMIR" (the literal second line of
#: the real title, "AGREEMENT" / "FOR DIGITAL PAYMENT COLLECTION VIA
#: PAYMIR" / "BETWEEN" / "Khyber Pakhtunkhwa Information Technology Board"
#: / "AND" / <counterparty>) appears in exactly 3 of 65 cached files --
#: the two known standalone real Bilateral samples (Conservator Wildlife
#: Peshawar Zoo, schdule_of_charges_or_bilateral) plus TMA_Thall_Agreement,
#: and zero of the other 62, including 10 genuine Tripartite-only samples
#: that mention "Paymir" only as incidental defined-terms body prose
#: ("the Paymir Digital Payment Platform...") without ever carrying this
#: exact heading. TMA_Thall_Agreement is the useful case: previously read
#: (see the old note this replaced) as a Bilateral clause "embedded" inside
#: one Tripartite document and therefore unsafe to split out -- rereading
#: the actual cached text shows it is not an embedded clause but a second,
#: complete, independent Agreement (its own "made and entered into on
#: this ___ day", its own First Party/Second Party definitions, its own
#: WHEREAS section) physically bundled after a separate Authority Letter
#: and Participation Memorandum in the same source file -- exactly the
#: kind of multi-instrument bundling the splitter exists to pull apart,
#: not a reason to keep it merged. "AGREEMENT" alone is deliberately not
#: used as the anchor (every one of these stamp papers' own e-stamp
#: Description field literally reads "AGREEMENT" regardless of type,
#: confirmed on both Bilateral samples and 3 Tripartite samples --
#: anchoring there would false-positive on every stamp-paper cover page).
#: Placed in this exempted list, not _STRONG_TITLE_PHRASES, for the same
#: reason as Tripartite above: on schdule_of_charges_or_bilateral this
#: title sits well below the header zone, behind the same STAMPING/
#: verification/payment-fields boilerplate block.
_FULL_PAGE_STRONG_PHRASES: list[tuple[DocumentType, tuple[str, ...]]] = [
    (DocumentType.TRIPARTITE_AGREEMENT, ("PARTICIPATION MEMORANDUM",)),
    (DocumentType.BILATERAL_AGREEMENT, ("FOR DIGITAL PAYMENT COLLECTION VIA PAYMIR",)),
]

#: Bare brand-name phrases in _STRONG_TITLE_PHRASES that are safe as
#: *strong* evidence (anchored at the start of a header-zone line -- a
#: real letterhead/logo shape) but too broad to trust as *weak* whole-
#: page substring evidence. Confirmed 2026-08-18: real Participation
#: Memorandum documents mention "1LINK" throughout their own body text
#: (1LINK is the counterparty they're addressed to, not the document's
#: subject), so _classify_text's unanchored substring check was mistyping
#: them as ONE_LINK_LETTER even with no real ONE_LINK_LETTER document
#: anywhere nearby -- confirmed on 3 occurrences within one real file
#: (GDA Abbotabad copies 2-4, cached OCR text): copy 2 fully read and
#: verbatim-confirmed, copies 3-4 pattern-matched at high/medium-high
#: confidence but not independently full-text-verified. Excluded from
#: _classify_text's weak fallback only; strong header-zone matching via
#: _classify_page is untouched.
#:
#: The _ACCOUNT_MAINTENANCE_BANK_NAMES entries are excluded for the exact
#: same reason: real Tripartite/Participation Memorandum pages state their
#: bank account details in prose deep in the page body (e.g. "...maintained
#: with (BANK OF KHYBER) in its branch...", confirmed on this same TMA Khal
#: Dir Lower file, page 9-10) -- a bank name mentioned *by* another
#: document as the account-holding bank is not evidence that page itself
#: is the bank's own AMC letterhead. Header-zone strong matching via
#: _classify_page is untouched; only the unanchored whole-page fallback is
#: excluded.
_WEAK_MATCH_EXCLUDED_PHRASES: frozenset[str] = frozenset(
    {"1LINK", "ONELINK", "ONE-LINK", *_ACCOUNT_MAINTENANCE_BANK_NAMES}
)

#: Marks a manifest/checklist cover page -- confirmed on multiple independent
#: real files in Confidential Data/: such a page lists every required document
#: by name (e.g. "Authority Letter", "Account Maintenance Certificate"), so its
#: own table rows can satisfy a _STRONG_TITLE_PHRASES entry inside the header
#: zone even though the page itself is not that document. Real titles seen so
#: far: plain "CHECKLIST", "MASTER CHECKLIST" (no space -- a prefix check
#: (startswith) caught the first but silently missed the second, so this is
#: matched as a substring rather than a prefix), and "MASTER CHECK LIST" /
#: "CHECK LIST FOR ON BOARDING..." (two words -- found 2026-08-23 on
#: TMA_Thall_Hangu__AUTHORITY_LETTER_copy1.txt while validating the Formal
#: Request Letter structural rule below: this file's checklist page used only
#: the two-word spelling, so the single-string "CHECKLIST" substring check
#: silently missed it and let its own "Authority Letter" row strong-match
#: AUTHORITY_LETTER, plus -- newly, before this fix -- also would have
#: satisfied the new letterhead+subject structural signal). Grepped the full
#: real corpus for "CHECK LIST": appears in exactly 2 files, both genuine
#: checklist covers, zero non-checklist real content -- safe to add as a
#: second marker. See the check in _classify_page below.
_CHECKLIST_PAGE_MARKERS: tuple[str, ...] = ("CHECKLIST", "CHECK LIST")

#: Header phrases shared by both faces of a CNIC. A page anchored with one of
#: these is a CNIC; the face is then decided by side-specific keyword scoring.
_CNIC_HEADER_PHRASES: tuple[str, ...] = (
    "COMPUTERISED NATIONAL IDENTITY",
    "COMPUTERIZED NATIONAL IDENTITY",
    "NATIONAL IDENTITY CARD",
    "ISLAMIC REPUBLIC OF PAKISTAN",
)

#: Deterministic side discriminators for the CNIC back face. Any back
#: indicator wins, so a real back page can never be labelled CNIC_FRONT.
#: ``NADRA`` is intentionally excluded: the front face also carries the NADRA
#: logo and a bare mention must not flip a front page to CNIC_BACK.
_CNIC_BACK_KEYS: tuple[str, ...] = (
    "ISSUING AUTHORITY",
    "ISSUE DATE",
    "DATE OF ISSUE",
    "PLACE OF ISSUE",
    "MANAGER",
    "THUMB",
    "QUALIFICATION",
)

#: Deterministic side discriminators for the CNIC front face.
_CNIC_FRONT_KEYS: tuple[str, ...] = (
    "IDENTITY NUMBER",
    "DATE OF BIRTH",
    "FATHER NAME",
    "FATHER'S NAME",
    "FATHERS NAME",
    "GENDER",
)


class DocumentSplitter:
    """Splits a bulk PDF into conservative, individually classified documents."""

    @classmethod
    def validate_structure(
        cls,
        content: bytes,
        *,
        max_bytes: int | None = None,
    ) -> None:
        """Cheaply reject unreadable or empty PDFs before they are queued.

        Opens the PDF just far enough to confirm it is well-formed and has at
        least one page -- no per-page classification or OCR, so this is safe
        to call synchronously from the upload request even though the actual
        split (page classification, optional OCR fallback) is deferred to the
        background queue worker.

        Raises:
            InvalidFileTypeException: When the content is empty, is not a
                readable PDF, or has zero pages.
            FileTooLargeException: When ``content`` exceeds ``max_bytes``.
        """
        if not content:
            raise InvalidFileTypeException("The uploaded file is empty")
        if max_bytes is not None and len(content) > max_bytes:
            raise FileTooLargeException(
                f"File exceeds the maximum allowed size of {max_bytes // (1024 * 1024)} MB"
            )
        if not content.startswith(b"%PDF-"):
            raise InvalidFileTypeException(
                "The uploaded file is not a valid, readable PDF"
            )

        try:
            document = fitz.open(stream=content, filetype="pdf")
        except (fitz.FileDataError, fitz.EmptyFileError, ValueError) as exc:
            raise InvalidFileTypeException(
                "The uploaded file is not a valid, readable PDF"
            ) from exc

        try:
            if len(document) == 0:
                raise InvalidFileTypeException(
                    "Bulk PDF produced no documents; expected at least one"
                )
        finally:
            document.close()

    @classmethod
    def split_bulk_pdf(
        cls,
        content: bytes,
        *,
        max_bytes: int | None = None,
        ocr_engine: object | None = None,
    ) -> SplitResult:
        """Split in-memory PDF ``content`` into categorized document bytes.

        The caller is expected to have already enforced the upload size limit;
        ``max_bytes`` is a defensive backstop so an out-of-range (e.g. future)
        call can never process a file larger than the configured maximum.

        Args:
            content: Full PDF file content (already read within the upload size
                limit — never pass a lazily-read stream here).
            max_bytes: Optional hard ceiling. Content larger than this is
                rejected with :class:`FileTooLargeException`.

        Returns:
            A :class:`SplitResult`: ``documents`` is a list of
            ``(DocumentType, PDF bytes)``, one entry per logical document (a
            valid PDF that yields no logical documents is rejected);
            ``warnings`` lists every page that was silently absorbed into an
            open document despite weakly matching a different type --
            ``document_index`` indexes into ``documents``.

        Raises:
            InvalidFileTypeException: When the content is empty, is not a
                readable PDF, or yields zero logical documents.
            FileTooLargeException: When ``content`` exceeds ``max_bytes``.
        """
        if not content:
            raise InvalidFileTypeException("The uploaded file is empty")
        if max_bytes is not None and len(content) > max_bytes:
            raise FileTooLargeException(
                f"File exceeds the maximum allowed size of {max_bytes // (1024 * 1024)} MB"
            )
        if not content.startswith(b"%PDF-"):
            raise InvalidFileTypeException(
                "The uploaded file is not a valid, readable PDF"
            )

        try:
            document = fitz.open(stream=content, filetype="pdf")
        except (fitz.FileDataError, fitz.EmptyFileError, ValueError) as exc:
            raise InvalidFileTypeException(
                "The uploaded file is not a valid, readable PDF"
            ) from exc

        split_documents: list[tuple[DocumentType, bytes]] = []
        warnings: list[AbsorptionWarning] = []
        current_type: DocumentType | None = None
        current_pages: list[int] = []
        #: The strong-title phrase that opened/last extended current_pages,
        #: when it's a _CONTINUATION_TITLE_PHRASES entry -- lets a repeat of
        #: that exact phrase extend the same document instead of starting a
        #: new copy. None for any other phrase (or no phrase yet).
        current_continuation_phrase: str | None = None
        #: (page_number, weakly_matched_type) pairs collected for the
        #: currently-open group -- flushed into `warnings`, indexed against
        #: `split_documents`, whenever that group is finalized below.
        pending_warnings: list[tuple[int, DocumentType]] = []

        def _finalize_current_group() -> None:
            split_documents.append(
                (current_type, cls._create_pdf(document, current_pages))
            )
            if pending_warnings:
                document_index = len(split_documents) - 1
                for page_num, weak_type in pending_warnings:
                    warnings.append(
                        AbsorptionWarning(
                            document_index=document_index,
                            document_type=current_type,
                            page_number=page_num,
                            weakly_matched_type=weak_type,
                        )
                    )
                pending_warnings.clear()

        try:
            for page_num in range(len(document)):
                page = document.load_page(page_num)
                detected_type, strong_evidence, matched_phrase = cls._classify_page(
                    page, ocr_engine
                )

                if (
                    strong_evidence
                    and current_pages
                    and matched_phrase is not None
                    and matched_phrase == current_continuation_phrase
                ):
                    # The same continuation-eligible title repeats on this
                    # strong-matched page: still the same logical multi-page
                    # document (e.g. the 1-Link Application Form's own Form
                    # A / directors / Form B sections), not a new copy.
                    current_pages.append(page_num)
                elif strong_evidence:
                    # Strong header/title evidence marks a fresh document —
                    # even when it equals the current type (repeated copies).
                    if current_pages:
                        _finalize_current_group()
                    current_type = detected_type or DocumentType.OTHER_SUPPORTING_DOCUMENT
                    current_pages = [page_num]
                    current_continuation_phrase = (
                        matched_phrase
                        if matched_phrase in _CONTINUATION_TITLE_PHRASES
                        else None
                    )
                elif current_pages:
                    # No boundary evidence: a continuation page. Body keywords
                    # must never start a new document -- but if the weak
                    # classifier recognizes a *different* type than the one
                    # currently open, that disagreement is worth surfacing
                    # for a human to check, even though the split itself
                    # doesn't change here (visibility only, no behavior
                    # change -- see CONTEXT.md 2026-08-18 on the confirmed
                    # cross-document absorption this discards otherwise).
                    if detected_type is not None and detected_type != current_type:
                        logger.warning(
                            "Page %s weakly matches %s but was absorbed into "
                            "the open %s document -- possible cross-document "
                            "absorption, review recommended",
                            page_num,
                            detected_type.value,
                            current_type.value if current_type else "OTHER_SUPPORTING_DOCUMENT",
                        )
                        pending_warnings.append((page_num, detected_type))
                    current_pages.append(page_num)
                else:
                    # First page without strong evidence: weak phrases only type
                    # the document; never split on them.
                    current_type = detected_type or DocumentType.OTHER_SUPPORTING_DOCUMENT
                    current_pages = [page_num]
                    current_continuation_phrase = None

            if current_pages:
                _finalize_current_group()
        finally:
            document.close()

        if not split_documents:
            raise InvalidFileTypeException(
                "Bulk PDF produced no documents; expected at least one"
            )

        logger.info("Split bulk PDF into %s documents", len(split_documents))
        return SplitResult(documents=split_documents, warnings=warnings)

    @classmethod
    def _classify_page(
        cls, page: fitz.Page, ocr_engine: object | None = None
    ) -> tuple[DocumentType | None, bool, str | None]:
        """Classify one page, returning ``(type, strong_evidence, matched_phrase)``.

        ``strong_evidence`` is only ever ``True`` for anchored title phrases in
        the header region of the page. The returned type without strong
        evidence is weak/full-text evidence, usable only for typing a document
        that has no type yet. ``matched_phrase`` is the exact
        _STRONG_TITLE_PHRASES entry that matched (``None`` otherwise) -- used
        by split_bulk_pdf to detect a repeated _CONTINUATION_TITLE_PHRASES
        entry across consecutive pages. Also ``None`` (with strong_evidence
        ``True``) for the Formal Request Letter structural fallback below,
        since that match has no single literal phrase to report -- it is
        never a continuation candidate anyway (every real occurrence is a
        single page).
        """
        lines = _extract_lines(page)
        page_height = page.rect.height or 0
        full_text = " ".join(text for _, text in lines)

        if len(full_text.strip()) < _MIN_NATIVE_TEXT_CHARS and ocr_engine:
            try:
                import cv2
                import numpy as np
                pix = page.get_pixmap(dpi=150)
                img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                if pix.n == 4:
                    img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
                
                result = ocr_engine.extract(img)
                full_text = result.text
                
                # Upper-cased to match _extract_lines' convention: every
                # phrase in _STRONG_TITLE_PHRASES/_CNIC_HEADER_PHRASES is
                # matched via a case-sensitive startswith() against an
                # all-caps phrase, so raw (non-upper-cased) OCR output would
                # silently fail to match a title printed in mixed case.
                lines = []
                for idx, line_text in enumerate(full_text.splitlines()):
                    lines.append((float(idx * 10), line_text.upper()))
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("PaddleOCR fallback failed during split: %s", exc)

        found_formal_request_letterhead = False
        found_formal_request_subject = False
        for y_position, text in lines:
            if page_height and y_position >= page_height * _HEADER_ZONE_RATIO:
                continue
            # A checklist page can never be one of the documents it lists --
            # bail out before any title matching (strong or the weak
            # _classify_text fallback below, which would hit the same table
            # row as a substring match) so it can't masquerade as one. Matched
            # as a substring, not a prefix: real titles seen include both a
            # plain "CHECKLIST", "MASTER CHECKLIST" and "MASTER CHECK LIST"
            # that a prefix check would silently miss.
            if any(marker in text for marker in _CHECKLIST_PAGE_MARKERS):
                return None, False, None
            for phrase in _CNIC_HEADER_PHRASES:
                if text.startswith(phrase):
                    return cls._resolve_cnic_side(full_text), True, None
            for doc_type, phrases in _STRONG_TITLE_PHRASES:
                for phrase in phrases:
                    if text.startswith(phrase):
                        return doc_type, True, phrase
            # Real scans routinely OCR a stray leading punctuation mark onto an
            # otherwise-clean line (e.g. ".Subject:" for "Subject:") -- found
            # 2026-08-23 on a real Formal Request Letter that the structural
            # fallback below should have caught but didn't, because a strict
            # startswith() has no tolerance for it. Stripped once, up front,
            # rather than switching to an unanchored substring check: the
            # colon-anchored prefix match is still what excludes mid-sentence
            # boilerplate ("Subject to arbitration...") -- only leading noise
            # is forgiven, not the position of the phrase itself.
            stripped_text = text.lstrip(string.punctuation + " ")
            if stripped_text.startswith(_FORMAL_REQUEST_LETTERHEAD_PREFIX):
                found_formal_request_letterhead = True
            if stripped_text.startswith(_FORMAL_REQUEST_SUBJECT_PREFIX):
                found_formal_request_subject = True

        # Formal Request Letter structural fallback: only reached once every
        # phrase-based check above has had its chance on every header-zone
        # line without matching, so it never overrides a more specific match.
        if found_formal_request_letterhead and found_formal_request_subject:
            return DocumentType.FORMAL_REQUEST_LETTER, True, None

        # Second pass: phrases confirmed to sit reliably below the header
        # zone on real samples (see _FULL_PAGE_STRONG_PHRASES) -- still
        # anchored at the start of a line, just not zone-restricted.
        for _y_position, text in lines:
            for doc_type, phrases in _FULL_PAGE_STRONG_PHRASES:
                for phrase in phrases:
                    if text.startswith(phrase):
                        return doc_type, True, phrase

        return cls._classify_text(full_text), False, None

    @staticmethod
    def _classify_text(text: str) -> DocumentType | None:
        """Classify a page's full text with deterministic title heuristics.

        ``None`` means "no recognizable document type"; callers fall back to
        :class:`DocumentType.OTHER_SUPPORTING_DOCUMENT`.
        """
        upper = text.upper()
        for doc_type, phrases in _STRONG_TITLE_PHRASES:
            for phrase in phrases:
                if phrase in _WEAK_MATCH_EXCLUDED_PHRASES:
                    continue
                if phrase in upper:
                    return doc_type
        for doc_type, phrases in _FULL_PAGE_STRONG_PHRASES:
            for phrase in phrases:
                if phrase in upper:
                    return doc_type
        if any(phrase in upper for phrase in _CNIC_HEADER_PHRASES):
            return DocumentSplitter._resolve_cnic_side(upper)
        return None

    @staticmethod
    def _resolve_cnic_side(full_text: str) -> DocumentType:
        """Return ``CNIC_BACK`` or ``CNIC_FRONT`` from deterministic field keys.

        Any back-side indicator wins so real back pages are never labelled
        front; otherwise front-side identity fields choose the front face. An
        unrecognised side defaults to front (the most commonly scanned face).
        """
        if any(key in full_text for key in _CNIC_BACK_KEYS):
            return DocumentType.CNIC_BACK
        if any(key in full_text for key in _CNIC_FRONT_KEYS):
            return DocumentType.CNIC_FRONT
        return DocumentType.CNIC_FRONT

    @staticmethod
    def _create_pdf(source_doc: fitz.Document, page_numbers: list[int]) -> bytes:
        """Extract specific pages from a source document into new PDF bytes."""
        new_doc = fitz.open()
        for page_num in page_numbers:
            new_doc.insert_pdf(source_doc, from_page=page_num, to_page=page_num)

        pdf_bytes = new_doc.write()
        new_doc.close()
        return pdf_bytes


def _extract_lines(page: fitz.Page) -> list[tuple[float, str]]:
    """Return ``(y0, upper-cased text)`` for every text line on the page."""
    lines: list[tuple[float, str]] = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            bbox = line.get("bbox") or (0.0, 0.0, 0.0, 0.0)
            text = "".join(
                span.get("text", "") for span in line.get("spans", [])
            ).strip().upper()
            if text:
                lines.append((bbox[1], text))
    return lines
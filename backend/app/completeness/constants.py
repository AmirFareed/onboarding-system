"""Configuration for the document completeness module.

The canonical classification of document types into mandatory and optional
categories lives here and nowhere else. Verification logic consumes these sets
so adding a document type only requires editing this module, never the service,
route or schema code.
"""

from enum import StrEnum

from app.database.models.enums import DocumentType


class CompletenessStatus(StrEnum):
    """Overall outcome of a completeness verification.

    The precedence is strictest-first: an invalid document set always wins over
    duplicates, which win over incompleteness.
    """

    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    DUPLICATE_DOCUMENTS = "DUPLICATE_DOCUMENTS"
    INVALID_DOCUMENT_SET = "INVALID_DOCUMENT_SET"


#: Document types every application must provide exactly once.
#:
#: SCHEDULE_OF_CHARGES deliberately removed 2026-08-22: real-world evidence
#: (every candidate real sample found so far, including every file whose name
#: suggested this type) confirms it is not a real standalone document in this
#: checklist -- its content (the Payment Methods & Charges clause) lives
#: inside the Bilateral Agreement, which already has its own real extractor
#: (BilateralAgreementExtractor.transaction_charges) and its own required
#: presence check above. See CONTEXT.md for the full decision record.
#:
#: CNIC_FRONT added 2026-08-23: the frontend's own upload checklist
#: (data/documents.js) already treats CNIC as required and has since before
#: this module existed -- this set had simply never been reconciled against
#: it, so a fully-compliant applicant who uploaded everything the Upload
#: page asked for, including CNIC, could never reach COMPLETE (CNIC_FRONT
#: fell through to the "unexpected document" path instead). CNIC_FRONT only,
#: not CNIC_BACK: CNIC_FRONT already has a real, sample-validated extractor
#: (CnicFrontExtractor) -- positive evidence real applications include it.
#: CNIC_BACK has the standing, deliberate "zero real samples exist" gap
#: (see CONTEXT.md, 2026-08-17) that keeps it out of extraction scope too;
#: making it a hard completeness requirement without any real evidence risks
#: repeating the SCHEDULE_OF_CHARGES mistake -- an unconditional blocker for
#: a type that may not structurally arrive from a real bulk split.
REQUIRED_DOCUMENT_TYPES: frozenset[DocumentType] = frozenset(
    {
        DocumentType.TRIPARTITE_AGREEMENT,
        DocumentType.BILATERAL_AGREEMENT,
        DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
        DocumentType.ONE_LINK_LETTER,
        DocumentType.AUTHORITY_LETTER,
        DocumentType.BUSINESS_REQUIREMENT_DOCUMENT,
        DocumentType.FORMAL_REQUEST_LETTER,
        DocumentType.CNIC_FRONT,
    }
)

#: Document types an application may provide but does not have to.
OPTIONAL_DOCUMENT_TYPES: frozenset[DocumentType] = frozenset(
    {
        DocumentType.OTHER_SUPPORTING_DOCUMENT,
    }
)

#: Document types that are internal processing artifacts rather than real
#: onboarding documents (e.g. the BULK_UPLOAD placeholder that holds a bulk
#: PDF until it is split). They are recognised -- never flagged as unexpected
#: -- but contribute nothing to required or optional presence.
PLACEHOLDER_DOCUMENT_TYPES: frozenset[DocumentType] = frozenset(
    {
        DocumentType.BULK_UPLOAD,
    }
)

#: Every document type the pipeline recognises (required plus optional plus
#: placeholders). Any document type outside this set is treated as unexpected.
ALL_CONFIGURED_DOCUMENT_TYPES: frozenset[DocumentType] = (
    REQUIRED_DOCUMENT_TYPES | OPTIONAL_DOCUMENT_TYPES | PLACEHOLDER_DOCUMENT_TYPES
)

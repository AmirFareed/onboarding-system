"""Configuration for the document analysis module.

Centralizes the analysed document types, the verification statuses, the scoring
weights and thresholds, and the analysis version. The extractor, validator,
consistency and scoring code consume these constants, so tuning a threshold or
adding a document type never requires touching the service or route layers.
"""

from enum import StrEnum


class AnalyzedDocumentType(StrEnum):
    """Document categories recognised by the analysis pipeline.

    Independent of the storage-level ``DocumentType`` enum (which only holds the
    upload checklist categories); the analysed category is inferred from the OCR
    text by rule-based heuristics.
    """

    BANK_STATEMENT = "BANK_STATEMENT"
    PAYSLIP = "PAYSLIP"
    ID_DOCUMENT = "ID_DOCUMENT"
    TAX_DOCUMENT = "TAX_DOCUMENT"
    #: Phase 1 of the required-document checklist (see
    #: docs/IMPLEMENTATION_ROADMAP.md). Named identically to the storage-level
    #: DocumentType they correspond to, but distinct enums -- routed via
    #: document_analysis.services._CHECKLIST_TYPE_MAP, not via
    #: detect_document_type's keyword table.
    BILATERAL_AGREEMENT = "BILATERAL_AGREEMENT"
    AUTHORITY_LETTER = "AUTHORITY_LETTER"
    ACCOUNT_MAINTENANCE_CERTIFICATE = "ACCOUNT_MAINTENANCE_CERTIFICATE"
    TRIPARTITE_AGREEMENT = "TRIPARTITE_AGREEMENT"
    #: Phase 1, fourth checklist type. Named identically to the storage-level
    #: DocumentType.BUSINESS_REQUIREMENT_DOCUMENT it corresponds to -- see the
    #: BILATERAL_AGREEMENT comment above for the same routing note.
    BUSINESS_REQUIREMENT_DOCUMENT = "BUSINESS_REQUIREMENT_DOCUMENT"
    #: Phase 1, fifth checklist type. Named identically to the storage-level
    #: DocumentType.ONE_LINK_LETTER it corresponds to -- see the
    #: BILATERAL_AGREEMENT comment above for the same routing note. In every
    #: real sample seen so far this slot is actually populated by a
    #: Participation Memorandum, not the docs/Master_Rules_Combined.md
    #: Section 4 Application Form -- see OneLinkLetterExtractor's docstring
    #: and CONTEXT.md for the full finding; this extractor is grounded in
    #: what's really there, not the unvalidated spec document.
    ONE_LINK_LETTER = "ONE_LINK_LETTER"
    #: Phase 1, sixth checklist type -- front face only. Named identically to
    #: the storage-level DocumentType.CNIC_FRONT it corresponds to -- see the
    #: BILATERAL_AGREEMENT comment above for the same routing note.
    #: DocumentType.CNIC_BACK stays unmapped: zero real CNIC_BACK samples
    #: exist anywhere in this session's cache (see CONTEXT.md), so back-face
    #: extraction has no real-sample validation and is explicitly out of
    #: scope until a sample turns up -- see CnicFrontExtractor's docstring.
    CNIC_FRONT = "CNIC_FRONT"
    FORMAL_REQUEST_LETTER = "FORMAL_REQUEST_LETTER"
    UNKNOWN = "UNKNOWN"


class VerificationStatus(StrEnum):
    """Overall outcome of the verification scoring."""

    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


#: Version of the extraction/scoring logic. Bumped whenever the rules change so
#: stored results can be traced to the exact logic that produced them.
ANALYSIS_VERSION: str = "1.0.0"

#: Tolerance (in currency units) when reconciling balances.
BALANCE_EPSILON: float = 0.01

#: Deterministic scoring weights. Extraction coverage dominates because a
#: document with missing critical fields cannot be trusted regardless of how
#: clean the remaining validations are.
SCORE_WEIGHT_FIELD_COVERAGE: float = 0.5
SCORE_WEIGHT_VALIDATION: float = 0.3
SCORE_WEIGHT_CONSISTENCY: float = 0.2

#: Score thresholds mapping a confidence score to a verification status.
VERIFIED_MIN_SCORE: float = 0.8
PARTIALLY_VERIFIED_MIN_SCORE: float = 0.6
NEEDS_REVIEW_MIN_SCORE: float = 0.4

# -- Expected and critical field sets per analysed document type --------------
#: Every field a type is expected to carry; used for extraction coverage.
EXPECTED_FIELDS: dict[AnalyzedDocumentType, frozenset[str]] = {
    AnalyzedDocumentType.BANK_STATEMENT: frozenset(
        {
            "account_holder",
            "account_number",
            "iban",
            "bank_name",
            "statement_period",
            "opening_balance",
            "closing_balance",
            "total_credits",
            "total_debits",
            "currency",
            "transaction_count",
        }
    ),
    AnalyzedDocumentType.PAYSLIP: frozenset(
        {
            "employee_name",
            "employer_name",
            "gross_salary",
            "net_salary",
            "salary_month",
            "payment_date",
            "employee_id",
        }
    ),
    AnalyzedDocumentType.ID_DOCUMENT: frozenset(
        {
            "full_name",
            "date_of_birth",
            "document_number",
            "nationality",
            "issue_date",
            "expiry_date",
        }
    ),
    AnalyzedDocumentType.TAX_DOCUMENT: frozenset(
        {
            "taxpayer_name",
            "tax_reference_number",
            "tax_year",
            "gross_income",
            "total_tax",
            "currency",
        }
    ),
    #: Field names deliberately match app.rule_engine.rules.cross_document_rules
    #: (account_holder, account_number, iban): those rules are already
    #: registered and compare these exact names across BILATERAL_AGREEMENT,
    #: TRIPARTITE_AGREEMENT and ACCOUNT_MAINTENANCE_CERTIFICATE, but until now
    #: none of the three had any extractor, so the rules could only ever FAIL
    #: on a real application ("field is missing from document"). This is the
    #: first of the three to close that gap.
    AnalyzedDocumentType.BILATERAL_AGREEMENT: frozenset(
        {
            "organization_name",
            "platform_name",
            "transaction_charges",
            "account_holder",
            "account_number",
            "iban",
            "effective_date",
        }
    ),
    #: account_holder/account_number/iban are opportunistic, not guaranteed:
    #: docs/Master_Rules_Combined.md Section 2 says "account maintenance
    #: details must appear at the top", but neither real sample reviewed so
    #: far (two independent departments, Confidential Data/) carries any bank
    #: account information at all -- real evidence overrides the spec's
    #: framing here, see CRITICAL_FIELDS below.
    AnalyzedDocumentType.AUTHORITY_LETTER: frozenset(
        {
            "focal_person_name",
            "focal_person_designation",
            "organization_name",
            "account_holder",
            "account_number",
            "iban",
        }
    ),
    # Real required-document checklist categories with field-level extractors.
    # Field names deliberately match the cross-document consistency rules
    # (app/rule_engine/rules/cross_document_rules.py): account_holder,
    # account_number, iban, statement_period and branch_code must keep their
    # exact names so the normalization stage can compare them across
    # Bilateral / Tripartite / AMC documents.
    AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE: frozenset(
        {
            "account_holder",
            "account_number",
            "iban",
            "bank_name",
            "branch_name",
            "issue_date",
        }
    ),
    AnalyzedDocumentType.TRIPARTITE_AGREEMENT: frozenset(
        {
            "party_1link",
            "party_kpitb",
            "party_subbiller",
            "account_holder",
            "account_number",
            "branch_code",
        }
    ),
    #: docs/Master_Rules_Combined.md Section 10 requires the BRD to both
    #: confirm digitization intent and list the revenue-generating services.
    #: Real BRDs (three independent departments, Confidential Data/) satisfy
    #: both but with no shared template -- see CRITICAL_FIELDS below for why
    #: only one of the two is treated as reliably detectable.
    AnalyzedDocumentType.BUSINESS_REQUIREMENT_DOCUMENT: frozenset(
        {"digitization_intent_confirmed", "revenue_services_listed"}
    ),
    #: branch_code stays excluded -- unchanged from the original 2026-08-19
    #: decision, still true against the corrected real-content shape (see
    #: OneLinkLetterExtractor's docstring): the form has no such field at
    #: all. account_number_or_iban/account_holder/bank_name added
    #: 2026-09-14 once the extractor was corrected to target the genuine
    #: "Application Form (In-Direct Customer)" instead of the Participation
    #: Memorandum this slot no longer receives -- all three are reliably
    #: present, single-valued fields on every one of 8 independent real
    #: samples checked.
    AnalyzedDocumentType.ONE_LINK_LETTER: frozenset(
        {"organization_name", "account_number_or_iban", "account_holder", "bank_name"}
    ),
    #: document_number deliberately reuses the same field name IdentityExtractor
    #: (ID_DOCUMENT) already produces, so app.rule_engine.rules.format_rules.
    #: FormatCnicRule (field_names=("document_number", "tax_reference_number"))
    #: validates it automatically -- see CnicFrontExtractor's docstring for why
    #: full_name and date_of_expiry are the other two fields real samples
    #: support, and why date_of_birth/date_of_issue/father_name were not
    #: attempted this pass.
    AnalyzedDocumentType.CNIC_FRONT: frozenset(
        {"document_number", "full_name", "date_of_expiry"}
    ),
    AnalyzedDocumentType.FORMAL_REQUEST_LETTER: frozenset(
        {
            "organization_name",
            "addressee",
            "subject",
            "date",
            "focal_person_name",
            "focal_person_designation",
        }
    ),
}

#: Fields whose absence forces the document into manual review regardless of
#: how the remaining checks scored. Scoped per document type for analysis
#: scoring — deliberately a separate set from `app.confidence.constants.
#: CRITICAL_FIELDS`, which is a flat global set gating human-review routing.
#: Keep both in sync by intent, not by identical membership.
CRITICAL_FIELDS: dict[AnalyzedDocumentType, frozenset[str]] = {
    AnalyzedDocumentType.BANK_STATEMENT: frozenset(
        {"account_number", "account_holder", "opening_balance", "closing_balance"}
    ),
    AnalyzedDocumentType.PAYSLIP: frozenset(
        {"employee_name", "gross_salary", "net_salary", "salary_month"}
    ),
    AnalyzedDocumentType.ID_DOCUMENT: frozenset(
        {"full_name", "date_of_birth", "document_number", "expiry_date"}
    ),
    AnalyzedDocumentType.TAX_DOCUMENT: frozenset(
        {"taxpayer_name", "tax_reference_number", "tax_year", "gross_income"}
    ),
    #: organization_name, account_number and transaction_charges are the
    #: fields docs/Master_Rules_Combined.md explicitly calls "required content"
    #: for this document (Section 7). account_number is additionally critical
    #: because the cross-document consistency rules can never pass without it.
    AnalyzedDocumentType.BILATERAL_AGREEMENT: frozenset(
        {"organization_name", "account_number", "transaction_charges"}
    ),
    #: account_holder/account_number/iban deliberately excluded -- real
    #: evidence (two independent departments) shows Authority Letters
    #: routinely omit bank details entirely, despite the master-rules spec
    #: implying they're required; treating them as critical would force every
    #: real application into manual review for a field that's rarely there.
    AnalyzedDocumentType.AUTHORITY_LETTER: frozenset(
        {"focal_person_name", "focal_person_designation", "organization_name"}
    ),
    AnalyzedDocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE: frozenset(
        {"account_holder", "account_number", "iban"}
    ),
    AnalyzedDocumentType.TRIPARTITE_AGREEMENT: frozenset(
        {"party_1link", "party_kpitb", "party_subbiller", "account_holder", "account_number"}
    ),
    #: digitization_intent_confirmed only. Master rules require BOTH this and
    #: revenue_services_listed (Section 10: "confirms... digitized" and
    #: "identifies and lists... services", neither hedged) -- unlike Authority
    #: Letter's bank fields, real evidence doesn't contradict either
    #: requirement; both are genuinely present in all three real samples
    #: reviewed. But the two differ sharply in extraction reliability.
    #: digitization_intent_confirmed is anchored on "KPITB('s) Fin(-)Tech
    #: Unit" -- a specific institutional name that must appear verbatim in
    #: any real onboarding-intent statement, near-templated the same way
    #: Authority Letter's core sentence was, so one regex generalizes with
    #: real confidence. revenue_services_listed's real-world phrasing has no
    #: such anchor -- the three samples express it as informal single-fee
    #: prose, a numbered list, and a categorized bullet breakdown
    #: respectively, three structurally incompatible forms. The regex here is
    #: anchored on those three known phrasings and will plausibly miss a
    #: fourth department's own wording -- a real extraction-reliability gap,
    #: not a documented absence, so treating it as critical would risk
    #: failing real, compliant BRDs whose services list just isn't phrased
    #: one of the three known ways.
    AnalyzedDocumentType.BUSINESS_REQUIREMENT_DOCUMENT: frozenset(
        {"digitization_intent_confirmed"}
    ),
    #: organization_name only, unchanged 2026-09-14 when the extractor was
    #: corrected to target the real "Application Form (In-Direct Customer)"
    #: instead of the Participation Memorandum this checklist slot no
    #: longer receives (see OneLinkLetterExtractor's docstring) -- the real
    #: form simply has no branch_code field of any kind, so there is
    #: nothing to mark critical or guess at. account_number_or_iban/
    #: account_holder/bank_name are newly extracted and reliable (8/8 real
    #: samples) but deliberately left non-critical here too: only
    #: organization_name was already an established, department-confirmed
    #: critical field, and expanding the critical set is a bigger,
    #: separate decision than fixing the extraction gap this pass targets.
    AnalyzedDocumentType.ONE_LINK_LETTER: frozenset({"organization_name"}),
    #: document_number only. This is the field docs/Master_Rules_Combined.md
    #: Section 12's core check ("CNIC follows the required format and is not
    #: expired... information is consistent") is actually anchored on, and
    #: it's the one field extracted reliably (format-anchored, position-
    #: independent) across all 3 real samples including the one with a
    #: scrambled label/value reading order. full_name and date_of_expiry are
    #: both deliberately non-critical -- see CnicFrontExtractor's docstring:
    #: full_name is reliable but only validated against a single real
    #: organization's samples; date_of_expiry only extracts cleanly on 2 of
    #: 3 samples (the label/value block shape breaks on the scrambled one),
    #: an honest extraction-reliability gap, not an absence.
    AnalyzedDocumentType.CNIC_FRONT: frozenset({"document_number"}),
    AnalyzedDocumentType.FORMAL_REQUEST_LETTER: frozenset(
        {"organization_name", "subject", "date"}
    ),
}

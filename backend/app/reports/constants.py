"""Configuration for the validation report module.

Centralizes the report version, the report-level overall status vocabulary and
its precedence, the mapping from stored validation categories onto the report's
business-rule groups and the deterministic recommendation table. The module
only aggregates what earlier stages persisted -- it never runs any rule or
detection -- so the constants here are pure presentation and derivation data.

The eight report groups are a reorganization of the eight Phase 10 rule
categories: ``field_presence`` folds into ``document_completeness`` and the
``visual`` category splits by rule id prefix into signature and stamp groups.
"""

from enum import StrEnum

from app.technical_validation.constants import TECHNICAL_VALIDATION_RULE_CATEGORY

#: Version of the report logic. Bumped whenever the aggregation, the status
#: derivation, the recommendation table or the HTML layout changes so a stored
#: or printed report can be traced to the exact generator that produced it.
REPORT_VERSION: str = "1.0.0"


# -- Overall report status ----------------------------------------------------
class ReportOverallStatus(StrEnum):
    """Overall verdict of a validation report.

    Values mirror the report specification: REJECTED is an external human
    decision (``applications.status == REJECTED``) that always wins; otherwise
    the verdict is derived strictly from the stored validation results.
    """

    REJECTED = "REJECTED"
    FAILED = "FAILED"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    APPROVED = "APPROVED"


#: Overall status precedence, strictest first. REJECTED is decided by the
#: application status, FAILED by any critical failure, MANUAL_REVIEW_REQUIRED by
#: any pending item; APPROVED is the fallback for everything else. Warnings are
#: informational and never block approval.
OVERALL_STATUS_PRECEDENCE: tuple[ReportOverallStatus, ...] = (
    ReportOverallStatus.REJECTED,
    ReportOverallStatus.FAILED,
    ReportOverallStatus.MANUAL_REVIEW_REQUIRED,
    ReportOverallStatus.APPROVED,
)


# -- Business rule groups -----------------------------------------------------
#: The eight report groups in fixed display order.
REPORT_GROUP_ORDER: tuple[str, ...] = (
    "Document Validation",
    "Format Validation",
    "Cross Document Validation",
    "Date Validation",
    "Signature Validation",
    "Stamp Validation",
    "Business Policy Validation",
    "Quality Validation",
)

#: Stored rule categories folded whole into a report group. The ``visual``
#: category is split by rule id prefix instead (see ``group_label``).
RULE_CATEGORY_GROUPS: dict[str, str] = {
    "document_completeness": "Document Validation",
    "field_presence": "Document Validation",
    "format": "Format Validation",
    "cross_document": "Cross Document Validation",
    "date": "Date Validation",
    "policy": "Business Policy Validation",
    "quality": "Quality Validation",
}

#: Prefixes that tell a ``visual`` category row's signature group from its
#: stamp group. Rule ids follow ``VIS_SIGNATURE_*`` / ``VIS_STAMP_*``.
VISUAL_SIGNATURE_PREFIX: str = "VIS_SIGNATURE_"
VISUAL_STAMP_PREFIX: str = "VIS_STAMP_"
GROUP_SIGNATURE: str = "Signature Validation"
GROUP_STAMP: str = "Stamp Validation"

#: Category of the technical validation rows stored in ``validation_results``.
TECHNICAL_VALIDATION_CATEGORY: str = TECHNICAL_VALIDATION_RULE_CATEGORY

#: Minimum per-field confidence below which a field is considered low
#: confidence and drives the correction recommendation. Matches the rule
#: engine's floor so both modules agree.
CONFIDENCE_FLOOR: float = 0.5

#: Substring that identifies a blur failure message from the technical
#: validation stage, used to surface the blurred-document recommendation.
BLUR_MESSAGE_MARKER: str = "Blur score"

#: Substring that identifies a "present more than once" document-presence
#: failure (see ``_DocumentPresenceRule.evaluate``), as distinct from a
#: genuinely-missing document -- both fail the same rule id with different
#: messages, and reviewers need different recommendations for each.
DUPLICATE_MESSAGE_MARKER: str = "is present more than once"

#: Document type carried by each document-presence rule, keyed by rule id.
DOCUMENT_TYPE_BY_RULE: dict[str, str] = {
    "DOC_TRIPARTITE_PRESENT": "TRIPARTITE_AGREEMENT",
    "DOC_BILATERAL_PRESENT": "BILATERAL_AGREEMENT",
    "DOC_AMC_PRESENT": "ACCOUNT_MAINTENANCE_CERTIFICATE",
    "DOC_ONE_LINK_PRESENT": "ONE_LINK_LETTER",
    "DOC_AUTHORITY_LETTER_PRESENT": "AUTHORITY_LETTER",
    "DOC_BRD_PRESENT": "BUSINESS_REQUIREMENT_DOCUMENT",
    "DOC_FORMAL_REQUEST_PRESENT": "FORMAL_REQUEST_LETTER",
}

#: Document type carried by each visual rule, keyed by rule id. The signature
#: group covers six document types and the stamp group five.
VISUAL_TYPE_BY_RULE: dict[str, str] = {
    "VIS_SIGNATURE_TRIPARTITE": "TRIPARTITE_AGREEMENT",
    "VIS_SIGNATURE_AMC": "ACCOUNT_MAINTENANCE_CERTIFICATE",
    "VIS_SIGNATURE_ONE_LINK": "ONE_LINK_LETTER",
    "VIS_SIGNATURE_AUTHORITY_LETTER": "AUTHORITY_LETTER",
    "VIS_SIGNATURE_BILATERAL": "BILATERAL_AGREEMENT",
    "VIS_SIGNATURE_FORMAL_REQUEST": "FORMAL_REQUEST_LETTER",
    "VIS_STAMP_TRIPARTITE": "TRIPARTITE_AGREEMENT",
    "VIS_STAMP_AMC": "ACCOUNT_MAINTENANCE_CERTIFICATE",
    "VIS_STAMP_ONE_LINK": "ONE_LINK_LETTER",
    "VIS_STAMP_AUTHORITY_LETTER": "AUTHORITY_LETTER",
    "VIS_STAMP_BILATERAL": "BILATERAL_AGREEMENT",
}


# -- Recommendation vocabulary -------------------------------------------------
#: Recommendation codes and their default message, in deterministic order.
#: Each entry is expanded at generation time (e.g. with the affected document
#: types) but the set and order never depend on the data.
RECOMMENDATION_TEMPLATES: dict[str, str] = {
    "MISSING_REQUIRED_DOCUMENT": "Ensure all required documents are uploaded: {details}.",
    "DUPLICATE_REQUIRED_DOCUMENT": (
        "Multiple copies were uploaded for: {details}. Confirm which copy is correct."
    ),
    "MISSING_SIGNATURE": "Review missing signatures on: {details}.",
    "MISSING_STAMP": "Review missing stamps on: {details}.",
    "IBAN_INCONSISTENCY": "Review failed IBAN consistency across documents.",
    "HOLDER_INCONSISTENCY": "Review account holder consistency across documents.",
    "ACCOUNT_NUMBER_INCONSISTENCY": "Review account number consistency across documents.",
    "PERIOD_INCONSISTENCY": "Review statement period consistency across documents.",
    "BALANCE_RECONCILIATION": "Review account balance reconciliation.",
    "VERIFY_BLURRED_DOCUMENTS": "Verify blurred documents.",
    "CORRECT_LOW_CONFIDENCE": "Correct low-confidence fields.",
    "REVIEW_DATES": "Review document dates and statement period.",
    "COMPLETE_PENDING_REVIEW": "Complete the manual review of pending items.",
    "NO_ACTION_REQUIRED": "No corrective action required.",
}

#: Deterministic order in which applicable recommendations are listed.
RECOMMENDATION_ORDER: tuple[str, ...] = (
    "MISSING_REQUIRED_DOCUMENT",
    "DUPLICATE_REQUIRED_DOCUMENT",
    "MISSING_SIGNATURE",
    "MISSING_STAMP",
    "IBAN_INCONSISTENCY",
    "HOLDER_INCONSISTENCY",
    "ACCOUNT_NUMBER_INCONSISTENCY",
    "PERIOD_INCONSISTENCY",
    "BALANCE_RECONCILIATION",
    "VERIFY_BLURRED_DOCUMENTS",
    "CORRECT_LOW_CONFIDENCE",
    "REVIEW_DATES",
    "COMPLETE_PENDING_REVIEW",
    "NO_ACTION_REQUIRED",
)

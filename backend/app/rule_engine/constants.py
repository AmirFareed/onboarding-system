"""Configuration for the business rule engine module.

Centralizes the rule categories, the overall status vocabulary, the severity
mapping, the audit action and the application-level configuration sets the
rules evaluate against. Rules are deliberately driven by data in this module:
changing a required document type, a threshold or a tolerated deviation never
requires touching a rule implementation.

The module ships a complete, deterministic ruleset (``RULE_CATEGORIES``) that
extends the Phase 4 completeness classification with the Phase 10 business
rule requirements. Where the two differ -- the rule engine treats the bilateral
agreement as required -- the rule-engine configuration wins for this module and
the difference is documented in ``docs/rule_engine.md``.
"""

from enum import StrEnum

from app.database.models.enums import DocumentType, Severity, ValidationStatus

#: Version of the rule engine logic. Bumped whenever a rule or the configuration
#: changes so stored validation rows can be traced to the exact ruleset that
#: produced them.
RULE_ENGINE_VERSION: str = "1.0.0"

#: Category identifiers keyed to their human-readable labels. Every rule
#: carries one of these categories and every persisted rule-engine row is told
#: apart from the technical validation rows by membership of this set.
RULE_CATEGORIES: dict[str, str] = {
    "document_completeness": "Document completeness",
    "field_presence": "Required field presence",
    "format": "Field format",
    "cross_document": "Cross-document consistency",
    "date": "Date and period",
    "visual": "Visual verification",
    "policy": "Policy compliance",
    "quality": "Data quality",
}

#: Categories that never block the run: nothing in the engine is optional at
#: runtime, but the set is kept here so callers can reason about the module's
#: full vocabulary without importing rules.
RULE_CATEGORY_KEYS: frozenset[str] = frozenset(RULE_CATEGORIES)

#: Severity derived from a rule's status when the result is persisted. The
#: mapping matches the technical validation module's convention so both
#: producers of ``validation_results`` rows agree on severity semantics.
SEVERITY_PASS: Severity = Severity.INFO
SEVERITY_WARNING: Severity = Severity.WARNING
SEVERITY_FAIL: Severity = Severity.ERROR


class RuleEngineStatus(StrEnum):
    """Application-level outcome of a business rule validation run.

    The value is a plain ``ValidationStatus``; this enum only names the four
    outcomes in one place for documentation and tests.
    """

    PASS = ValidationStatus.PASS.value
    FAIL = ValidationStatus.FAIL.value
    WARNING = ValidationStatus.WARNING.value
    PENDING_MANUAL_REVIEW = ValidationStatus.PENDING_MANUAL_REVIEW.value


#: Overall status precedence, strictest first. Any failed rule fails the run;
#: otherwise any pending rule holds the run; otherwise any warning downgrades
#: the run; otherwise every rule passed.
OVERALL_STATUS_PRECEDENCE: tuple[ValidationStatus, ...] = (
    ValidationStatus.FAIL,
    ValidationStatus.PENDING_MANUAL_REVIEW,
    ValidationStatus.WARNING,
    ValidationStatus.PASS,
)


# -- Document configuration ---------------------------------------------------
#: Document types the rule engine treats as required, each exactly once. This
#: extends the Phase 4 required set with the bilateral agreement.
#:
#: SCHEDULE_OF_CHARGES deliberately removed 2026-08-22, same reasoning as
#: completeness/constants.py's REQUIRED_DOCUMENT_TYPES -- see there and
#: CONTEXT.md for the decision record. Corresponding rule (DocumentScheduleRule,
#: rule_engine/rules/document_rules.py) is unregistered, not deleted -- see
#: rule_engine/rules/__init__.py.
#:
#: CNIC_FRONT added 2026-08-23, same reasoning and same reconciliation as
#: completeness/constants.py's REQUIRED_DOCUMENT_TYPES -- see there and
#: CONTEXT.md. CNIC_BACK deliberately not added (zero real samples).
REQUIRED_DOCUMENT_TYPES: tuple[DocumentType, ...] = (
    DocumentType.TRIPARTITE_AGREEMENT,
    DocumentType.BILATERAL_AGREEMENT,
    DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    DocumentType.ONE_LINK_LETTER,
    DocumentType.AUTHORITY_LETTER,
    DocumentType.BUSINESS_REQUIREMENT_DOCUMENT,
    DocumentType.FORMAL_REQUEST_LETTER,
    DocumentType.CNIC_FRONT,
)


# -- Visual detection configuration -------------------------------------------
#: Detection kinds the visual rules consume from the visual detection results.
SIGNATURE_DETECTION: str = "SIGNATURE"
STAMP_DETECTION: str = "STAMP"

#: Document types that must carry a signature, per the Phase 10 checklist.
SIGNATURE_DOCUMENT_TYPES: tuple[DocumentType, ...] = (
    DocumentType.TRIPARTITE_AGREEMENT,
    DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    DocumentType.ONE_LINK_LETTER,
    DocumentType.AUTHORITY_LETTER,
    DocumentType.BILATERAL_AGREEMENT,
    DocumentType.FORMAL_REQUEST_LETTER,
)

#: Document types that must carry a stamp.
STAMP_DOCUMENT_TYPES: tuple[DocumentType, ...] = (
    DocumentType.TRIPARTITE_AGREEMENT,
    DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    DocumentType.ONE_LINK_LETTER,
    DocumentType.AUTHORITY_LETTER,
    DocumentType.BILATERAL_AGREEMENT,
)


# -- Quality thresholds -------------------------------------------------------
#: Minimum per-field confidence before the quality floor rule passes.
CONFIDENCE_FLOOR: float = 0.5

#: Tolerance (absolute) used by the balance reconciliation rule. A difference
#: of up to this many units is considered a rounding residue.
RECONCILIATION_TOLERANCE: float = 0.01


# -- Policy vocabulary --------------------------------------------------------
#: Account holder values that are not a real named entity (placeholders the
#: policy rule rejects).
PLACEHOLDER_ACCOUNT_HOLDERS: frozenset[str] = frozenset(
    {"NOT PROVIDED", "N/A", "NA", "NONE", "XXXX", "UNKNOWN", "TBD"}
)

#: A statement period older than this many days fails the recency rule with a
#: warning (the account may still be valid but the statement is stale).
STATEMENT_MAX_AGE_DAYS: int = 365

#: Oldest plausible birth year accepted by the date-of-birth sanity rule.
MIN_BIRTH_YEAR: int = 1900

#: Format rules are not executed at all when no normalized value of their
#: fields exists; they report a warning that there is nothing to validate.
NOTHING_TO_VALIDATE: str = "No values of the required fields are present to validate"


# -- Audit action identifier --------------------------------------------------
ACTION_VALIDATED: str = "rule_engine.validated"

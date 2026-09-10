"""Configuration for the confidence scoring module.

Centralizes the evaluation statuses, the per-field verification statuses, the
critical-field classification, the confidence source identifiers and the audit
action names. The threshold and the source weights themselves live in
``app.core.config.Settings`` so they can be tuned without touching code; this
module only pins the vocabulary the rest of the module shares.
"""

from enum import StrEnum

#: Version of the confidence/scoring logic. Bumped whenever the scoring rules
#: change so stored field rows can be traced to the exact logic that produced
#: them.
CONFIDENCE_VERSION: str = "1.0.0"


class EvaluationStatus(StrEnum):
    """Application-level outcome of a confidence evaluation."""

    READY_FOR_NORMALIZATION = "READY_FOR_NORMALIZATION"
    REQUIRES_HUMAN_REVIEW = "REQUIRES_HUMAN_REVIEW"
    PROCESSING_HALTED = "PROCESSING_HALTED"


class FieldVerificationStatus(StrEnum):
    """Per-field verification state written to the extracted field row."""

    AUTO_VERIFIED = "AUTO_VERIFIED"
    PENDING_REVIEW = "PENDING_REVIEW"
    VERIFIED = "VERIFIED"
    CORRECTED = "CORRECTED"
    CANNOT_VERIFY = "CANNOT_VERIFY"


# -- Confidence sources -------------------------------------------------------
#: Identifiers must match the keys of ``Settings.confidence_weights`` so the
#: configured weights can be looked up directly.
SOURCE_REGEX: str = "regex"
SOURCE_TEMPLATE: str = "template"
SOURCE_OCR: str = "ocr"
SOURCE_AI: str = "ai"

#: Every source the module knows about; used to validate the configured weights.
CONFIDENCE_SOURCES: frozenset[str] = frozenset(
    {SOURCE_REGEX, SOURCE_TEMPLATE, SOURCE_OCR, SOURCE_AI}
)

#: Confidence a regex source contributes when the value validated successfully.
REGEX_SCORE_VALID: float = 1.0
#: Confidence when the value matched a pattern but failed its validation.
REGEX_SCORE_INVALID: float = 0.25
#: Confidence when the field is missing entirely.
REGEX_SCORE_MISSING: float = 0.0

#: Template coverage below which the reason is annotated as a template problem.
TEMPLATE_MISMATCH_COVERAGE: float = 0.5
#: OCR confidence below which the reason is annotated as low OCR confidence.
LOW_OCR_CONFIDENCE: float = 0.5


# -- Critical fields ----------------------------------------------------------
#: Fields whose low confidence forces human review regardless of how the rest of
#: the application scored (IBAN, account number, account title, bank name, CNIC
#: and the date fields, mapped onto the extractor's field names). Deliberately
#: a separate set from `app.document_analysis.constants.CRITICAL_FIELDS`, which
#: is scoped per document type for analysis scoring, not review gating.
CRITICAL_FIELDS: frozenset[str] = frozenset(
    {
        "iban",
        "account_number",
        "account_holder",
        "bank_name",
        "document_number",
        "date_of_birth",
        "expiry_date",
        "issue_date",
        "payment_date",
        "statement_period",
        "salary_month",
    }
)


def is_critical(field_name: str) -> bool:
    """Return whether ``field_name`` is a critical field.

    Args:
        field_name: Machine-readable name of the field.

    Returns:
        ``True`` when a low confidence in this field must force human review.
    """
    return field_name in CRITICAL_FIELDS


# -- Confidence reasons -------------------------------------------------------
#: Human-readable explanations for a field's confidence score. Reasons are
#: combined with ``; `` when several contributors apply.
REASON_VALID: str = "Validated by extraction"
REASON_REGEX_MISMATCH: str = "Regex pattern mismatch"
REASON_MISSING_CONTEXT: str = "Missing expected context"
REASON_TEMPLATE_MISMATCH: str = "Template mismatch"
REASON_LOW_OCR: str = "Low OCR confidence"
REASON_AI_DISAGREEMENT: str = "AI disagreement"


# -- Audit action identifiers -------------------------------------------------
ACTION_EVALUATED: str = "confidence.evaluated"
ACTION_VERIFIED: str = "confidence.field_verified"
ACTION_CORRECTED: str = "confidence.field_corrected"
ACTION_CANNOT_VERIFY: str = "confidence.field_cannot_verify"
ACTION_REVIEWED: str = "confidence.reviewed"
ACTION_HALTED: str = "confidence.processing_halted"

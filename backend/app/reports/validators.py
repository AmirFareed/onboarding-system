"""Pure derivation helpers for the validation report module.

Everything here is a deterministic function of its inputs, so the overall
status, the category grouping and the recommendation list can be unit-tested
without a database. The service computes the raw findings from stored data and
hands them to these helpers; no validation logic ever lives here.
"""

from __future__ import annotations

from app.database.models.enums import ApplicationStatus
from app.reports.constants import (
    GROUP_SIGNATURE,
    GROUP_STAMP,
    RECOMMENDATION_ORDER,
    RECOMMENDATION_TEMPLATES,
    RULE_CATEGORY_GROUPS,
    VISUAL_SIGNATURE_PREFIX,
    VISUAL_STAMP_PREFIX,
    ReportOverallStatus,
)


def group_label(category: str, rule_id: str) -> str:
    """Return the report group a validation row belongs to.

    Most stored rule categories map whole onto a report group. The ``visual``
    category splits by rule id prefix into a signature group and a stamp group,
    and ``field_presence`` rows fold into the document validation group.

    Args:
        category: Stored ``rule_category`` of the validation row.
        rule_id: Stored ``rule_id`` of the validation row.

    Returns:
        The report group label the row is summarized under.
    """
    if category == "visual":
        if rule_id.startswith(VISUAL_SIGNATURE_PREFIX):
            return GROUP_SIGNATURE
        if rule_id.startswith(VISUAL_STAMP_PREFIX):
            return GROUP_STAMP
    return RULE_CATEGORY_GROUPS.get(category, category)


def derive_overall_status(
    *,
    application_status: str | None,
    has_failure: bool,
    has_pending_review: bool,
) -> ReportOverallStatus:
    """Derive the report's overall status from the stored evidence.

    A rejected application status is an external human decision and always
    wins. Otherwise any critical failure fails the report, any pending manual
    review item holds it, and the report is approved in every other case --
    warnings are informational and never block approval.

    Args:
        application_status: Current ``applications.status`` value.
        has_failure: Whether any stored validation row failed.
        has_pending_review: Whether any stored rule row awaits manual review.

    Returns:
        The derived overall status.
    """
    if application_status == ApplicationStatus.REJECTED.value:
        return ReportOverallStatus.REJECTED
    if has_failure:
        return ReportOverallStatus.FAILED
    if has_pending_review:
        return ReportOverallStatus.MANUAL_REVIEW_REQUIRED
    return ReportOverallStatus.APPROVED


def build_recommendations(findings: dict) -> list[dict[str, str]]:
    """Build the deterministic, ordered recommendation list.

    Args:
        findings: Aggregated findings computed by the service, with boolean or
            list flags for every recommendation trigger (missing documents,
            missing signatures/stamps, consistency failures, balance
            reconciliation, blurred documents, low-confidence fields, date
            anomalies, pending review, approval).

    Returns:
        The applicable recommendations as ``{"code": ..., "message": ...}``
        dicts in fixed order, ending with ``NO_ACTION_REQUIRED`` only when no
        other recommendation applies.
    """
    def _present(code: str) -> bool:
        flag = _FLAGS[code]
        return bool(findings.get(flag))

    _FLAGS: dict[str, str] = {
        "MISSING_REQUIRED_DOCUMENT": "missing_document_types",
        "DUPLICATE_REQUIRED_DOCUMENT": "duplicate_document_types",
        "MISSING_SIGNATURE": "missing_signature_documents",
        "MISSING_STAMP": "missing_stamp_documents",
        "IBAN_INCONSISTENCY": "iban_inconsistent",
        "HOLDER_INCONSISTENCY": "holder_inconsistent",
        "ACCOUNT_NUMBER_INCONSISTENCY": "account_number_inconsistent",
        "PERIOD_INCONSISTENCY": "period_inconsistent",
        "BALANCE_RECONCILIATION": "reconciliation_failed",
        "VERIFY_BLURRED_DOCUMENTS": "blurred_documents",
        "CORRECT_LOW_CONFIDENCE": "low_confidence",
        "REVIEW_DATES": "date_failures",
        "COMPLETE_PENDING_REVIEW": "pending_review",
    }

    recommendations: list[dict[str, str]] = []
    for code in RECOMMENDATION_ORDER:
        if code == "NO_ACTION_REQUIRED":
            if not recommendations and findings.get("approved"):
                recommendations.append(
                    {"code": code, "message": RECOMMENDATION_TEMPLATES[code]}
                )
            continue
        if not _present(code):
            continue
        message = RECOMMENDATION_TEMPLATES[code]
        if "{details}" in message:
            details = findings.get(_FLAGS[code])
            if isinstance(details, (list, tuple)):
                message = message.format(details=", ".join(str(item) for item in details))
        recommendations.append({"code": code, "message": message})
    return recommendations

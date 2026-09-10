"""Tests for the validation report API.

End-to-end tests build complete applications through the real API -- upload,
processing, analysis, confidence evaluation, normalization and business rule
validation -- and then check the read-only report endpoints. The report must
never run rules or detections itself and must never write to the database.
"""

from app.database.connection import SessionLocal
from app.database.models.enums import ApplicationStatus, DocumentType
from app.database.repositories.application_repository import ApplicationRepository
from app.reports.constants import REPORT_GROUP_ORDER, VISUAL_TYPE_BY_RULE
from app.rule_engine.constants import REQUIRED_DOCUMENT_TYPES
from tests.test_confidence_api import evaluate
from tests.test_document_analysis_api import (
    AUTHORITY_LETTER_TEXT,
    BANK_STATEMENT_TEXT,
    ONE_LINK_LETTER_TEXT,
    add_digital_pdf,
    analyze_documents,
    run_processing,
)
from tests.test_formal_request_letter_extractor import SYNTHETIC_FORMAL_REQUEST_LETTER
from tests.test_normalization_api import normalize
from tests.test_rule_engine_api import (
    ACCOUNT_MAINTENANCE_CERTIFICATE_CROSS_DOC_TEXT,
    BILATERAL_STATEMENT_TEXT,
    TRIPARTITE_AGREEMENT_CROSS_DOC_TEXT,
    add_visual_detection,
    document_ids_by_type,
    validate,
)
from tests.test_technical_validation_api import create_application

API = "/api/v1"

REPORT_URL = "/validation-report"
HTML_URL = "/validation-report/html"
SUMMARY_URL = "/validation-summary"

REPORT_VERSION = "1.0.0"

#: Synthetic (fabricated, non-real) fixture giving BUSINESS_REQUIREMENT_DOCUMENT
#: its own real-shaped text, same as BILATERAL_AGREEMENT/AUTHORITY_LETTER/AMC/
#: TRIPARTITE_AGREEMENT above -- BRD now has a real extractor too (routed via
#: document_analysis.services._CHECKLIST_TYPE_MAP), so feeding it BANK_STATEMENT_TEXT
#: (the generic fallback for "no extractor yet" types) would extract nothing and
#: drag the fleet-wide mean confidence down for a reason unrelated to what this
#: test is actually checking.
BUSINESS_REQUIREMENT_DOCUMENT_TEXT = """BUSINESS REQUIREMENT DOCUMENT
The Sample Development Authority is a government organization responsible for
regional development. The major sources of income of this Authority are the
prescribed fees collected at each facility office.
This office intends to go towards Digital Payments via KPITB's FinTech Unit.
"""

#: Per-group rule totals expected from the 54-rule ruleset (57 implemented,
#: CrossPeriodRule, CrossBranchCodeRule and DocumentScheduleRule unregistered
#: -- see rule_engine/rules/__init__.py -- plus FieldStatementPeriodPresenceRule
#: and FieldBalancesPresenceRule removed outright, same file).
EXPECTED_GROUP_TOTALS = {
    "Document Validation": 18,
    "Format Validation": 6,
    # CrossPeriodRule is unregistered (see rule_engine/rules/__init__.py) --
    # 3 of the 4 implemented cross-document rules are active.
    "Cross Document Validation": 3,
    "Date Validation": 8,
    "Signature Validation": 6,
    "Stamp Validation": 5,
    "Business Policy Validation": 4,
    "Quality Validation": 4,
}


def build_full_application(client, storage_root, *, with_detections: bool) -> int:
    """Build an application carrying all eight required documents, analysed.

    SCHEDULE_OF_CHARGES deliberately excluded: no longer a required document
    type (see rule_engine/constants.py's REQUIRED_DOCUMENT_TYPES and
    CONTEXT.md) -- this fixture derives its document set directly from that
    constant.

    CNIC_FRONT added 2026-08-23 (see rule_engine/constants.py and
    completeness/constants.py) -- back up to eight documents. It has no
    dedicated branch below and falls to the generic BANK_STATEMENT_TEXT
    fallback like any other required type without special-cased text, same
    as the rest of this docstring already describes.

    BILATERAL_AGREEMENT, AUTHORITY_LETTER, ACCOUNT_MAINTENANCE_CERTIFICATE,
    TRIPARTITE_AGREEMENT, BUSINESS_REQUIREMENT_DOCUMENT, ONE_LINK_LETTER and
    FORMAL_REQUEST_LETTER each get their own real-shaped text, since all
    seven now have real extractors (Phase 1 + Track B). FORMAL_REQUEST_LETTER
    reuses the synthetic fixture from test_formal_request_letter_extractor.py
    rather than duplicating it -- it carries a real Subject: line, so
    FLD_FORMAL_REQUEST_SUBJECT_PRESENT passes here instead of failing on the
    generic bank-statement fallback that has none. The AMC, Bilateral and
    Tripartite texts
    carry the same account_holder/account_number values, so the
    cross-document consistency rules still agree. AUTHORITY_LETTER's
    CRITICAL_FIELDS are all non-bank fields (focal_person_name/designation/
    organization_name -- see AuthorityLetterExtractor's docstring), so no
    cross-document account value needs to line up. Every other required type
    (including CNIC_FRONT, despite having its own real extractor --
    CnicFrontExtractor -- elsewhere) keeps using BANK_STATEMENT_TEXT via the
    generic keyword-based classifier here, unaffected by either change.
    """
    application_id = create_application(client)
    for document_type in REQUIRED_DOCUMENT_TYPES:
        if document_type is DocumentType.BILATERAL_AGREEMENT:
            text = BILATERAL_STATEMENT_TEXT
        elif document_type is DocumentType.AUTHORITY_LETTER:
            text = AUTHORITY_LETTER_TEXT
        elif document_type is DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE:
            text = ACCOUNT_MAINTENANCE_CERTIFICATE_CROSS_DOC_TEXT
        elif document_type is DocumentType.TRIPARTITE_AGREEMENT:
            text = TRIPARTITE_AGREEMENT_CROSS_DOC_TEXT
        elif document_type is DocumentType.BUSINESS_REQUIREMENT_DOCUMENT:
            text = BUSINESS_REQUIREMENT_DOCUMENT_TEXT
        elif document_type is DocumentType.ONE_LINK_LETTER:
            text = ONE_LINK_LETTER_TEXT
        elif document_type is DocumentType.FORMAL_REQUEST_LETTER:
            text = SYNTHETIC_FORMAL_REQUEST_LETTER
        else:
            text = BANK_STATEMENT_TEXT
        add_digital_pdf(
            storage_root,
            application_id,
            text,
            document_type=document_type,
            filename=f"{document_type.value}.pdf",
        )
    run_processing(client, application_id)
    analyze_documents(client, application_id)
    evaluate(client, application_id)
    normalize(client, application_id)
    validate(client, application_id)
    if with_detections:
        document_ids = document_ids_by_type(application_id)
        for rule_id, document_type in VISUAL_TYPE_BY_RULE.items():
            add_visual_detection(
                document_id=document_ids[document_type],
                detection_type=rule_id.split("_")[1],
                is_present=True,
                confidence=1.0,
            )
        validate(client, application_id)
    return application_id


def build_single_statement_application(client, storage_root) -> int:
    """Build a minimal analysed application with a real AMC document."""
    application_id = create_application(client)
    add_digital_pdf(
        storage_root,
        application_id,
        ACCOUNT_MAINTENANCE_CERTIFICATE_CROSS_DOC_TEXT,
        document_type=DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    run_processing(client, application_id)
    analyze_documents(client, application_id)
    evaluate(client, application_id)
    normalize(client, application_id)
    validate(client, application_id)
    return application_id


def get_report(client, application_id: int, *, url: str = REPORT_URL):
    """GET a report endpoint and return the response."""
    return client.get(f"{API}/applications/{application_id}{url}")


# --- Overall statuses --------------------------------------------------------


def test_report_approved_application(authenticated_client, storage_root):
    application_id = build_full_application(authenticated_client, storage_root, with_detections=True)

    response = get_report(authenticated_client, application_id)

    assert response.status_code == 200
    report = response.json()
    assert report["application_id"] == application_id
    assert report["report_version"] == REPORT_VERSION
    assert report["overall_status"] == "APPROVED"
    assert report["application"]["status"] == "SUBMITTED"
    assert report["application"]["created_by"] == "Test Operator"
    assert len(report["document_summary"]) == 8

    summary = report["rule_summary"]
    assert summary["total"] == 54
    assert summary["failed"] == 0
    assert summary["pending_manual_review"] == 0
    assert summary["passed"] + summary["warnings"] == 54

    assert [
        group["category"] for group in summary["by_category"]
    ] == list(REPORT_GROUP_ORDER)
    for group in summary["by_category"]:
        assert group["total"] == EXPECTED_GROUP_TOTALS[group["category"]]

    visual = report["visual_detection_summary"]
    assert visual["documents_checked"] == 6
    assert visual["signature_detected"] == 6
    assert visual["stamp_detected"] == 5
    assert visual["signature_missing"] == 0
    assert visual["stamp_missing"] == 0
    assert visual["average_confidence"] == 1.0

    extraction = report["extraction_summary"]
    assert extraction["total_fields"] > 0
    assert extraction["auto_verified"] == extraction["total_fields"]
    # AUTHORITY_LETTER's EXPECTED_FIELDS includes account_holder/account_number/
    # iban, which real Authority Letters never carry (see AuthorityLetterExtractor's
    # docstring) -- its template coverage is honestly 0.5, pulling the fleet-wide
    # mean confidence just under 1.0. Value recalibrated 2026-08-16: previously
    # BUSINESS_REQUIREMENT_DOCUMENT fell through to BANK_STATEMENT_TEXT (no real
    # extractor existed for it yet), contributing as a fully-covered 9-field bank
    # statement. It now has its own real extractor (see
    # BUSINESS_REQUIREMENT_DOCUMENT_TEXT above) and is fully covered on its own
    # narrower 2-field template (confirmed via extract_fields against the exact
    # PDF-probed text, 0 missing) -- the fleet-wide mean shifted because the
    # field-count composition of the fleet changed, not because of a new gap.
    # Recalibrated again 2026-08-17: ONE_LINK_LETTER now has its own real
    # extractor too (see ONE_LINK_LETTER_TEXT above) instead of falling
    # through to BANK_STATEMENT_TEXT -- fully covered on its own 2-field
    # template (organization_name + branch_code, 0 missing), same shift
    # pattern as BUSINESS_REQUIREMENT_DOCUMENT above.
    # Recalibrated again 2026-08-19 (department decision, see CONTEXT.md):
    # branch_code dropped from OneLinkLetterExtractor's field list, so its
    # template is now organization_name alone (still 0 missing, still fully
    # covered) -- verified via the actual test run, not derived by hand.
    # Recalibrated again 2026-08-19: FORMAL_REQUEST_LETTER now has its own
    # real-shaped text (SYNTHETIC_FORMAL_REQUEST_LETTER) instead of falling
    # through to BANK_STATEMENT_TEXT, so it now contributes its own real
    # extracted-field confidence scores to the fleet-wide mean instead of a
    # fully-covered 9-field bank statement's -- same shift pattern as the
    # entries above, verified via the actual test run.
    # Recalibrated again 2026-08-22: BILATERAL_STATEMENT_TEXT (test_rule_engine_api.py)
    # was rewritten to the real Bilateral Agreement template shape (see
    # BilateralAgreementExtractor's docstring) -- it no longer carries a
    # labeled "Account Title" at all, since no real Bilateral Agreement sample
    # has one, so its own template coverage is honestly lower than the old
    # synthetic fixture's -- same shift pattern as the entries above, verified
    # via the actual test run.
    # Recalibrated again 2026-08-22 (second time same day): SCHEDULE_OF_CHARGES
    # removed from REQUIRED_DOCUMENT_TYPES (see CONTEXT.md) -- build_full_application
    # now builds seven documents instead of eight, dropping the fully-covered
    # 9-field BANK_STATEMENT_TEXT fallback that type used to contribute --
    # fewer, honestly-lower-scoring real extractors now make up the fleet
    # mean instead of one artificially-easy synthetic filler, verified via
    # the actual test run.
    # CNIC_FRONT added 2026-08-23 (see rule_engine/constants.py) -- back up to
    # eight documents. CNIC_FRONT has no dedicated text branch above, so it
    # falls to the same fully-covered BANK_STATEMENT_TEXT fallback the removed
    # SCHEDULE_OF_CHARGES type used to use. Confirmed via the actual test run
    # (not assumed) that the fleet-wide mean lands on this exact same value --
    # a genuine coincidence, not a derived one.
    assert extraction["overall_confidence"] == 0.9587

    assert [item["code"] for item in report["recommendations"]] == [
        "NO_ACTION_REQUIRED"
    ]


def test_report_failed_application(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)

    report = get_report(authenticated_client, application_id).json()

    assert report["overall_status"] == "FAILED"
    summary = report["rule_summary"]
    assert summary["total"] == 54
    assert summary["failed"] > 0
    # Only the present AMC document's visual rules await detection; the rest
    # fail because their documents are missing.
    assert summary["pending_manual_review"] == 2
    assert len(summary["by_category"]) == 8

    codes = [item["code"] for item in report["recommendations"]]
    assert "MISSING_REQUIRED_DOCUMENT" in codes
    assert "COMPLETE_PENDING_REVIEW" in codes
    assert "NO_ACTION_REQUIRED" not in codes

    visual = report["visual_detection_summary"]
    assert visual["documents_checked"] == 0
    assert visual["signature_detected"] == 0
    assert visual["stamp_missing"] == 0


def test_report_duplicate_document_recommends_duplicate_not_missing(
    authenticated_client, storage_root
):
    """A document present more than once must not be reported as missing.

    Regression test for the 2026-08-25 finding: application 20315's report
    told a reviewer to "ensure ONE_LINK_LETTER is uploaded" while 3 real
    copies were already present, because DOC_ONE_LINK_PRESENT fails
    identically for "zero present" and "more than one present" and both
    landed in the same missing_document_types bucket. The rule's PASS/FAIL
    semantics are unchanged here (a duplicate still fails the rule) -- only
    which recommendation a reviewer sees for that failure.
    """
    application_id = build_full_application(
        authenticated_client, storage_root, with_detections=False
    )
    add_digital_pdf(
        storage_root,
        application_id,
        ONE_LINK_LETTER_TEXT,
        document_type=DocumentType.ONE_LINK_LETTER,
        filename="one_link_letter_copy2.pdf",
    )
    run_processing(authenticated_client, application_id)
    analyze_documents(authenticated_client, application_id)
    evaluate(authenticated_client, application_id)
    normalize(authenticated_client, application_id)
    validate(authenticated_client, application_id)

    report = get_report(authenticated_client, application_id).json()

    codes = [item["code"] for item in report["recommendations"]]
    assert "DUPLICATE_REQUIRED_DOCUMENT" in codes
    duplicate_message = next(
        item["message"]
        for item in report["recommendations"]
        if item["code"] == "DUPLICATE_REQUIRED_DOCUMENT"
    )
    assert "ONE_LINK_LETTER" in duplicate_message

    if "MISSING_REQUIRED_DOCUMENT" in codes:
        missing_message = next(
            item["message"]
            for item in report["recommendations"]
            if item["code"] == "MISSING_REQUIRED_DOCUMENT"
        )
        assert "ONE_LINK_LETTER" not in missing_message


def test_report_manual_review_required_application(authenticated_client, storage_root):
    application_id = build_full_application(
        authenticated_client, storage_root, with_detections=False
    )

    report = get_report(authenticated_client, application_id).json()

    assert report["overall_status"] == "MANUAL_REVIEW_REQUIRED"
    summary = report["rule_summary"]
    assert summary["failed"] == 0
    assert summary["pending_manual_review"] == 11
    codes = [item["code"] for item in report["recommendations"]]
    assert "COMPLETE_PENDING_REVIEW" in codes
    assert "NO_ACTION_REQUIRED" not in codes


def test_report_rejected_application_overrides_status(authenticated_client, storage_root):
    application_id = build_full_application(authenticated_client, storage_root, with_detections=True)
    db = SessionLocal()
    try:
        repository = ApplicationRepository(db)
        application = repository.get_by_id(application_id)
        repository.update(application, status=ApplicationStatus.REJECTED)
    finally:
        db.close()

    report = get_report(authenticated_client, application_id).json()

    assert report["overall_status"] == "REJECTED"
    assert report["application"]["status"] == "REJECTED"


# --- Report variants ---------------------------------------------------------


def test_report_summary_condensed(authenticated_client, storage_root):
    application_id = build_full_application(authenticated_client, storage_root, with_detections=True)

    response = get_report(authenticated_client, application_id, url=SUMMARY_URL)

    assert response.status_code == 200
    summary = response.json()
    assert summary["application_id"] == application_id
    assert summary["report_version"] == REPORT_VERSION
    assert summary["overall_status"] == "APPROVED"
    assert summary["application_status"] == "SUBMITTED"
    assert summary["document_count"] == 8
    assert summary["rule_total"] == 54
    assert summary["rule_passed"] + summary["rule_warnings"] == 54
    assert summary["rule_failed"] == 0
    assert summary["rule_pending_review"] == 0
    assert summary["field_count"] > 0
    # See test_report_approved_application's overall_confidence comment.
    assert summary["overall_confidence"] == 0.9587
    assert summary["recommendation_count"] == 1


def test_report_html_is_printable(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)

    response = get_report(authenticated_client, application_id, url=HTML_URL)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    html = response.text
    assert "Validation Report" in html
    assert "status-banner" in html
    assert str(application_id) in html
    assert "Executive Summary" in html
    assert "Documents" in html
    assert "What You Need to Do" in html


def test_report_is_idempotent(authenticated_client, storage_root):
    application_id = build_single_statement_application(authenticated_client, storage_root)

    first = get_report(authenticated_client, application_id).json()
    second = get_report(authenticated_client, application_id).json()

    first.pop("generated_at")
    second.pop("generated_at")
    assert first == second


# --- Error paths -------------------------------------------------------------


def test_report_with_no_validation_results_is_not_yet_reviewed(authenticated_client, storage_root):
    """An application with zero stored rule rows must render as "not yet
    reviewed", never as a silent 422 (the report was previously blocked
    entirely until business validation ran, which is exactly backwards for
    an application that's still missing required documents -- the report's
    whole point is to show that) and never as APPROVED (nothing has
    actually been checked yet)."""
    application_id = create_application(authenticated_client)

    for url in (REPORT_URL, SUMMARY_URL):
        response = get_report(authenticated_client, application_id, url=url)
        assert response.status_code == 200, response.text
        assert response.json()["overall_status"] == "MANUAL_REVIEW_REQUIRED"

    html_response = get_report(authenticated_client, application_id, url=HTML_URL)
    assert html_response.status_code == 200, html_response.text
    assert "Under Review" in html_response.text


def test_report_technical_results_alone_is_not_yet_reviewed(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    add_digital_pdf(storage_root, application_id, BANK_STATEMENT_TEXT)
    run_processing(authenticated_client, application_id)

    response = get_report(authenticated_client, application_id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["overall_status"] == "MANUAL_REVIEW_REQUIRED"
    assert body["rule_summary"]["total"] == 0
    assert len(body["document_summary"]) == 1


def test_report_endpoints_application_not_found(authenticated_client):
    for url in (REPORT_URL, HTML_URL, SUMMARY_URL):
        response = get_report(authenticated_client, 999999, url=url)
        assert response.status_code == 404
        assert response.json()["detail"] == "Application not found"



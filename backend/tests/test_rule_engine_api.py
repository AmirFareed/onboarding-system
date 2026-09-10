"""Tests for the business rule engine API and end-to-end validation flow.

End-to-end tests exercise the full chain through the real API: upload, document
processing, analysis, confidence evaluation, normalization and then business
rule validation. Visual detection outcomes are injected directly through the
repository, since the detection pipeline itself is external.
"""

from sqlalchemy import text

from app.database.connection import SessionLocal
from app.database.models.enums import DocumentType
from app.database.repositories.visual_detection_repository import (
    VisualDetectionRepository,
)
from tests.test_confidence_api import (
    add_digital_statement,
    add_scanned_statement,
    audit_actions,
    evaluate,
)
from tests.test_document_analysis_api import (
    BANK_STATEMENT_TEXT,
    add_digital_pdf,
    analyze_documents,
    run_processing,
)
from tests.test_normalization_api import normalize
from tests.test_technical_validation_api import (
    add_document,
    create_application,
    run_validation,
)

API = "/api/v1"

VALIDATE_URL = "/validate"
VALIDATION_RESULTS_URL = "/validation-results"

RULE_ENGINE_VERSION = "1.0.0"

#: Synthetic Bilateral Agreement text (never real data), real-template-shaped
#: 2026-08-22 to match BilateralAgreementExtractor's real-sample rewrite (see
#: that class's docstring and test_document_analysis_engine.py's fixture of
#: the same shape) -- the previous version used a labeled "Department:"/
#: "Section 5.2:"/"Account Title:" shape that matched neither real sample and
#: is honestly missing under the rewritten patterns.
#:
#: account_number/iban deliberately carry the SAME values as
#: ACCOUNT_MAINTENANCE_CERTIFICATE_CROSS_DOC_TEXT/TRIPARTITE_AGREEMENT_CROSS_DOC_TEXT
#: below, via a combined "Account No./IBAN: <number>/<iban>" label the shared
#: structural parser (_extract_bank_account_block) splits into separate
#: account_number and iban values -- so CROSS_ACCOUNT_NUMBER_MATCH/
#: CROSS_IBAN_MATCH below still have something real to compare. No
#: "Account Title"/"Account Holder" label is present at all: real Bilateral
#: Agreement bank tables never have one (confirmed on two independent real
#: samples -- see BilateralAgreementExtractor's docstring), which is exactly
#: why BILATERAL_AGREEMENT was removed from CrossAccountHolderRule's
#: participants (cross_document_rules.py) -- account_holder is not compared
#: against this fixture by that rule any more.
#:
#: Deliberately has no statement_period: a Bilateral Agreement doesn't carry
#: one, so CROSS_PERIOD_MATCH is expected to FAIL below, not PASS (rule is
#: actually unregistered -- see the other fixture files' matching comment).
BILATERAL_STATEMENT_TEXT = """AGREEMENT
FOR DIGITAL PAYMENT COLLECTION VIA PAYMIR
BETWEEN
Khyber Pakhtunkhwa Information Technology Board
AND
Sample Regional Development Authority

This Agreement is made and entered into on this 09 day of 03, 2026, at Peshawar,
By and Between:
Khyber Pakhtunkhwa Information Technology Board (KPITB), hereinafter referred as First party
or Party A or Party 1;
and
Sample Regional Development Authority, Government of Khyber Pakhtunkhwa, Peshawar,
having its registered office at Sample Road, Peshawar, hereinafter referred to as "Client" or
Second Party or Party B or Party 2 which expression shall, unless repugnant to the context,
include its successors-in-interests.

"PAYMIR" means Digital Payment Gateway developed by the KPITB.

5. PAYMENT METHODS & CHARGES
5.1.The following payment methods shall be available to citizens through Paymir:
5.2.Transaction Charges:
Amount in PKR (Transaction Range)
Transaction Charges (Including 1-LINK)
PKR 1-10,000
PKR 25.00 per transaction
6. DEPOSIT & DISBURSEMENT OF FUNDS
6.1.All payments collected through Paymir shall be deposited directly into the provided Bank of
the Sample Regional Development Authority as follow:
Bank Name: Future Bank Limited
Account No./IBAN: 1234567890/DE89370400440532013000
"""

#: Synthetic (fabricated, non-real) Account Maintenance Certificate text
#: carrying the same account_holder/account_number/iban values as
#: BANK_STATEMENT_TEXT/BILATERAL_STATEMENT_TEXT, plus a full AMC field set
#: (bank_name, branch_name, issue_date) so the certificate's template coverage
#: is complete and every extracted field auto-verifies -- an AMC without its
#: branch/issue details scores too low to be normalized without human review.
#: Deliberately carries no statement_period or balances, which a real AMC never
#: has (Master Rules section 3).
#: The issue-date label sits in the letterhead, before the certifying
#: sentence -- moved there 2026-08-26 to match the real corpus (Confidential
#: Data/.ocr_cache/, 7 samples across 4 banks): every real sample states its
#: own issue date in the header, never inside the post-certification detail
#: block as this fixture previously placed it. See
#: AccountMaintenanceCertificateExtractor's class docstring and CONTEXT.md.
ACCOUNT_MAINTENANCE_CERTIFICATE_CROSS_DOC_TEXT = """FUTURE BANK LIMITED
ACCOUNT MAINTENANCE CERTIFICATE
Date of Issue: 15/08/2026

This is to certify that the following account is maintained with us:

Account Title: John A. Doe
Account Number: 1234567890
IBAN: DE89370400440532013000
Bank Name: Future Bank Limited
Branch Name: Main Branch
"""

#: Synthetic (fabricated, non-real) Tripartite Agreement text carrying all six
#: Tripartite extractor fields (parties + account/branch details) with the same
#: account_holder/account_number values as the AMC/Bilateral fixtures above, so
#: the cross-document rules can compare a real-shaped Tripartite Agreement.
#: Deliberately has no iban/statement_period -- a Tripartite Agreement carries
#: neither (see TripartiteAgreementExtractor's expected field set).
TRIPARTITE_AGREEMENT_CROSS_DOC_TEXT = """TRIPARTITE AGREEMENT
This Tripartite Agreement is made and entered into by and between:
1-Link (Private) Limited, having its registered office at 4th Floor, State Life Building, Karachi (hereinafter referred to as '1-Link')
Khyber Pakhtunkhwa Information Technology Board, having its registered office at Civil Secretariat, Peshawar (hereinafter referred to as 'KPITB')
Transport and Mass Transit Department, Government of Khyber Pakhtunkhwa, having its office at Peshawar (hereinafter referred to as the 'Sub-biller')

Bank Details:
Account Title: John A. Doe
Account Number: 1234567890
Branch: Main Branch
"""

#: The Tripartite Agreement above with a different account holder, used by the
#: cross-document mismatch test.
TRIPARTITE_AGREEMENT_MISMATCH_TEXT = TRIPARTITE_AGREEMENT_CROSS_DOC_TEXT.replace(
    "Account Title: John A. Doe",
    "Account Title: John B. Smith",
)


def validate(client, application_id: int) -> dict:
    """Call the validate endpoint and return the JSON response."""
    response = client.post(f"{API}/applications/{application_id}{VALIDATE_URL}")
    assert response.status_code == 200, response.text
    return response.json()


def get_validation_results(client, application_id: int, category: str | None = None) -> dict:
    """Call the validation-results endpoint and return the JSON response."""
    url = f"{API}/applications/{application_id}{VALIDATION_RESULTS_URL}"
    if category:
        url += f"?category={category}"
    response = client.get(url)
    assert response.status_code == 200, response.text
    return response.json()


def add_statement_with_type(
    client,
    storage_root,
    application_id: int,
    *,
    document_type: DocumentType,
    text: str = BANK_STATEMENT_TEXT,
) -> int:
    """Add one analysed document of ``document_type`` to an application."""
    add_digital_pdf(storage_root, application_id, text, document_type=document_type)
    run_processing(client, application_id)
    analyze_documents(client, application_id)
    return application_id


def add_digital_amc(client, storage_root, application_id: int) -> int:
    """Upload + process + analyze a digital Account Maintenance Certificate."""
    add_digital_pdf(
        storage_root,
        application_id,
        ACCOUNT_MAINTENANCE_CERTIFICATE_CROSS_DOC_TEXT,
        document_type=DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
    )
    run_processing(client, application_id)
    analyze_documents(client, application_id)
    return application_id


def add_visual_detection(
    *,
    document_id: int,
    detection_type: str,
    is_present: bool,
    confidence: float | None = None,
) -> None:
    """Insert a visual detection outcome for a document."""
    db = SessionLocal()
    try:
        VisualDetectionRepository(db).upsert(
            document_id=document_id,
            detection_type=detection_type,
            is_present=is_present,
            confidence=confidence,
            detection_engine="test",
        )
    finally:
        db.close()


def document_ids_by_type(application_id: int) -> dict[str, int]:
    """Return the document id of each document type for an application."""
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                "SELECT document_type, id FROM documents "
                "WHERE application_id = :application_id"
            ),
            {"application_id": application_id},
        ).all()
        return {row[0]: row[1] for row in rows}
    finally:
        db.close()


# --- Full chain ---------------------------------------------------------------


def test_validate_digital_statement_full_chain(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    add_digital_amc(authenticated_client, storage_root, application_id)
    evaluate(authenticated_client, application_id)
    normalize(authenticated_client, application_id)

    result = validate(authenticated_client, application_id)

    assert result["application_id"] == application_id
    assert result["rule_engine_version"] == RULE_ENGINE_VERSION
    assert result["summary"]["total"] == 54
    assert len(result["category_summary"]) == 8

    by_rule = {item["rule_id"]: item for item in result["results"]}
    assert by_rule["DOC_AMC_PRESENT"]["status"] == "PASS"
    assert by_rule["DOC_TRIPARTITE_PRESENT"]["status"] == "FAIL"
    assert by_rule["DOC_BILATERAL_PRESENT"]["status"] == "FAIL"
    assert by_rule["FLD_IBAN_PRESENT"]["status"] == "PASS"
    assert by_rule["FLD_ACCOUNT_HOLDER_PRESENT"]["status"] == "PASS"
    assert by_rule["FMT_IBAN"]["status"] == "PASS"
    assert by_rule["FMT_ACCOUNT_NUMBER"]["status"] == "PASS"
    # The AMC carries no amount/period/currency/transaction fields by design
    # (see Master Rules section 3), so the bank-statement rules warn rather
    # than pass on a real certificate.
    assert by_rule["FMT_AMOUNT"]["status"] == "WARNING"
    assert by_rule["DATE_PERIOD_SEQUENCE"]["status"] == "WARNING"
    assert by_rule["DATE_PERIOD_WITHIN_RANGE"]["status"] == "WARNING"
    assert by_rule["POL_BALANCE_RECONCILIATION"]["status"] == "WARNING"
    assert by_rule["POL_SINGLE_CURRENCY"]["status"] == "WARNING"
    assert by_rule["POL_ACCOUNT_HOLDER_REAL"]["status"] == "PASS"
    assert by_rule["QUAL_TRANSACTION_COUNT"]["status"] == "PASS"
    assert by_rule["VIS_SIGNATURE_AMC"]["status"] == "PENDING_MANUAL_REVIEW"
    assert by_rule["VIS_STAMP_AMC"]["status"] == "PENDING_MANUAL_REVIEW"
    assert by_rule["CROSS_ACCOUNT_HOLDER_MATCH"]["status"] == "FAIL"

    assert result["validation_status"] == "FAIL"


def test_validate_persists_rule_results(authenticated_client, storage_root):
    application_id = add_digital_statement(authenticated_client, storage_root)
    evaluate(authenticated_client, application_id)
    normalize(authenticated_client, application_id)
    validate(authenticated_client, application_id)

    stored = get_validation_results(authenticated_client, application_id)

    assert stored["application_id"] == application_id
    assert stored["total"] == 54
    by_rule = {item["rule_id"]: item for item in stored["results"]}
    assert by_rule["FMT_IBAN"]["status"] == "PASS"
    assert by_rule["FMT_IBAN"]["severity"] == "INFO"
    assert by_rule["DOC_TRIPARTITE_PRESENT"]["severity"] == "ERROR"
    # The digital statement is not an AMC document, so the AMC-targeted visual
    # rule fails as a missing document (ERROR) rather than pending review.
    assert by_rule["VIS_SIGNATURE_AMC"]["severity"] == "ERROR"
    assert by_rule["VIS_SIGNATURE_AMC"]["category_label"] == "Visual verification"
    assert by_rule["FLD_IBAN_PRESENT"]["related_field_names"] == ["iban"]
    assert by_rule["FMT_IBAN"]["related_document_ids"]


def test_validate_is_idempotent_in_storage(authenticated_client, storage_root):
    application_id = add_digital_statement(authenticated_client, storage_root)
    evaluate(authenticated_client, application_id)
    normalize(authenticated_client, application_id)

    validate(authenticated_client, application_id)
    first = get_validation_results(authenticated_client, application_id)
    validate(authenticated_client, application_id)
    second = get_validation_results(authenticated_client, application_id)

    assert first["total"] == second["total"] == 54
    assert [item["rule_id"] for item in first["results"]] == [
        item["rule_id"] for item in second["results"]
    ]


def test_validate_is_audited(authenticated_client, storage_root):
    application_id = add_digital_statement(authenticated_client, storage_root)
    evaluate(authenticated_client, application_id)
    normalize(authenticated_client, application_id)
    validate(authenticated_client, application_id)

    actions = audit_actions(application_id)
    assert actions.count("rule_engine.validated") == 1


def test_get_validation_results_excludes_technical_rows(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    add_digital_pdf(storage_root, application_id, BANK_STATEMENT_TEXT)
    run_validation(authenticated_client, application_id)
    run_processing(authenticated_client, application_id)
    analyze_documents(authenticated_client, application_id)
    evaluate(authenticated_client, application_id)
    normalize(authenticated_client, application_id)
    validate(authenticated_client, application_id)

    stored = get_validation_results(authenticated_client, application_id)
    assert stored["total"] == 54
    assert all(
        item["rule_category"] != "technical_validation" for item in stored["results"]
    )


def test_get_validation_results_filters_by_category(authenticated_client, storage_root):
    application_id = add_digital_statement(authenticated_client, storage_root)
    evaluate(authenticated_client, application_id)
    normalize(authenticated_client, application_id)
    validate(authenticated_client, application_id)

    stored = get_validation_results(authenticated_client, application_id, category="visual")

    assert stored["total"] == 11
    assert all(item["rule_category"] == "visual" for item in stored["results"])
    assert all(item["category_label"] == "Visual verification" for item in stored["results"])


# --- Visual detections -------------------------------------------------------


def test_validate_visual_rules_pass_with_detections(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    add_digital_amc(authenticated_client, storage_root, application_id)
    evaluate(authenticated_client, application_id)
    normalize(authenticated_client, application_id)
    amc_id = document_ids_by_type(application_id)["ACCOUNT_MAINTENANCE_CERTIFICATE"]
    add_visual_detection(document_id=amc_id, detection_type="SIGNATURE", is_present=True)
    add_visual_detection(document_id=amc_id, detection_type="STAMP", is_present=True)

    result = validate(authenticated_client, application_id)

    by_rule = {item["rule_id"]: item for item in result["results"]}
    assert by_rule["VIS_SIGNATURE_AMC"]["status"] == "PASS"
    assert by_rule["VIS_STAMP_AMC"]["status"] == "PASS"


def test_validate_visual_rules_fail_when_absent(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    add_digital_amc(authenticated_client, storage_root, application_id)
    evaluate(authenticated_client, application_id)
    normalize(authenticated_client, application_id)
    amc_id = document_ids_by_type(application_id)["ACCOUNT_MAINTENANCE_CERTIFICATE"]
    add_visual_detection(document_id=amc_id, detection_type="SIGNATURE", is_present=False)

    result = validate(authenticated_client, application_id)

    by_rule = {item["rule_id"]: item for item in result["results"]}
    assert by_rule["VIS_SIGNATURE_AMC"]["status"] == "FAIL"
    assert "not detected" in by_rule["VIS_SIGNATURE_AMC"]["message"]


# --- Cross-document consistency ----------------------------------------------


def test_validate_cross_document_rules_pass(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    add_statement_with_type(
        authenticated_client,
        storage_root,
        application_id,
        document_type=DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
        text=ACCOUNT_MAINTENANCE_CERTIFICATE_CROSS_DOC_TEXT,
    )
    add_statement_with_type(
        authenticated_client,
        storage_root,
        application_id,
        document_type=DocumentType.BILATERAL_AGREEMENT,
        text=BILATERAL_STATEMENT_TEXT,
    )
    add_statement_with_type(
        authenticated_client,
        storage_root,
        application_id,
        document_type=DocumentType.TRIPARTITE_AGREEMENT,
        text=TRIPARTITE_AGREEMENT_CROSS_DOC_TEXT,
    )
    evaluate(authenticated_client, application_id)
    normalize(authenticated_client, application_id)

    result = validate(authenticated_client, application_id)

    by_rule = {item["rule_id"]: item for item in result["results"]}
    assert by_rule["CROSS_ACCOUNT_HOLDER_MATCH"]["status"] == "PASS"
    assert by_rule["CROSS_ACCOUNT_NUMBER_MATCH"]["status"] == "PASS"
    assert by_rule["CROSS_IBAN_MATCH"]["status"] == "PASS"
    # CrossPeriodRule is unregistered (rule_engine/rules/__init__.py): a
    # Bilateral Agreement doesn't carry a statement_period in the real spec,
    # so the rule could never legitimately pass -- same treatment as
    # CrossBranchCodeRule. Not present in by_rule at all.
    assert "CROSS_PERIOD_MATCH" not in by_rule
    assert by_rule["DOC_AMC_PRESENT"]["status"] == "PASS"
    assert by_rule["DOC_BILATERAL_PRESENT"]["status"] == "PASS"
    assert by_rule["DOC_TRIPARTITE_PRESENT"]["status"] == "PASS"


def test_validate_cross_document_rules_fail_on_mismatch(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)
    add_statement_with_type(
        authenticated_client,
        storage_root,
        application_id,
        document_type=DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
        text=ACCOUNT_MAINTENANCE_CERTIFICATE_CROSS_DOC_TEXT,
    )
    add_statement_with_type(
        authenticated_client,
        storage_root,
        application_id,
        document_type=DocumentType.BILATERAL_AGREEMENT,
        text=BILATERAL_STATEMENT_TEXT,
    )
    add_statement_with_type(
        authenticated_client,
        storage_root,
        application_id,
        document_type=DocumentType.TRIPARTITE_AGREEMENT,
        text=TRIPARTITE_AGREEMENT_MISMATCH_TEXT,
    )
    evaluate(authenticated_client, application_id)
    normalize(authenticated_client, application_id)

    result = validate(authenticated_client, application_id)

    by_rule = {item["rule_id"]: item for item in result["results"]}
    assert by_rule["CROSS_ACCOUNT_HOLDER_MATCH"]["status"] == "FAIL"
    assert "differs" in by_rule["CROSS_ACCOUNT_HOLDER_MATCH"]["message"]
    assert by_rule["CROSS_ACCOUNT_NUMBER_MATCH"]["status"] == "PASS"


# --- Pipeline robustness -----------------------------------------------------


def test_validate_runs_without_extracted_fields(authenticated_client, storage_root):
    application_id = create_application(authenticated_client)

    result = validate(authenticated_client, application_id)

    assert result["summary"]["total"] == 54
    assert result["validation_status"] == "FAIL"
    by_rule = {item["rule_id"]: item for item in result["results"]}
    assert by_rule["DOC_AMC_PRESENT"]["status"] == "FAIL"
    assert by_rule["FLD_IBAN_PRESENT"]["status"] == "FAIL"


def test_validate_skipped_fields_warn(authenticated_client, storage_root, monkeypatch):
    application_id = add_scanned_statement(authenticated_client, storage_root, monkeypatch)
    flagged = evaluate(authenticated_client, application_id)["fields_requiring_review"]
    decisions = [
        {"field_name": field["field_name"], "decision": "VERIFIED"}
        for field in flagged
        if field["field_name"] != "iban"
    ]
    decisions.append({"field_name": "iban", "decision": "CANNOT_VERIFY"})
    review_response = authenticated_client.post(
        f"{API}/applications/{application_id}/confidence/review",
        json={"reviewer_name": "reviewer", "decisions": decisions},
    )
    assert review_response.status_code == 200, review_response.text
    normalize(authenticated_client, application_id)

    result = validate(authenticated_client, application_id)

    by_rule = {item["rule_id"]: item for item in result["results"]}
    assert by_rule["FLD_IBAN_PRESENT"]["status"] == "FAIL"
    assert by_rule["FMT_IBAN"]["status"] == "WARNING"


# --- Error paths -------------------------------------------------------------


def test_validate_application_not_found(authenticated_client):
    response = authenticated_client.post(f"{API}/applications/999999{VALIDATE_URL}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Application not found"


def test_get_validation_results_application_not_found(authenticated_client):
    response = authenticated_client.get(f"{API}/applications/999999{VALIDATION_RESULTS_URL}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Application not found"

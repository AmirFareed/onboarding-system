"""Tests for the business rule engine rules.

Rules are pure functions of a :class:`RuleContext`, so every rule is unit
tested here by building contexts by hand -- no database, no HTTP. Tests cover
every rule category plus the registry contract (50 rules, 8 categories,
unique ids) and the overall-status/severity derivation helpers.
"""

from datetime import date, timedelta

import pytest

from app.database.models.enums import DocumentType, ValidationStatus
from app.rule_engine.rules import REGISTRY
from app.rule_engine.schemas import FieldValue, RuleContext
from app.rule_engine.services import _overall_status, _severity_for
from app.rule_engine.rules.base import RuleResult

AMC = DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE.value
TRIPARTITE = DocumentType.TRIPARTITE_AGREEMENT.value
BILATERAL = DocumentType.BILATERAL_AGREEMENT.value
ONE_LINK = DocumentType.ONE_LINK_LETTER.value
FORMAL_REQUEST = DocumentType.FORMAL_REQUEST_LETTER.value

STATEMENT_FIELDS = [
    ("iban", "DE89370400440532013000"),
    ("account_number", "1234567890"),
    ("account_holder", "JOHN A. DOE"),
    ("bank_name", "SPARKASSE"),
    ("statement_period", "2026-01-01 - 2026-01-31"),
    ("opening_balance", "1,250.50"),
    ("closing_balance", "3,200.75"),
    ("total_credits", "2,500.00"),
    ("total_debits", "549.75"),
    ("currency", "EUR"),
    ("transactions", "23"),
]


def field(
    name: str,
    normalized: str,
    *,
    doc_id: int = 1,
    doc_type: str = AMC,
    extracted: str | None = None,
    confidence: float | None = 1.0,
) -> FieldValue:
    """Build a field value record for a context."""
    return FieldValue(
        field_name=name,
        document_id=doc_id,
        document_type=doc_type,
        extracted_value=extracted if extracted is not None else normalized or "",
        normalized_value=normalized,
        verification_status="AUTO_VERIFIED",
        confidence_score=confidence,
    )


def context(
    *,
    docs: dict[str, list[int]] | None = None,
    fields: list[FieldValue] | None = None,
    detections: dict[tuple[int, str], bool] | None = None,
) -> RuleContext:
    """Build a rule context for hand-written scenarios."""
    return RuleContext(
        application_id=1,
        documents_by_type=docs or {},
        fields=fields or [],
        detections=detections or {},
    )


def rule(rule_id: str):
    """Return the registered rule with ``rule_id``."""
    rule = REGISTRY.get(rule_id)
    assert rule is not None, f"rule {rule_id} not registered"
    return rule


def run(rule_id: str, ctx: RuleContext) -> RuleResult:
    """Evaluate the registered rule against ``ctx``."""
    return rule(rule_id).evaluate(ctx)


# --- Registry contract -------------------------------------------------------


def test_registry_has_54_rules_in_8_categories():
    from collections import Counter

    rules = REGISTRY.rules()
    assert len(rules) == 54
    categories = Counter(rule.category for rule in rules)
    assert categories == {
        # DocumentScheduleRule is implemented but deliberately not registered
        # -- see the inline rationale in rule_engine/rules/__init__.py.
        "document_completeness": 7,
        "field_presence": 11,
        "format": 6,
        # CrossBranchCodeRule and CrossPeriodRule are implemented but
        # deliberately not registered -- see the inline rationale in
        # rule_engine/rules/__init__.py. FieldStatementPeriodPresenceRule and
        # FieldBalancesPresenceRule were removed outright -- see the same file.
        "cross_document": 3,
        "date": 8,
        "visual": 11,
        "policy": 4,
        "quality": 4,
    }


def test_registry_rule_ids_are_unique():
    ids = [rule.id for rule in REGISTRY.rules()]
    assert len(ids) == len(set(ids))


# --- Document completeness ---------------------------------------------------


@pytest.mark.parametrize(
    "document_type,rule_id",
    [
        (DocumentType.TRIPARTITE_AGREEMENT, "DOC_TRIPARTITE_PRESENT"),
        (DocumentType.BILATERAL_AGREEMENT, "DOC_BILATERAL_PRESENT"),
        (DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE, "DOC_AMC_PRESENT"),
        (DocumentType.ONE_LINK_LETTER, "DOC_ONE_LINK_PRESENT"),
        (DocumentType.AUTHORITY_LETTER, "DOC_AUTHORITY_LETTER_PRESENT"),
        (DocumentType.BUSINESS_REQUIREMENT_DOCUMENT, "DOC_BRD_PRESENT"),
        (DocumentType.FORMAL_REQUEST_LETTER, "DOC_FORMAL_REQUEST_PRESENT"),
    ],
)
def test_document_rule_passes_with_exactly_one_document(document_type, rule_id):
    result = run(rule_id, context(docs={document_type.value: [10]}))
    assert result.status is ValidationStatus.PASS
    assert result.related_document_ids == [10]


def test_document_rule_fails_when_missing():
    result = run("DOC_AMC_PRESENT", context(docs={ONE_LINK: [1]}))
    assert result.status is ValidationStatus.FAIL
    assert "missing" in result.message.lower()


def test_document_rule_fails_when_duplicated():
    result = run("DOC_AMC_PRESENT", context(docs={AMC: [1, 2]}))
    assert result.status is ValidationStatus.FAIL
    assert "more than once" in result.message


# --- Field presence ----------------------------------------------------------


def test_field_presence_passes_with_normalized_value():
    result = run(
        "FLD_IBAN_PRESENT",
        context(fields=[field("iban", "DE89370400440532013000")]),
    )
    assert result.status is ValidationStatus.PASS


def test_field_presence_fails_when_missing():
    result = run("FLD_IBAN_PRESENT", context(fields=[field("account_number", "123")]))
    assert result.status is ValidationStatus.FAIL
    assert "missing" in result.message.lower()


def test_field_presence_warns_when_not_normalized():
    result = run(
        "FLD_IBAN_PRESENT",
        context(fields=[field("iban", None, extracted="DE89370400440532013000")]),
    )
    assert result.status is ValidationStatus.WARNING
    assert "no normalized value" in result.message


def test_field_presence_ignores_other_document_types():
    result = run(
        "FLD_IBAN_PRESENT",
        context(
            docs={ONE_LINK: [1], AMC: [2]},
            fields=[field("iban", "DE89370400440532013000", doc_id=1, doc_type=ONE_LINK)],
        ),
    )
    assert result.status is ValidationStatus.FAIL


def test_bilateral_effective_date_passes_with_normalized_value():
    """Mirrors the real Conservator_Wildlife_Peshawar_Zoo sample: the
    preamble's day/month/year are filled in, extracting a normalized ISO
    date."""
    result = run(
        "FLD_BILATERAL_EFFECTIVE_DATE_PRESENT",
        context(fields=[field("effective_date", "2026-05-11", doc_type=BILATERAL)]),
    )
    assert result.status is ValidationStatus.PASS


def test_bilateral_effective_date_fails_when_missing():
    """Mirrors the real schdule_of_charges_or_bilateral sample: the
    preamble's day/month/year are the template's own unfilled placeholder
    ("on this day of , 20 ,"), so RegexExtractor never emits an
    effective_date FieldValue at all -- confirmed 2026-08-23 by running
    extract_fields directly against that real cached document, not assumed."""
    result = run(
        "FLD_BILATERAL_EFFECTIVE_DATE_PRESENT",
        context(fields=[field("platform_name", "Paymir", doc_type=BILATERAL)]),
    )
    assert result.status is ValidationStatus.FAIL
    assert "bilateral agreement" in result.message.lower()


def test_bilateral_effective_date_ignores_other_document_types():
    result = run(
        "FLD_BILATERAL_EFFECTIVE_DATE_PRESENT",
        context(
            docs={AMC: [1], BILATERAL: [2]},
            fields=[field("effective_date", "2026-05-11", doc_id=1, doc_type=AMC)],
        ),
    )
    assert result.status is ValidationStatus.FAIL


def test_formal_request_subject_passes_with_normalized_value():
    result = run(
        "FLD_FORMAL_REQUEST_SUBJECT_PRESENT",
        context(
            fields=[
                field(
                    "subject",
                    "REQUEST FOR DIGITAL ACCOUNT AND FOR ONLINE PAYMENTS.",
                    doc_id=1,
                    doc_type=FORMAL_REQUEST,
                )
            ]
        ),
    )
    assert result.status is ValidationStatus.PASS


def test_formal_request_subject_fails_when_missing():
    result = run(
        "FLD_FORMAL_REQUEST_SUBJECT_PRESENT",
        context(fields=[field("organization_name", "TMA LAL DIR UPPER", doc_type=FORMAL_REQUEST)]),
    )
    assert result.status is ValidationStatus.FAIL
    assert "formal request letter" in result.message.lower()


def test_formal_request_subject_ignores_other_document_types():
    result = run(
        "FLD_FORMAL_REQUEST_SUBJECT_PRESENT",
        context(
            docs={AMC: [1], FORMAL_REQUEST: [2]},
            fields=[field("subject", "SOME SUBJECT", doc_id=1, doc_type=AMC)],
        ),
    )
    assert result.status is ValidationStatus.FAIL


def test_formal_request_organization_passes_with_normalized_value():
    result = run(
        "FLD_FORMAL_REQUEST_ORGANIZATION_PRESENT",
        context(
            fields=[
                field(
                    "organization_name",
                    "TEHSIL MUNICIPAL ADMINISTRATION LAL DIR UPPER",
                    doc_id=1,
                    doc_type=FORMAL_REQUEST,
                )
            ]
        ),
    )
    assert result.status is ValidationStatus.PASS


def test_formal_request_organization_fails_when_missing():
    result = run(
        "FLD_FORMAL_REQUEST_ORGANIZATION_PRESENT",
        context(fields=[field("subject", "SOME SUBJECT", doc_type=FORMAL_REQUEST)]),
    )
    assert result.status is ValidationStatus.FAIL
    assert "formal request letter" in result.message.lower()


AUTHORITY = DocumentType.AUTHORITY_LETTER.value


def test_authority_letter_organization_passes_with_normalized_value():
    result = run(
        "FLD_AUTHORITY_LETTER_ORGANIZATION_PRESENT",
        context(fields=[field("organization_name", "Directorate", doc_type=AUTHORITY)]),
    )
    assert result.status is ValidationStatus.PASS


def test_authority_letter_organization_fails_when_missing():
    result = run(
        "FLD_AUTHORITY_LETTER_ORGANIZATION_PRESENT",
        context(fields=[field("focal_person_name", "Naveed Khan", doc_type=AUTHORITY)]),
    )
    assert result.status is ValidationStatus.FAIL
    assert "authority letter" in result.message.lower()


def test_authority_letter_focal_person_passes_with_normalized_value():
    result = run(
        "FLD_AUTHORITY_LETTER_FOCAL_PERSON_PRESENT",
        context(fields=[field("focal_person_name", "Naveed Khan", doc_type=AUTHORITY)]),
    )
    assert result.status is ValidationStatus.PASS


def test_authority_letter_focal_person_fails_when_missing():
    result = run(
        "FLD_AUTHORITY_LETTER_FOCAL_PERSON_PRESENT",
        context(fields=[field("organization_name", "Directorate", doc_type=AUTHORITY)]),
    )
    assert result.status is ValidationStatus.FAIL
    assert "authority letter" in result.message.lower()


BRD = DocumentType.BUSINESS_REQUIREMENT_DOCUMENT.value


def test_brd_digitization_intent_passes_with_normalized_value():
    result = run(
        "FLD_BRD_DIGITIZATION_INTENT_PRESENT",
        context(fields=[field("digitization_intent_confirmed", "KPITB's FinTech Unit", doc_type=BRD)]),
    )
    assert result.status is ValidationStatus.PASS


def test_brd_digitization_intent_fails_when_missing():
    result = run(
        "FLD_BRD_DIGITIZATION_INTENT_PRESENT",
        context(fields=[field("revenue_services_listed", "Fee collection", doc_type=BRD)]),
    )
    assert result.status is ValidationStatus.FAIL
    assert "business requirement document" in result.message.lower()


# --- Format ------------------------------------------------------------------


def test_iban_format_passes():
    result = run(
        "FMT_IBAN",
        context(fields=[field("iban", "DE89370400440532013000")]),
    )
    assert result.status is ValidationStatus.PASS


def test_iban_format_fails_on_invalid_value():
    result = run(
        "FMT_IBAN",
        context(fields=[field("iban", "NOT AN IBAN")]),
    )
    assert result.status is ValidationStatus.FAIL


def test_format_rule_warns_when_nothing_to_validate():
    result = run("FMT_IBAN", context(fields=[field("account_number", "123456")]))
    assert result.status is ValidationStatus.WARNING
    assert "no values of the required fields" in result.message.lower()


def test_account_number_format_fails_on_short_value():
    result = run(
        "FMT_ACCOUNT_NUMBER",
        context(fields=[field("account_number", "12")]),
    )
    assert result.status is ValidationStatus.FAIL


def test_amount_format_passes_on_thousands_separators():
    result = run(
        "FMT_AMOUNT",
        context(fields=[field("opening_balance", "1,250.50")]),
    )
    assert result.status is ValidationStatus.PASS


def test_amount_format_fails_on_bare_text():
    result = run(
        "FMT_AMOUNT",
        context(fields=[field("closing_balance", "lots")]),
    )
    assert result.status is ValidationStatus.FAIL


def test_date_shape_format_fails_on_non_iso_date():
    result = run(
        "FMT_DATE_SHAPE",
        context(fields=[field("payment_date", "31/01/2026")]),
    )
    assert result.status is ValidationStatus.FAIL


# --- Cross-document ----------------------------------------------------------


def _cross_document_context(**tripartite_overrides) -> RuleContext:
    docs = {
        AMC: [1],
        BILATERAL: [2],
        TRIPARTITE: [3],
    }
    fields = [
        field("account_holder", "JOHN A. DOE", doc_id=1, doc_type=AMC),
        field("account_holder", "JOHN A. DOE", doc_id=2, doc_type=BILATERAL),
        field("account_holder", "JOHN A. DOE", doc_id=3, doc_type=TRIPARTITE),
        field("account_number", "1234567890", doc_id=1, doc_type=AMC),
        field("account_number", "1234567890", doc_id=2, doc_type=BILATERAL),
        field("account_number", "1234567890", doc_id=3, doc_type=TRIPARTITE),
        field("iban", "DE89370400440532013000", doc_id=1, doc_type=AMC),
        field("iban", "DE89370400440532013000", doc_id=2, doc_type=BILATERAL),
        field("statement_period", "2026-01-01 - 2026-01-31", doc_id=1, doc_type=AMC),
        field("statement_period", "2026-01-01 - 2026-01-31", doc_id=2, doc_type=BILATERAL),
    ]
    if tripartite_overrides:
        for name, value in tripartite_overrides.items():
            fields = [
                f
                for f in fields
                if not (f.field_name == name and f.document_type == TRIPARTITE)
            ]
            fields.append(field(name, value, doc_id=3, doc_type=TRIPARTITE))
    return context(docs=docs, fields=fields)


def test_cross_document_rule_passes_when_values_agree():
    result = run("CROSS_ACCOUNT_HOLDER_MATCH", _cross_document_context())
    assert result.status is ValidationStatus.PASS


def test_cross_document_rule_fails_on_mismatch():
    result = run(
        "CROSS_ACCOUNT_HOLDER_MATCH",
        _cross_document_context(account_holder="JOHN B. SMITH"),
    )
    assert result.status is ValidationStatus.FAIL
    assert "differs" in result.message


def test_cross_document_rule_fails_on_missing_participant():
    docs = _cross_document_context().documents_by_type
    del docs[TRIPARTITE]
    result = run("CROSS_ACCOUNT_HOLDER_MATCH", context(docs=docs, fields=_cross_document_context().fields))
    assert result.status is ValidationStatus.FAIL
    assert "missing" in result.message.lower()


def test_cross_document_rule_fails_on_missing_field_in_participant():
    # TRIPARTITE, not BILATERAL: CrossAccountHolderRule's participants no
    # longer include BILATERAL_AGREEMENT (unregistered 2026-08-22 -- real
    # Bilateral Agreement bank tables never carry an Account Title/Holder
    # column, see cross_document_rules.py), so stripping BILATERAL's
    # account_holder here would no longer affect this rule at all.
    ctx = _cross_document_context()
    ctx.fields = [
        field_value
        for field_value in ctx.fields
        if not (field_value.field_name == "account_holder" and field_value.document_type == TRIPARTITE)
    ]
    result = run("CROSS_ACCOUNT_HOLDER_MATCH", ctx)
    assert result.status is ValidationStatus.FAIL
    assert "missing from document" in result.message


# --- Date and period ---------------------------------------------------------


def _period_context(period: str | None) -> RuleContext:
    return context(fields=[field("statement_period", period)] if period else [])


def test_period_sequence_passes():
    result = run("DATE_PERIOD_SEQUENCE", _period_context("2026-01-01 - 2026-01-31"))
    assert result.status is ValidationStatus.PASS


def test_period_sequence_fails_when_reversed():
    result = run("DATE_PERIOD_SEQUENCE", _period_context("2026-01-31 - 2026-01-01"))
    assert result.status is ValidationStatus.FAIL


def test_period_sequence_warns_when_nothing_to_validate():
    result = run("DATE_PERIOD_SEQUENCE", _period_context(None))
    assert result.status is ValidationStatus.WARNING


def _recent_period() -> str:
    end = date.today() - timedelta(days=30)
    start = end - timedelta(days=30)
    return f"{start.isoformat()} - {end.isoformat()}"


def test_period_range_passes_for_recent_period():
    result = run("DATE_PERIOD_WITHIN_RANGE", _period_context(_recent_period()))
    assert result.status is ValidationStatus.PASS


def test_period_range_fails_for_future_period():
    end = date.today() + timedelta(days=10)
    start = end - timedelta(days=30)
    result = run(
        "DATE_PERIOD_WITHIN_RANGE",
        _period_context(f"{start.isoformat()} - {end.isoformat()}"),
    )
    assert result.status is ValidationStatus.FAIL
    assert "future" in result.message


def test_period_range_warns_for_stale_period():
    end = date.today() - timedelta(days=400)
    start = end - timedelta(days=30)
    result = run(
        "DATE_PERIOD_WITHIN_RANGE",
        _period_context(f"{start.isoformat()} - {end.isoformat()}"),
    )
    assert result.status is ValidationStatus.WARNING


def test_issue_precedes_expiry_passes():
    ctx = context(
        fields=[
            field("issue_date", "2020-01-01"),
            field("expiry_date", "2030-01-01"),
        ]
    )
    assert run("DATE_ISSUE_PRECEDES_EXPIRY", ctx).status is ValidationStatus.PASS


def test_issue_precedes_expiry_fails():
    ctx = context(
        fields=[
            field("issue_date", "2030-01-01"),
            field("expiry_date", "2020-01-01"),
        ]
    )
    assert run("DATE_ISSUE_PRECEDES_EXPIRY", ctx).status is ValidationStatus.FAIL


def test_payment_recency_fails_on_future_date():
    future = (date.today() + timedelta(days=5)).isoformat()
    result = run("DATE_PAYMENT_RECENCY", context(fields=[field("payment_date", future)]))
    assert result.status is ValidationStatus.FAIL


def test_dob_sanity_fails_on_implausible_year():
    result = run(
        "DATE_DOB_SANITY",
        context(fields=[field("date_of_birth", "1850-01-01")]),
    )
    assert result.status is ValidationStatus.FAIL


def test_cnic_not_expired_fails_on_past_date():
    past = (date.today() - timedelta(days=5)).isoformat()
    result = run(
        "DATE_CNIC_NOT_EXPIRED",
        context(fields=[field("date_of_expiry", past, doc_type=DocumentType.CNIC_FRONT.value)]),
    )
    assert result.status is ValidationStatus.FAIL


def test_cnic_not_expired_passes_on_future_date():
    future = (date.today() + timedelta(days=365)).isoformat()
    result = run(
        "DATE_CNIC_NOT_EXPIRED",
        context(fields=[field("date_of_expiry", future, doc_type=DocumentType.CNIC_FRONT.value)]),
    )
    assert result.status is ValidationStatus.PASS


def test_cnic_not_expired_warns_when_missing():
    result = run("DATE_CNIC_NOT_EXPIRED", context())
    assert result.status is ValidationStatus.WARNING


def test_cnic_not_expired_warns_on_unparseable_value():
    result = run(
        "DATE_CNIC_NOT_EXPIRED",
        context(fields=[field("date_of_expiry", "not-a-date", doc_type=DocumentType.CNIC_FRONT.value)]),
    )
    assert result.status is ValidationStatus.WARNING


# --- Visual verification -----------------------------------------------------


def _visual_context(doc_type: str, doc_id: int, detected: bool | None) -> RuleContext:
    detections = {(doc_id, "SIGNATURE"): detected} if detected is not None else {}
    return context(docs={doc_type: [doc_id]}, detections=detections)


def test_visual_rule_passes_when_detection_present():
    result = run("VIS_SIGNATURE_AMC", _visual_context(AMC, 1, True))
    assert result.status is ValidationStatus.PASS


def test_visual_rule_fails_when_detection_absent():
    result = run("VIS_SIGNATURE_AMC", _visual_context(AMC, 1, False))
    assert result.status is ValidationStatus.FAIL
    assert "not detected" in result.message


def test_visual_rule_pending_when_no_detection_outcome():
    result = run("VIS_SIGNATURE_AMC", _visual_context(AMC, 1, None))
    assert result.status is ValidationStatus.PENDING_MANUAL_REVIEW


def test_visual_rule_fails_when_document_missing():
    result = run("VIS_SIGNATURE_AMC", context(docs={}))
    assert result.status is ValidationStatus.FAIL


# --- Policy ------------------------------------------------------------------


def test_policy_account_holder_real_passes():
    result = run(
        "POL_ACCOUNT_HOLDER_REAL",
        context(fields=[field("account_holder", "JOHN A. DOE")]),
    )
    assert result.status is ValidationStatus.PASS


def test_policy_account_holder_rejects_placeholder():
    result = run(
        "POL_ACCOUNT_HOLDER_REAL",
        context(fields=[field("account_holder", "NOT PROVIDED")]),
    )
    assert result.status is ValidationStatus.FAIL


def test_policy_reconciliation_passes():
    fields = [field(name, value) for name, value in STATEMENT_FIELDS]
    result = run("POL_BALANCE_RECONCILIATION", context(fields=fields))
    assert result.status is ValidationStatus.PASS


def test_policy_reconciliation_fails_on_mismatch():
    fields = [
        field("opening_balance", "1,250.50"),
        field("closing_balance", "9,999.99"),
        field("total_credits", "2,500.00"),
        field("total_debits", "549.75"),
    ]
    result = run("POL_BALANCE_RECONCILIATION", context(fields=fields))
    assert result.status is ValidationStatus.FAIL


def test_policy_reconciliation_warns_when_component_missing():
    result = run(
        "POL_BALANCE_RECONCILIATION",
        context(fields=[field("opening_balance", "1,250.50")]),
    )
    assert result.status is ValidationStatus.WARNING


def test_policy_single_currency_passes():
    result = run(
        "POL_SINGLE_CURRENCY",
        context(fields=[field("currency", "EUR")]),
    )
    assert result.status is ValidationStatus.PASS


def test_policy_single_currency_fails_on_mixed_currencies():
    fields = [
        field("currency", "EUR", doc_id=1),
        field("currency", "USD", doc_id=2),
    ]
    result = run("POL_SINGLE_CURRENCY", context(fields=fields))
    assert result.status is ValidationStatus.FAIL


def test_policy_salary_aligned_passes():
    fields = [
        field("salary_month", "2026-01", doc_type=ONE_LINK),
        field("statement_period", "2026-01-01 - 2026-01-31"),
    ]
    result = run("POL_PERIOD_SALARY_ALIGNED", context(fields=fields))
    assert result.status is ValidationStatus.PASS


def test_policy_salary_aligned_fails_when_outside_period():
    fields = [
        field("salary_month", "2026-03", doc_type=ONE_LINK),
        field("statement_period", "2026-01-01 - 2026-01-31"),
    ]
    result = run("POL_PERIOD_SALARY_ALIGNED", context(fields=fields))
    assert result.status is ValidationStatus.FAIL


# --- Quality -----------------------------------------------------------------


def test_quality_clean_values_passes():
    fields = [field(name, value) for name, value in STATEMENT_FIELDS]
    result = run("QUAL_NORMALIZED_VALUES_CLEAN", context(fields=fields))
    assert result.status is ValidationStatus.PASS


def test_quality_clean_values_fails_on_stray_whitespace():
    result = run(
        "QUAL_NORMALIZED_VALUES_CLEAN",
        context(fields=[field("account_holder", "JOHN A. DOE ")]),
    )
    assert result.status is ValidationStatus.FAIL


def test_quality_no_empty_values_passes():
    fields = [field(name, value) for name, value in STATEMENT_FIELDS]
    result = run("QUAL_NO_EMPTY_VALUES", context(fields=fields))
    assert result.status is ValidationStatus.PASS


def test_quality_no_empty_values_fails_on_empty_extracted():
    result = run(
        "QUAL_NO_EMPTY_VALUES",
        context(fields=[field("iban", "DE89...", extracted="")]),
    )
    assert result.status is ValidationStatus.FAIL


def test_quality_confidence_floor_passes():
    fields = [field(name, value) for name, value in STATEMENT_FIELDS]
    result = run("QUAL_CONFIDENCE_FLOOR", context(fields=fields))
    assert result.status is ValidationStatus.PASS


def test_quality_confidence_floor_fails_below_threshold():
    result = run(
        "QUAL_CONFIDENCE_FLOOR",
        context(fields=[field("iban", "DE89...", confidence=0.2)]),
    )
    assert result.status is ValidationStatus.FAIL


def test_quality_transaction_count_passes():
    result = run(
        "QUAL_TRANSACTION_COUNT",
        context(fields=[field("transaction_count", "23")]),
    )
    assert result.status is ValidationStatus.PASS


def test_quality_transaction_count_fails_on_non_integer():
    result = run(
        "QUAL_TRANSACTION_COUNT",
        context(fields=[field("transaction_count", "many")]),
    )
    assert result.status is ValidationStatus.FAIL


# --- Overall status and severity helpers -------------------------------------


def _result(status: ValidationStatus, rule_id: str = "X") -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        rule_name=rule_id,
        category="format",
        status=status,
    )


def test_overall_status_precedence():
    assert _overall_status([_result(ValidationStatus.PASS)]) is ValidationStatus.PASS
    assert (
        _overall_status([_result(ValidationStatus.PASS), _result(ValidationStatus.WARNING)])
        is ValidationStatus.WARNING
    )
    assert (
        _overall_status(
            [
                _result(ValidationStatus.PASS),
                _result(ValidationStatus.WARNING),
                _result(ValidationStatus.PENDING_MANUAL_REVIEW),
            ]
        )
        is ValidationStatus.PENDING_MANUAL_REVIEW
    )
    assert (
        _overall_status(
            [
                _result(ValidationStatus.PASS),
                _result(ValidationStatus.WARNING),
                _result(ValidationStatus.PENDING_MANUAL_REVIEW),
                _result(ValidationStatus.FAIL),
            ]
        )
        is ValidationStatus.FAIL
    )


def test_severity_for_statuses():
    assert _severity_for(ValidationStatus.PASS).value == "INFO"
    assert _severity_for(ValidationStatus.WARNING).value == "WARNING"
    assert _severity_for(ValidationStatus.PENDING_MANUAL_REVIEW).value == "WARNING"
    assert _severity_for(ValidationStatus.FAIL).value == "ERROR"

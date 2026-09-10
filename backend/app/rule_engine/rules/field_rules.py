"""Required field presence rules.

One rule per critical field expected on a specific document type, checking
that the field carries a normalized value. A field that is entirely absent
fails the rule; a field present but not yet normalized warns, because the
pipeline state rather than the document itself is the blocker. Most existing
rules target the account maintenance certificate's account-level identity
fields; `target_document_types`/`document_label` are overridable per rule so
the same base also covers other single-document fields (e.g. the formal
request letter's subject line) without duplicating this logic.
"""

from app.database.models.enums import DocumentType, ValidationStatus
from app.rule_engine.rules.base import BaseRule, RuleContext, RuleResult

#: Category every field-presence rule belongs to.
CATEGORY = "field_presence"

#: Document types the presence rules apply to (the account maintenance
#: certificate carries the account-level identity fields).
TARGET_DOCUMENT_TYPES = frozenset({DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE})


class _FieldPresenceRule(BaseRule):
    """Base rule asserting a field has a normalized value on one document type.

    Attributes:
        field_name: Field the rule enforces.
        target_document_types: Document types the rule applies to. Defaults
            to the account maintenance certificate for backward compatibility
            with the original AMC-only rules below.
        document_label: Human-readable document name used in messages.
    """

    field_name: str
    target_document_types: frozenset[DocumentType] = TARGET_DOCUMENT_TYPES
    document_label: str = "account maintenance certificate"

    category = CATEGORY

    def evaluate(self, context: RuleContext) -> RuleResult:
        values = [
            value
            for value in context.values(self.field_name)
            if value.document_type in {item.value for item in self.target_document_types}
        ]
        related_documents = sorted({value.document_id for value in values})
        related_fields = [self.field_name]
        normalized = [value for value in values if (value.normalized_value or "").strip()]
        if not values:
            return self.result(
                ValidationStatus.FAIL,
                f"Required field {self.field_name} is missing from the "
                f"{self.document_label}",
                related_document_ids=related_documents,
                related_field_names=related_fields,
            )
        if not normalized:
            return self.result(
                ValidationStatus.WARNING,
                f"Field {self.field_name} is present but has no normalized value",
                related_document_ids=related_documents,
                related_field_names=related_fields,
            )
        return self.result(
            ValidationStatus.PASS,
            f"Required field {self.field_name} is present with a normalized value",
            related_document_ids=related_documents,
            related_field_names=related_fields,
        )


class FieldIbanPresenceRule(_FieldPresenceRule):
    """The AMC must carry a normalized IBAN."""

    id = "FLD_IBAN_PRESENT"
    name = "IBAN present on account maintenance certificate"
    field_name = "iban"


class FieldAccountNumberPresenceRule(_FieldPresenceRule):
    """The AMC must carry a normalized account number."""

    id = "FLD_ACCOUNT_NUMBER_PRESENT"
    name = "Account number present on account maintenance certificate"
    field_name = "account_number"


class FieldAccountHolderPresenceRule(_FieldPresenceRule):
    """The AMC must carry a normalized account holder."""

    id = "FLD_ACCOUNT_HOLDER_PRESENT"
    name = "Account holder present on account maintenance certificate"
    field_name = "account_holder"


class FieldBankNamePresenceRule(_FieldPresenceRule):
    """The AMC must carry a normalized bank name."""

    id = "FLD_BANK_NAME_PRESENT"
    name = "Bank name present on account maintenance certificate"
    field_name = "bank_name"


class FieldFormalRequestSubjectPresenceRule(_FieldPresenceRule):
    """The formal request letter must state its subject/purpose.

    Real subject lines vary in exact wording across organizations (confirmed
    against 3 real samples so far -- see CONTEXT.md's Formal Request Letter
    entries), so this checks presence only, never content, the same way the
    CrossPeriodRule/CrossBranchCodeRule incidents taught not to assert an
    exact-match shape real data won't reliably satisfy.
    """

    id = "FLD_FORMAL_REQUEST_SUBJECT_PRESENT"
    name = "Subject present on formal request letter"
    field_name = "subject"
    target_document_types = frozenset({DocumentType.FORMAL_REQUEST_LETTER})
    document_label = "formal request letter"


class FieldFormalRequestOrganizationPresenceRule(_FieldPresenceRule):
    """The formal request letter must name the requesting organization.

    `organization_name` is one of FormalRequestLetterExtractor's own
    CRITICAL_FIELDS (document_analysis/constants.py) and, unlike that same
    extractor's `date` field, extracts correctly on the one real sample on
    file -- `date` is deliberately not given a presence rule here since its
    own docstring documents it as an honest, still-open extraction miss on
    that same real sample; asserting its presence would repeat the
    CrossPeriodRule mistake of a rule real data can't pass.
    """

    id = "FLD_FORMAL_REQUEST_ORGANIZATION_PRESENT"
    name = "Organization name present on formal request letter"
    field_name = "organization_name"
    target_document_types = frozenset({DocumentType.FORMAL_REQUEST_LETTER})
    document_label = "formal request letter"


class FieldAuthorityLetterOrganizationPresenceRule(_FieldPresenceRule):
    """The authority letter must name the authorizing organization.

    `organization_name` is one of AuthorityLetterExtractor's own
    CRITICAL_FIELDS and extracts non-empty on all 4 real cached samples
    (DG_Sports, GDA_Abbotabad, TMA_Khal_Dir_Lower, TMA_Lal_Dir_Upper, 4
    independent organizations) -- confirmed directly, not assumed.
    """

    id = "FLD_AUTHORITY_LETTER_ORGANIZATION_PRESENT"
    name = "Organization name present on authority letter"
    field_name = "organization_name"
    target_document_types = frozenset({DocumentType.AUTHORITY_LETTER})
    document_label = "authority letter"


class FieldAuthorityLetterFocalPersonPresenceRule(_FieldPresenceRule):
    """The authority letter must name a focal person.

    `focal_person_name` is one of AuthorityLetterExtractor's own
    CRITICAL_FIELDS and extracts non-empty on all 4 real cached samples,
    same evidence base as organization_name above. Its sibling field
    `focal_person_designation` is deliberately not given a presence rule --
    confirmed missing (None) on the TMA_Lal_Dir_Upper real sample, an honest
    extraction gap, not an absence this rule should assert against; adding
    one would repeat the CrossPeriodRule mistake of a rule real data can't
    reliably pass.
    """

    id = "FLD_AUTHORITY_LETTER_FOCAL_PERSON_PRESENT"
    name = "Focal person name present on authority letter"
    field_name = "focal_person_name"
    target_document_types = frozenset({DocumentType.AUTHORITY_LETTER})
    document_label = "authority letter"


class FieldBrdDigitizationIntentPresenceRule(_FieldPresenceRule):
    """The business requirement document must confirm digitization intent.

    `digitization_intent_confirmed` is BusinessRequirementDocumentExtractor's
    own CRITICAL_FIELDS member and extracts a clean, consistent value on all
    3 real cached samples, 3 independent organizations ("KPITB's FinTech
    Unit" / "KPITB's FIN TECH UNIT") -- anchored on a specific institutional
    name that appears near-verbatim in any real onboarding-intent statement,
    unlike its sibling field `revenue_services_listed`, which
    document_analysis/constants.py deliberately excludes from CRITICAL_FIELDS
    for the opposite reason (three structurally incompatible real phrasings,
    no safe single anchor).
    """

    id = "FLD_BRD_DIGITIZATION_INTENT_PRESENT"
    name = "Digitization intent confirmed on business requirement document"
    field_name = "digitization_intent_confirmed"
    target_document_types = frozenset({DocumentType.BUSINESS_REQUIREMENT_DOCUMENT})
    document_label = "business requirement document"


class FieldBilateralPlatformNamePresenceRule(_FieldPresenceRule):
    """The bilateral agreement must explicitly name the digital platform.

    Master Rules Section 7 requires the document to explicitly mention the
    correct digital platform terminology (PayMin / Digital Muhasil / Paymere
    BCX). `platform_name` is `BilateralAgreementExtractor`'s own field for
    this, real-sample validated 2026-08-22 -- both real samples on file use
    "PAYMIR" and extract a normalized `Paymir` value (confirmed directly via
    the extractor, not assumed). Presence-only, same convention as every
    other rule in this file: the master rule's further "parallel line-to-line
    formatting must be maintained exactly as the standard template" clause
    is not checked here -- that is a layout/formatting conformance question
    with no extraction behind it yet, out of scope for this rule.
    """

    id = "FLD_BILATERAL_PLATFORM_NAME_PRESENT"
    name = "Platform name present on bilateral agreement"
    field_name = "platform_name"
    target_document_types = frozenset({DocumentType.BILATERAL_AGREEMENT})
    document_label = "bilateral agreement"


class FieldBilateralEffectiveDatePresenceRule(_FieldPresenceRule):
    """The bilateral agreement's effective date must be present.

    Master Rules Section 7's Date Requirement ("The effective date and
    authorized person details should be checked, but dates that are required
    to remain blank must remain blank") is genuinely ambiguous about which
    reading applies to this specific field -- see CONTEXT.md's 2026-08-23
    scoping entry for the full analysis. Scope decision (Abdul, 2026-08-23):
    require presence, not blankness. Accepted, intended consequence: a
    genuinely incomplete/unexecuted agreement (the real template's own
    unfilled "day of ___, 20__" placeholder) FAILs this rule rather than
    passing it.

    `_FieldPresenceRule`, not `_DateRule` (date_rules.py), despite the
    field's name -- confirmed empirically, not assumed: `_DateRule`'s
    `_evaluate_presence()` downgrades to WARNING ("nothing to validate")
    whenever no `FieldValue` exists at all for the field on that document,
    and `RegexExtractor` never emits one when its pattern doesn't match (run
    directly against both real cached samples 2026-08-23: the blank-template
    sample's `extract_fields()` result has no `effective_date` key at all,
    not an empty one). That would have silently turned the intended FAIL
    into a WARNING for the one case this rule exists to catch.
    `_FieldPresenceRule.evaluate()` treats "no value for this field on this
    document type" as FAIL directly, which is the behavior actually wanted
    here.

    Real-sample validated 2026-08-23 against both real Bilateral Agreement
    samples on file: `Conservator_Wildlife_Peshawar_Zoo` extracts
    `effective_date: '2026-05-11'` (filled preamble) -> PASS;
    `schdule_of_charges_or_bilateral` extracts no `effective_date` at all
    (unfilled template placeholder, "on this day of , 20 ,") -> FAIL.
    """

    id = "FLD_BILATERAL_EFFECTIVE_DATE_PRESENT"
    name = "Effective date present on bilateral agreement"
    field_name = "effective_date"
    target_document_types = frozenset({DocumentType.BILATERAL_AGREEMENT})
    document_label = "bilateral agreement"


__all__ = [
    "FieldAccountHolderPresenceRule",
    "FieldAccountNumberPresenceRule",
    "FieldAuthorityLetterFocalPersonPresenceRule",
    "FieldAuthorityLetterOrganizationPresenceRule",
    "FieldBankNamePresenceRule",
    "FieldBilateralEffectiveDatePresenceRule",
    "FieldBilateralPlatformNamePresenceRule",
    "FieldBrdDigitizationIntentPresenceRule",
    "FieldFormalRequestOrganizationPresenceRule",
    "FieldFormalRequestSubjectPresenceRule",
    "FieldIbanPresenceRule",
]

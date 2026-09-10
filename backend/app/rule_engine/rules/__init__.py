"""Business rule registry.

Collects every rule instance of the module into a deterministic, ordered
registry. The registry is the single entry point the service uses to execute
the ruleset; it also exposes lookups by id and category for tests and future
drill-downs. Rules execute in registration order, which the registry keeps
stable.
"""

from app.rule_engine.constants import RULE_CATEGORY_KEYS
from app.rule_engine.rules.base import BaseRule
from app.rule_engine.rules.cross_document_rules import (
    CrossAccountHolderRule,
    CrossAccountNumberRule,
    CrossIbanRule,
)
from app.rule_engine.rules.date_rules import (
    DateCnicNotExpiredRule,
    DateDobSanityRule,
    DateExpiryPresenceRule,
    DateIssuePrecedesExpiryRule,
    DateIssuePresenceRule,
    DatePaymentRecencyRule,
    DatePeriodRangeRule,
    DatePeriodSequenceRule,
)
from app.rule_engine.rules.document_rules import (
    DocumentAmcRule,
    DocumentAuthorityLetterRule,
    DocumentBilateralRule,
    DocumentBrdRule,
    DocumentFormalRequestRule,
    DocumentOneLinkRule,
    DocumentTripartiteRule,
)
from app.rule_engine.rules.field_rules import (
    FieldAccountHolderPresenceRule,
    FieldAccountNumberPresenceRule,
    FieldAuthorityLetterFocalPersonPresenceRule,
    FieldAuthorityLetterOrganizationPresenceRule,
    FieldBankNamePresenceRule,
    FieldBilateralEffectiveDatePresenceRule,
    FieldBilateralPlatformNamePresenceRule,
    FieldBrdDigitizationIntentPresenceRule,
    FieldFormalRequestOrganizationPresenceRule,
    FieldFormalRequestSubjectPresenceRule,
    FieldIbanPresenceRule,
)
from app.rule_engine.rules.format_rules import (
    FormatAccountNumberRule,
    FormatAmountRule,
    FormatCnicRule,
    FormatDateShapeRule,
    FormatEStampRule,
    FormatIbanRule,
)
from app.rule_engine.rules.policy_rules import (
    PolicyAccountHolderRealRule,
    PolicyBalanceReconciliationRule,
    PolicyPeriodSalaryAlignedRule,
    PolicySingleCurrencyRule,
)
from app.rule_engine.rules.quality_rules import (
    QualityConfidenceFloorRule,
    QualityNoEmptyValuesRule,
    QualityNormalizedValuesCleanRule,
    QualityTransactionCountRule,
)
from app.rule_engine.rules.visual_rules import (
    VisualSignatureAmcRule,
    VisualSignatureAuthorityLetterRule,
    VisualSignatureBilateralRule,
    VisualSignatureFormalRequestRule,
    VisualSignatureOneLinkRule,
    VisualSignatureTripartiteRule,
    VisualStampAmcRule,
    VisualStampAuthorityLetterRule,
    VisualStampBilateralRule,
    VisualStampOneLinkRule,
    VisualStampTripartiteRule,
)


class RuleRegistry:
    """Ordered registry of every rule in the module."""

    def __init__(self) -> None:
        self._rules: tuple[BaseRule, ...] = (
                # Document completeness (7 registered of 8 implemented).
                # DocumentScheduleRule is implemented but deliberately not
                # registered, found 2026-08-22: SCHEDULE_OF_CHARGES is not a
                # real standalone document in this checklist -- every real
                # candidate sample found (including every file whose name
                # suggested this type) turned out to actually be a Bilateral
                # Agreement. With this rule registered, it hard-FAILed every
                # real application unconditionally (no real sample has ever
                # been splitter-classified as SCHEDULE_OF_CHARGES), the same
                # failure shape as CrossBranchCodeRule/CrossPeriodRule above.
                # Bilateral Agreement's own required-presence check
                # (DocumentBilateralRule) plus its transaction_charges field
                # already cover what this type was meant to verify. Register
                # again only if a genuine standalone real sample surfaces.
                DocumentTripartiteRule(),
                DocumentBilateralRule(),
                DocumentAmcRule(),
                DocumentOneLinkRule(),
                DocumentAuthorityLetterRule(),
                DocumentBrdRule(),
                DocumentFormalRequestRule(),
                # Required field presence (11).
                # FieldStatementPeriodPresenceRule and FieldBalancesPresenceRule
                # were removed: real Account Maintenance Certificates never
                # carry statement_period/balances (see Master Rules section 3),
                # so both could only ever hard-FAIL -- same shape as the
                # CrossBranchCodeRule removal.
                FieldIbanPresenceRule(),
                FieldAccountNumberPresenceRule(),
                FieldAccountHolderPresenceRule(),
                FieldBankNamePresenceRule(),
                FieldFormalRequestSubjectPresenceRule(),
                FieldFormalRequestOrganizationPresenceRule(),
                FieldAuthorityLetterOrganizationPresenceRule(),
                FieldAuthorityLetterFocalPersonPresenceRule(),
                FieldBrdDigitizationIntentPresenceRule(),
                FieldBilateralPlatformNamePresenceRule(),
                FieldBilateralEffectiveDatePresenceRule(),


                # Format (6).
                FormatIbanRule(),
                FormatCnicRule(),
                FormatAccountNumberRule(),
                FormatAmountRule(),
                FormatDateShapeRule(),
                FormatEStampRule(),

                # Cross-document consistency (2 registered of 4 implemented).
                # CrossBranchCodeRule is implemented but deliberately not
                # registered: its `branch_code` field has no extraction or
                # normalization support anywhere in the pipeline (unlike the
                # other cross-document fields below, which are genuinely
                # extracted), and `_CrossDocumentRule.evaluate` FAILs (not
                # WARNING/PENDING_MANUAL_REVIEW) when a participant document
                # lacks the field. Registering it today would make every real
                # application FAIL this rule permanently. Register it once
                # branch-code extraction exists.
                #
                # CrossPeriodRule is the same failure mode, found 2026-08-16
                # while adding real field extraction for BILATERAL_AGREEMENT
                # (Phase 1, docs/IMPLEMENTATION_ROADMAP.md): it compares
                # `statement_period` between ACCOUNT_MAINTENANCE_CERTIFICATE
                # and BILATERAL_AGREEMENT, but neither document actually has
                # a period in the real spec (docs/Master_Rules_Combined.md
                # Sections 3 and 7) -- AMC is a certificate, and a Bilateral
                # Agreement carries a single Effective Date, not a range.
                # Once BILATERAL_AGREEMENT got a real (honest) extractor, this
                # rule started FAILing every application unconditionally,
                # since the field it compares can never be present on either
                # side. Unregistered until a real period-like field is
                # identified for both participants, or the rule is redesigned
                # around fields that actually exist.
                CrossAccountHolderRule(),
                CrossAccountNumberRule(),
                CrossIbanRule(),

                # Date and period (8).
                DatePeriodSequenceRule(),
                DatePeriodRangeRule(),
                DateIssuePrecedesExpiryRule(),
                DatePaymentRecencyRule(),
                DateDobSanityRule(),
                DateIssuePresenceRule(),
                DateExpiryPresenceRule(),
                DateCnicNotExpiredRule(),
                # Visual verification (11).
                VisualSignatureTripartiteRule(),
                VisualSignatureAmcRule(),
                VisualSignatureOneLinkRule(),
                VisualSignatureAuthorityLetterRule(),
                VisualSignatureBilateralRule(),
                VisualSignatureFormalRequestRule(),
                VisualStampTripartiteRule(),
                VisualStampAmcRule(),
                VisualStampOneLinkRule(),
                VisualStampAuthorityLetterRule(),
                VisualStampBilateralRule(),
                # Policy compliance (4).
                PolicyAccountHolderRealRule(),
                PolicyBalanceReconciliationRule(),
                PolicySingleCurrencyRule(),
                PolicyPeriodSalaryAlignedRule(),
                # Data quality (4).
                QualityNormalizedValuesCleanRule(),
                QualityNoEmptyValuesRule(),
                QualityConfidenceFloorRule(),
                QualityTransactionCountRule(),
            )
        ids = [rule.id for rule in self._rules]
        if len(set(ids)) != len(ids):  # pragma: no cover - defensive guard
            raise ValueError("Duplicate rule ids registered")
        for rule in self._rules:
            if rule.category not in RULE_CATEGORY_KEYS:  # pragma: no cover
                raise ValueError(f"Unknown rule category {rule.category}")

    def rules(self) -> tuple[BaseRule, ...]:
        """Return every rule in stable registration order."""
        return self._rules

    def get(self, rule_id: str) -> BaseRule | None:
        """Return the rule registered under ``rule_id``, or ``None``."""
        for rule in self._rules:
            if rule.id == rule_id:
                return rule
        return None

    def by_category(self, category: str) -> tuple[BaseRule, ...]:
        """Return the rules belonging to ``category`` in registration order."""
        return tuple(rule for rule in self._rules if rule.category == category)


#: Module-level singleton consumed by the service.
REGISTRY = RuleRegistry()

__all__ = ["REGISTRY", "RuleRegistry"]

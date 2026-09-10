"""Cross-document consistency rules.

Each rule compares the normalized value of one field across a set of documents
that must agree. A participant that is entirely missing fails the rule (the
comparison cannot be made and the document set is already incomplete), as does
a participant that lacks the field, and any disagreement between the values
fails the rule outright.
"""

from app.database.models.enums import DocumentType, ValidationStatus
from app.rule_engine.rules.base import (
    BaseRule,
    RuleContext,
    RuleResult,
    normalized_values,
)

#: Category every cross-document rule belongs to.
CATEGORY = "cross_document"


class _CrossDocumentRule(BaseRule):
    """Base rule asserting one field agrees across a set of documents.

    Attributes:
        field_name: Field compared across the participating documents.
        participants: Document types that must carry the field and agree.
    """

    field_name: str
    participants: frozenset[DocumentType]

    category = CATEGORY

    def evaluate(self, context: RuleContext) -> RuleResult:
        related_documents: list[int] = []
        related_fields = [self.field_name]
        values: list[tuple[str, int]] = []
        for participant in self.participants:
            documents = context.documents_of_type(participant.value)
            related_documents.extend(documents)
            if not documents:
                return self.result(
                    ValidationStatus.FAIL,
                    f"Document {participant.value} is missing; cannot compare "
                    f"field {self.field_name}",
                    related_document_ids=sorted(related_documents),
                    related_field_names=related_fields,
                )
            participants_values = normalized_values(
                context,
                self.field_name,
                document_types={participant.value},
            )
            if not participants_values:
                return self.result(
                    ValidationStatus.FAIL,
                    f"Field {self.field_name} is missing from document "
                    f"{participant.value}",
                    related_document_ids=sorted(related_documents),
                    related_field_names=related_fields,
                )
            values.extend(
                (participants_value, document_id)
                for document_id in documents
                for participants_value in participants_values
            )

        distinct = {value for value, _ in values}
        if len(distinct) == 1:
            return self.result(
                ValidationStatus.PASS,
                f"Field {self.field_name} is consistent across the compared "
                "documents",
                related_document_ids=sorted(related_documents),
                related_field_names=related_fields,
            )
        preview = ", ".join(sorted(f"{item!r}" for item in distinct))
        return self.result(
            ValidationStatus.FAIL,
            f"Field {self.field_name} differs between documents: {preview}",
            related_document_ids=sorted(related_documents),
            related_field_names=related_fields,
        )


class CrossAccountHolderRule(_CrossDocumentRule):
    """The account holder must agree on the AMC and tripartite docs.

    BILATERAL_AGREEMENT was removed from ``participants`` 2026-08-22, the
    same failure shape already on record for ``CrossBranchCodeRule`` /
    ``CrossPeriodRule`` (see CONTEXT.md): confirmed via real-sample
    validation of ``BilateralAgreementExtractor`` (two independent real
    departments) that the real Bilateral Agreement bank-account table only
    ever has a Bank Name + Account No column, never an Account Title/Holder
    column -- so ``account_holder`` is a genuine, structural honest-miss for
    this document type, not a gap in the extractor. Since
    ``_CrossDocumentRule.evaluate`` hard-FAILs when a participant lacks the
    field, leaving Bilateral registered here would make this rule
    permanently unpassable for every real application. AMC and Tripartite
    both do extract ``account_holder`` for real (via the shared
    ``_extract_bank_account_block`` structural parser), so the comparison
    between those two remains meaningful and stays registered.
    """

    id = "CROSS_ACCOUNT_HOLDER_MATCH"
    name = "Account holder is consistent across documents"
    field_name = "account_holder"
    participants = frozenset(
        {
            DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
            DocumentType.TRIPARTITE_AGREEMENT,
        }
    )


class CrossAccountNumberRule(_CrossDocumentRule):
    """The account number must agree on the AMC, bilateral and tripartite docs."""

    id = "CROSS_ACCOUNT_NUMBER_MATCH"
    name = "Account number is consistent across documents"
    field_name = "account_number"
    participants = frozenset(
        {
            DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
            DocumentType.BILATERAL_AGREEMENT,
            DocumentType.TRIPARTITE_AGREEMENT,
        }
    )


class CrossIbanRule(_CrossDocumentRule):
    """The IBAN must agree on the AMC and the bilateral agreement."""

    id = "CROSS_IBAN_MATCH"
    name = "IBAN is consistent across documents"
    field_name = "iban"
    participants = frozenset(
        {
            DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
            DocumentType.BILATERAL_AGREEMENT,
        }
    )


class CrossPeriodRule(_CrossDocumentRule):
    """The statement period must agree on the AMC and the bilateral agreement."""

    id = "CROSS_PERIOD_MATCH"
    name = "Statement period is consistent across documents"
    field_name = "statement_period"
    participants = frozenset(
        {
            DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE,
            DocumentType.BILATERAL_AGREEMENT,
        }
    )


__all__ = [
    "CrossAccountHolderRule",
    "CrossAccountNumberRule",
    "CrossBranchCodeRule",
    "CrossIbanRule",
    "CrossPeriodRule",
]


class CrossBranchCodeRule(_CrossDocumentRule):
    """The branch code must agree on the 1LINK Form, Tripartite Agreement, and Authority Letter."""

    id = "CROSS_BRANCH_CODE_MATCH"
    name = "Branch code is consistent across documents"
    field_name = "branch_code"
    participants = frozenset(
        {
            DocumentType.ONE_LINK_LETTER,
            DocumentType.TRIPARTITE_AGREEMENT,
            DocumentType.AUTHORITY_LETTER,
        }
    )

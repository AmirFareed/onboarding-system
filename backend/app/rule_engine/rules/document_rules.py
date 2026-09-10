"""Document completeness rules.

One rule per required document type, checking that the application contains
exactly one document of that type. A missing document fails the rule and a
duplicate set fails it as well, since every required document must appear
exactly once.
"""

from app.database.models.enums import DocumentType, ValidationStatus
from app.rule_engine.rules.base import BaseRule, RuleContext, RuleResult

#: Category every document rule belongs to.
CATEGORY = "document_completeness"


class _DocumentPresenceRule(BaseRule):
    """Base rule asserting exactly one document of a type is present.

    Attributes:
        document_type: Document type the rule enforces.
    """

    document_type: DocumentType

    category = CATEGORY

    def evaluate(self, context: RuleContext) -> RuleResult:
        documents = context.documents_of_type(self.document_type.value)
        related = list(documents)
        if not documents:
            return self.result(
                ValidationStatus.FAIL,
                f"Required document {self.document_type.value} is missing",
                related_document_ids=related,
            )
        if len(documents) > 1:
            return self.result(
                ValidationStatus.FAIL,
                f"Document {self.document_type.value} is present more than once "
                f"({len(documents)} documents)",
                related_document_ids=related,
            )
        return self.result(
            ValidationStatus.PASS,
            f"Document {self.document_type.value} is present exactly once",
            related_document_ids=related,
        )


class DocumentTripartiteRule(_DocumentPresenceRule):
    """The tripartite agreement must be present exactly once."""

    id = "DOC_TRIPARTITE_PRESENT"
    name = "Tripartite agreement present"
    document_type = DocumentType.TRIPARTITE_AGREEMENT


class DocumentBilateralRule(_DocumentPresenceRule):
    """The bilateral agreement must be present exactly once.

    The rule engine treats the bilateral agreement as a required document per
    the Phase 10 specification, although Phase 4 completeness marks it optional.
    """

    id = "DOC_BILATERAL_PRESENT"
    name = "Bilateral agreement present"
    document_type = DocumentType.BILATERAL_AGREEMENT


class DocumentAmcRule(_DocumentPresenceRule):
    """The account maintenance certificate must be present exactly once."""

    id = "DOC_AMC_PRESENT"
    name = "Account maintenance certificate present"
    document_type = DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE


class DocumentOneLinkRule(_DocumentPresenceRule):
    """The One Link letter must be present exactly once."""

    id = "DOC_ONE_LINK_PRESENT"
    name = "One Link letter present"
    document_type = DocumentType.ONE_LINK_LETTER


class DocumentAuthorityLetterRule(_DocumentPresenceRule):
    """The authority letter must be present exactly once."""

    id = "DOC_AUTHORITY_LETTER_PRESENT"
    name = "Authority letter present"
    document_type = DocumentType.AUTHORITY_LETTER


class DocumentScheduleRule(_DocumentPresenceRule):
    """The schedule of charges must be present exactly once."""

    id = "DOC_SCHEDULE_OF_CHARGES_PRESENT"
    name = "Schedule of charges present"
    document_type = DocumentType.SCHEDULE_OF_CHARGES


class DocumentBrdRule(_DocumentPresenceRule):
    """The business requirement document must be present exactly once."""

    id = "DOC_BRD_PRESENT"
    name = "Business requirement document present"
    document_type = DocumentType.BUSINESS_REQUIREMENT_DOCUMENT


class DocumentFormalRequestRule(_DocumentPresenceRule):
    """The formal request letter must be present exactly once."""

    id = "DOC_FORMAL_REQUEST_PRESENT"
    name = "Formal request letter present"
    document_type = DocumentType.FORMAL_REQUEST_LETTER


__all__ = [
    "DocumentAmcRule",
    "DocumentAuthorityLetterRule",
    "DocumentBilateralRule",
    "DocumentBrdRule",
    "DocumentFormalRequestRule",
    "DocumentOneLinkRule",
    "DocumentScheduleRule",
    "DocumentTripartiteRule",
]

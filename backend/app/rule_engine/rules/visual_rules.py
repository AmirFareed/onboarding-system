"""Visual verification rules.

One rule per document/kind pair from the Phase 10 checklist, consuming the
outcomes produced by the (external) visual detection pipeline via the
``visual_detection_results`` rows. A detection outcome that found the kind
passes the rule; one that did not find it fails; a document with no detection
outcome at all goes to manual review, because the pipeline has not yet
confirmed the visual evidence.
"""

from app.database.models.enums import DocumentType, ValidationStatus
from app.rule_engine.constants import SIGNATURE_DETECTION, STAMP_DETECTION
from app.rule_engine.rules.base import BaseRule, RuleContext, RuleResult

#: Category every visual rule belongs to.
CATEGORY = "visual"


class _VisualRule(BaseRule):
    """Base rule asserting a detection kind is present on a document type.

    Attributes:
        document_type: Document type the visual check applies to.
        detection_type: Detection kind that must be present.
    """

    document_type: DocumentType
    detection_type: str

    category = CATEGORY

    def evaluate(self, context: RuleContext) -> RuleResult:
        documents = context.documents_of_type(self.document_type.value)
        related = list(documents)
        if not documents:
            return self.result(
                ValidationStatus.FAIL,
                f"Document {self.document_type.value} is missing; cannot verify "
                f"{self.detection_type.lower()}",
                related_document_ids=related,
            )
        for document_id in documents:
            if not context.has_detection(document_id, self.detection_type):
                return self.result(
                    ValidationStatus.PENDING_MANUAL_REVIEW,
                    f"No {self.detection_type.lower()} detection outcome is "
                    f"available for document id={document_id}",
                    related_document_ids=[document_id],
                )
            if not context.is_detected(document_id, self.detection_type):
                return self.result(
                    ValidationStatus.FAIL,
                    f"{self.detection_type} not detected on document id={document_id}",
                    related_document_ids=[document_id],
                )
        return self.result(
            ValidationStatus.PASS,
            f"{self.detection_type} is present on every checked document",
            related_document_ids=related,
        )


class VisualSignatureTripartiteRule(_VisualRule):
    """The tripartite agreement must carry the parties' signatures."""

    id = "VIS_SIGNATURE_TRIPARTITE"
    name = "Tripartite agreement is signed"
    document_type = DocumentType.TRIPARTITE_AGREEMENT
    detection_type = SIGNATURE_DETECTION


class VisualSignatureAmcRule(_VisualRule):
    """The account maintenance certificate must carry a bank signature."""

    id = "VIS_SIGNATURE_AMC"
    name = "Account maintenance certificate is signed"
    document_type = DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE
    detection_type = SIGNATURE_DETECTION


class VisualSignatureOneLinkRule(_VisualRule):
    """The One Link letter must carry a signature."""

    id = "VIS_SIGNATURE_ONE_LINK"
    name = "One Link letter is signed"
    document_type = DocumentType.ONE_LINK_LETTER
    detection_type = SIGNATURE_DETECTION


class VisualSignatureAuthorityLetterRule(_VisualRule):
    """The authority letter must carry a signature."""

    id = "VIS_SIGNATURE_AUTHORITY_LETTER"
    name = "Authority letter is signed"
    document_type = DocumentType.AUTHORITY_LETTER
    detection_type = SIGNATURE_DETECTION


class VisualSignatureBilateralRule(_VisualRule):
    """The bilateral agreement must carry the parties' signatures."""

    id = "VIS_SIGNATURE_BILATERAL"
    name = "Bilateral agreement is signed"
    document_type = DocumentType.BILATERAL_AGREEMENT
    detection_type = SIGNATURE_DETECTION


class VisualSignatureFormalRequestRule(_VisualRule):
    """The formal request letter must carry a signature."""

    id = "VIS_SIGNATURE_FORMAL_REQUEST"
    name = "Formal request letter is signed"
    document_type = DocumentType.FORMAL_REQUEST_LETTER
    detection_type = SIGNATURE_DETECTION


class VisualStampTripartiteRule(_VisualRule):
    """The tripartite agreement must carry a company stamp."""

    id = "VIS_STAMP_TRIPARTITE"
    name = "Tripartite agreement is stamped"
    document_type = DocumentType.TRIPARTITE_AGREEMENT
    detection_type = STAMP_DETECTION


class VisualStampAmcRule(_VisualRule):
    """The account maintenance certificate must carry a bank stamp."""

    id = "VIS_STAMP_AMC"
    name = "Account maintenance certificate is stamped"
    document_type = DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE
    detection_type = STAMP_DETECTION


class VisualStampOneLinkRule(_VisualRule):
    """The One Link letter must carry a stamp."""

    id = "VIS_STAMP_ONE_LINK"
    name = "One Link letter is stamped"
    document_type = DocumentType.ONE_LINK_LETTER
    detection_type = STAMP_DETECTION


class VisualStampAuthorityLetterRule(_VisualRule):
    """The authority letter must carry a stamp."""

    id = "VIS_STAMP_AUTHORITY_LETTER"
    name = "Authority letter is stamped"
    document_type = DocumentType.AUTHORITY_LETTER
    detection_type = STAMP_DETECTION


class VisualStampBilateralRule(_VisualRule):
    """The bilateral agreement must carry a stamp."""

    id = "VIS_STAMP_BILATERAL"
    name = "Bilateral agreement is stamped"
    document_type = DocumentType.BILATERAL_AGREEMENT
    detection_type = STAMP_DETECTION


__all__ = [
    "VisualSignatureAmcRule",
    "VisualSignatureAuthorityLetterRule",
    "VisualSignatureBilateralRule",
    "VisualSignatureFormalRequestRule",
    "VisualSignatureOneLinkRule",
    "VisualSignatureTripartiteRule",
    "VisualStampAmcRule",
    "VisualStampAuthorityLetterRule",
    "VisualStampBilateralRule",
    "VisualStampOneLinkRule",
    "VisualStampTripartiteRule",
]

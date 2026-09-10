"""Configuration validation for the completeness module.

Verification depends on the required/optional document sets being consistent.
These validators run once when the service is constructed so a misconfigured
document catalogue fails fast instead of producing misleading reports.
"""

from app.completeness.constants import (
    ALL_CONFIGURED_DOCUMENT_TYPES,
    OPTIONAL_DOCUMENT_TYPES,
    REQUIRED_DOCUMENT_TYPES,
)
from app.completeness.exceptions import InvalidDocumentConfiguration
from app.database.models.enums import DocumentType


def validate_document_configuration() -> None:
    """Ensure the required/optional document catalogue is internally consistent.

    Raises:
        InvalidDocumentConfiguration: When a configured type is not a valid
            ``DocumentType``, the required and optional sets overlap, or no
            required documents are defined.
    """
    if not REQUIRED_DOCUMENT_TYPES:
        raise InvalidDocumentConfiguration("At least one required document type must be configured")

    known = set(DocumentType)
    invalid_types = sorted(ALL_CONFIGURED_DOCUMENT_TYPES - known)
    if invalid_types:
        names = ", ".join(str(value) for value in invalid_types)
        raise InvalidDocumentConfiguration(
            f"Configured document types are not valid DocumentType values: {names}"
        )

    overlap = sorted(REQUIRED_DOCUMENT_TYPES & OPTIONAL_DOCUMENT_TYPES)
    if overlap:
        names = ", ".join(value.value for value in overlap)
        raise InvalidDocumentConfiguration(
            f"Document types cannot be both required and optional: {names}"
        )

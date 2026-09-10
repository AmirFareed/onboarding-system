"""Constants for the upload module.

Centralizes the document-type storage layout, the allowed file formats and the
size limits enforced by the validators. Values are derived from the canonical
:class:`app.database.models.enums.DocumentType` enum rather than hard-coded
strings so the storage layer and the database stay in sync automatically.
"""

from app.database.models.enums import DocumentType

#: Storage sub-directory slug for every supported document type. The directory
#: names are stable, human-readable and decoupled from the enum values.
DOCUMENT_TYPE_SLUGS: dict[DocumentType, str] = {
    DocumentType.TRIPARTITE_AGREEMENT: "tripartite",
    DocumentType.BILATERAL_AGREEMENT: "bilateral",
    DocumentType.ACCOUNT_MAINTENANCE_CERTIFICATE: "account_maintenance",
    DocumentType.ONE_LINK_LETTER: "one_link",
    DocumentType.AUTHORITY_LETTER: "authority",
    DocumentType.SCHEDULE_OF_CHARGES: "schedule_of_charges",
    DocumentType.BUSINESS_REQUIREMENT_DOCUMENT: "business_requirement",
    DocumentType.FORMAL_REQUEST_LETTER: "formal_request",
    DocumentType.OTHER_SUPPORTING_DOCUMENT: "other",
    DocumentType.CNIC_FRONT: "cnic_front",
    DocumentType.CNIC_BACK: "cnic_back",
    DocumentType.BULK_UPLOAD: "bulk",
}

#: Maximum number of copies an application may hold per document type. Types
#: missing from this map are limited to a single copy. Multiple copies are a
#: business requirement: e.g. three 1-Link forms are uploaded per application.
#:
#: SCHEDULE_OF_CHARGES's 6-copy entry removed 2026-08-22: it is no longer a
#: required checklist type (see completeness/constants.py and CONTEXT.md),
#: so the business rationale for a generous multi-copy cap no longer applies
#: -- it now falls back to the default 1-copy limit like any other
#: non-required type. DOCUMENT_TYPE_SLUGS above deliberately keeps its entry:
#: that dict is a plain lookup (``DOCUMENT_TYPE_SLUGS[document_type]``, no
#: default) used for storage regardless of required-checklist status, and the
#: splitter's title-phrase entry for this type is deliberately left in place
#: (see preprocessing/splitter.py) -- removing the slug would crash storage
#: if the splitter ever did classify a real page as this type.
MAX_COPIES_BY_DOCUMENT_TYPE: dict[DocumentType, int] = {
    DocumentType.ONE_LINK_LETTER: 3,
    DocumentType.TRIPARTITE_AGREEMENT: 3,
}

#: Filename extensions accepted for upload, lower case with a leading dot.
ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
)

#: Expected media types per allowed extension.
MIME_TYPES_BY_EXTENSION: dict[str, frozenset[str]] = {
    ".pdf": frozenset({"application/pdf"}),
    ".doc": frozenset({"application/msword"}),
    ".docx": frozenset(
        {
            ("application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document")
        }
    ),
    ".png": frozenset({"image/png"}),
    ".jpg": frozenset({"image/jpeg"}),
    ".jpeg": frozenset({"image/jpeg"}),
    ".tif": frozenset({"image/tiff"}),
    ".tiff": frozenset({"image/tiff"}),
}

#: Extensions that can carry each media type (inverse of the map above).
EXTENSIONS_BY_MIME_TYPE: dict[str, frozenset[str]] = {}
for _extension, _mime_types in MIME_TYPES_BY_EXTENSION.items():
    for _mime in _mime_types:
        EXTENSIONS_BY_MIME_TYPE.setdefault(_mime, set()).add(_extension)
EXTENSIONS_BY_MIME_TYPE = {
    key: frozenset(value) for key, value in EXTENSIONS_BY_MIME_TYPE.items()
}

#: Media types the pipeline understands. A declared type outside this set is
#: rejected outright even when the bytes look like a supported format.
ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        mime
        for mimes in MIME_TYPES_BY_EXTENSION.values()
        for mime in mimes
    }
)

#: Generic media types that carry no format information; the sniffed content is
#: authoritative when one of these is declared.
GENERIC_MIME_TYPES: frozenset[str] = frozenset(
    {"", "application/octet-stream", "binary/octet-stream"}
)

#: Magic byte sequences used to sniff the real file format. Each sequence maps
#: to the extension whose format it identifies. The ``.tmp`` suffix sentinel is
#: never used; entries are matched by prefix so short/truncated files are
#: recognised as long as their header is intact.
MAGIC_BYTES: dict[bytes, str] = {
    b"%PDF-": ".pdf",
    b"\x89PNG\r\n\x1a\n": ".png",
    b"\xff\xd8\xff": ".jpg",
    b"II*\x00": ".tif",
    b"MM\x00*": ".tif",
    b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1": ".doc",
    b"PK\x03\x04": ".docx",
}

#: Number of leading bytes read to sniff the file format.
SNIFF_BYTES = 16

#: Bytes read per chunk while streaming an upload to disk.
READ_CHUNK_BYTES = 1024 * 1024

#: Base name used for application storage folders, e.g. ``APP-000001``.
APPLICATION_FOLDER_PREFIX = "APP-"

#: Sub-path under the storage root where uploaded documents live.
APPLICATIONS_DIRECTORY = "applications"

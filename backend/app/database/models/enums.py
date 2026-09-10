"""Domain enums shared by the ORM models.

Each enum maps to a native PostgreSQL ``ENUM`` type via SQLAlchemy. Native enum
types enforce allowed values at the database level (data integrity) while the
Python ``Enum`` classes keep the values strongly typed in application code. The
enum type name derives from the class name in lower case; when a new value is
added to an enum that already exists in a production database, a dedicated
migration must ``ALTER TYPE`` the enum.
"""

from enum import StrEnum


class ApplicationStatus(StrEnum):
    """Lifecycle state of a verification application."""

    SUBMITTED = "SUBMITTED"
    PROCESSING = "PROCESSING"
    PROCESSING_FAILED = "PROCESSING_FAILED"
    PENDING_REVIEW = "PENDING_REVIEW"
    NEEDS_DOCUMENTS = "NEEDS_DOCUMENTS"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CORRECTED = "CORRECTED"


class DocumentType(StrEnum):
    """Document categories accepted by the verification pipeline.

    The values mirror the checklist item families (signatures and stamps) that
    are verified for each financial document.
    """

    TRIPARTITE_AGREEMENT = "TRIPARTITE_AGREEMENT"
    BILATERAL_AGREEMENT = "BILATERAL_AGREEMENT"
    ACCOUNT_MAINTENANCE_CERTIFICATE = "ACCOUNT_MAINTENANCE_CERTIFICATE"
    ONE_LINK_LETTER = "ONE_LINK_LETTER"
    AUTHORITY_LETTER = "AUTHORITY_LETTER"
    SCHEDULE_OF_CHARGES = "SCHEDULE_OF_CHARGES"
    BUSINESS_REQUIREMENT_DOCUMENT = "BUSINESS_REQUIREMENT_DOCUMENT"
    FORMAL_REQUEST_LETTER = "FORMAL_REQUEST_LETTER"
    OTHER_SUPPORTING_DOCUMENT = "OTHER_SUPPORTING_DOCUMENT"
    CNIC_FRONT = "CNIC_FRONT"
    CNIC_BACK = "CNIC_BACK"
    BULK_UPLOAD = "BULK_UPLOAD"


class DocumentProcessingStatus(StrEnum):
    """State of a document within the processing pipeline."""

    UPLOADED = "UPLOADED"
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ValidationStatus(StrEnum):
    """Outcome of a validation rule check."""

    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    PENDING_MANUAL_REVIEW = "PENDING_MANUAL_REVIEW"


class Severity(StrEnum):
    """Importance level of a validation result."""

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class ReviewDecision(StrEnum):
    """Decision taken by a human reviewer."""

    APPROVE = "APPROVE"
    CORRECT = "CORRECT"
    REJECT = "REJECT"


class JobStatus(StrEnum):
    """Lifecycle state of a bulk processing queue job.

    A job moves ``QUEUED -> PROCESSING -> COMPLETED`` when successful. A
    recoverable failure schedules the job as ``RETRY_WAITING`` (claimable again
    after ``retry_at``); a failure that exhausts the attempt budget, or a stale
    ``PROCESSING`` job recovered after a worker crash, becomes ``FAILED``. The
    unique document id on a job guarantees one job per document, so a document
    can never be queued twice.
    """

    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRY_WAITING = "RETRY_WAITING"


class JobType(StrEnum):
    """What a queue job does when claimed.

    ``DOCUMENT_OCR`` processes one document (the original, and only, job kind).
    ``APPLICATION_PIPELINE`` runs analysis, confidence, normalization and rule
    validation for a whole application, once every one of its ``DOCUMENT_OCR``
    jobs has reached a terminal state. It is enqueued automatically, never by a
    document upload, so it carries no ``document_id``.
    """

    DOCUMENT_OCR = "DOCUMENT_OCR"
    APPLICATION_PIPELINE = "APPLICATION_PIPELINE"


class ValidationEventType(StrEnum):
    """Every kind of application-level event the validation history records.

    History rows are append-only: each event creates a new row so repeated
    document submissions and repeated operator checks preserve their full
    history instead of overwriting earlier records.
    """

    DOCUMENTS_REQUESTED = "DOCUMENTS_REQUESTED"
    DOCUMENTS_RECEIVED = "DOCUMENTS_RECEIVED"
    OPERATOR_SUBMITTED = "OPERATOR_SUBMITTED"
    OPERATOR_REJECTED = "OPERATOR_REJECTED"
    SUBMITTED_FOR_PROCESSING = "SUBMITTED_FOR_PROCESSING"
    PROCESSING_FAILED = "PROCESSING_FAILED"
    REVIEW_APPROVED = "REVIEW_APPROVED"
    REVIEW_CORRECTED = "REVIEW_CORRECTED"
    REVIEW_REJECTED = "REVIEW_REJECTED"

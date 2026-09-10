"""Regression test for the single-upload technical-validation gap.

Before this fix, UploadService.upload() never called TechnicalValidationService,
so a single-uploaded document had no stored PASS result and
DocumentProcessingService.process_one() permanently SKIPPED it -- it could
never reach OCR, let alone the Phase 4 pipeline. The bulk-upload path had this
fixed already (validates lazily inside process_one after splitting); single
upload never did.

Uses bank-statement-shaped content on purpose, not because that's realistic
production content for every document type, but because document_analysis's
classifier only recognizes 4 categories (bank statement/payslip/ID/tax
document) -- see CONTEXT.md's "Known gaps". This test proves the mechanical
fix (validation -> OCR -> pipeline trigger) works; it deliberately does not
claim to prove every document type reaches a report, which is a separate,
already-tracked gap.
"""

from app.database.models.enums import JobStatus, JobType
from app.database.connection import SessionLocal
from app.database.models.queue_job import QueueJob
from sqlalchemy import select

from app.bulk_queue.workers import drain_queue
from tests.test_bulk_upload_api import make_bulk_pdf
from tests.test_document_analysis_api import BANK_STATEMENT_TEXT
from tests.test_technical_validation_api import create_application

API = "/api/v1"


def upload_single_with_content(client, application_id: int, document_type: str, content: bytes):
    """Upload a single document via the real API with custom content."""
    return client.post(
        f"{API}/applications/{application_id}/documents",
        data={"document_type": document_type},
        files={"file": ("statement.pdf", content, "application/pdf")},
    )


def test_single_upload_reaches_a_working_report(authenticated_client):
    application_id = create_application(authenticated_client)
    response = upload_single_with_content(
        authenticated_client,
        application_id,
        "TRIPARTITE_AGREEMENT",
        make_bulk_pdf([BANK_STATEMENT_TEXT]),
    )
    assert response.status_code == 201, response.text

    start = authenticated_client.post(f"{API}/applications/{application_id}/processing/start")
    assert start.status_code == 200, start.text

    for _ in range(3):
        summary = drain_queue()
        if summary.processed == 0:
            break

    db = SessionLocal()
    try:
        document_job = db.scalars(
            select(QueueJob).where(
                QueueJob.application_id == application_id,
                QueueJob.job_type == JobType.DOCUMENT_OCR,
            )
        ).one()
    finally:
        db.close()

    # The actual bug: this used to be SKIPPED forever, never COMPLETED.
    assert document_job.status is JobStatus.COMPLETED, document_job.last_error

    pipeline_job = db_pipeline_job_for(application_id)
    assert pipeline_job is not None, "pipeline never triggered for a single upload"
    assert pipeline_job.status is JobStatus.COMPLETED, pipeline_job.last_error

    report = authenticated_client.get(f"{API}/applications/{application_id}/validation-report")
    assert report.status_code == 200, report.text


def db_pipeline_job_for(application_id: int):
    db = SessionLocal()
    try:
        return db.scalars(
            select(QueueJob).where(
                QueueJob.application_id == application_id,
                QueueJob.job_type == JobType.APPLICATION_PIPELINE,
            )
        ).one_or_none()
    finally:
        db.close()

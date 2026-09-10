# Resubmission Workflow Fix Report

**Date:** 2026-08-21
**Status:** Fix implemented, tests passing, no commit.

---

## Root Cause

In `upload/services.py::upload_bulk()`, `ApplicationRepository.update()` mutates the application object **in-place** (`application.status = status`). The code changes status from `NEEDS_DOCUMENTS` to `PROCESSING` **before** calling `_record_documents_received()`. By the time the receipt-recording method checks `application.status`, it already sees `PROCESSING` instead of `NEEDS_DOCUMENTS`, so it returns without recording the `DOCUMENTS_RECEIVED` event.

This means any resubmission via the bulk-upload path silently lost the receipt event, leaving `DOCUMENTS_REQUESTED` events permanently unmatched — and Performance had no waiting-span evidence to display.

The single-document `upload()` method was **not** affected (it doesn't change status before calling the receipt method), but the bulk-upload path — which is the primary upload mechanism — was broken.

---

## Production Changes

| File | Change | Why |
|------|--------|-----|
| `backend/app/upload/services.py` | Moved `_record_documents_received()` call **before** the status update in `upload_bulk()` | The `application` object is mutated in-place by `update()`, so the receipt must be recorded while the status is still `NEEDS_DOCUMENTS` |

No other production files were modified.

---

## Tests

All tests exercise the **real service/workflow path** (API calls + direct service verification), not direct database insertion.

```
Initial submission regression:            PASS
Missing-document request:                 PASS
Single resubmission:                      PASS
Multiple resubmissions:                   PASS
Open request:                             PASS
Initial bulk upload does not create false receipt: PASS
Performance calculation:                  PASS
Application History timeline:             PASS
```

| Test | What it verifies |
|------|-----------------|
| `test_initial_upload_creates_no_document_request_or_receipt` | Fresh upload on SUBMITTED app produces no DOCUMENTS_REQUESTED or DOCUMENTS_RECEIVED |
| `test_operator_request_creates_documents_requested` | Operator request creates correct event with missing types, actor, reason |
| `test_resubmission_records_documents_received` | Upload while NEEDS_DOCUMENTS creates DOCUMENTS_RECEIVED with correct metadata |
| `test_multiple_resubmission_cycles_are_tracked_independently` | Two request/receipt pairs produce 2 requests, 2 receipts, in chronological order |
| `test_open_request_has_no_received_event` | Unmatched request has no receipt, no fabricated data |
| `test_initial_bulk_upload_does_not_create_false_receipt` | Initial upload does not generate false DOCUMENTS_RECEIVED |
| `test_performance_waiting_span_matches_workflow_events` | Performance waiting_seconds ≥ 1, resubmissions=1, cycles=1, evidence span exists |
| `test_application_history_timeline_includes_request_and_receipt` | Timeline contains DOCUMENTS_REQUESTED and DOCUMENTS_RECEIVED in chronological order |

---

## Data Flow (Verified)

```
Operator request-documents API
  → status = NEEDS_DOCUMENTS
  → DOCUMENTS_REQUESTED recorded in application_validation_history

Applicant upload (single or bulk)
  → _record_documents_received() fires (status is NEEDS_DOCUMENTS)
  → DOCUMENTS_RECEIVED recorded in application_validation_history
  → status transitions to PROCESSING

Performance service
  → _waiting_spans() matches DOCUMENTS_REQUESTED → DOCUMENTS_RECEIVED
  → waiting_seconds = receipt.timestamp - request.timestamp
  → waiting_spans contains the evidence

Application History service
  → timeline merges DOCUMENTS_REQUESTED + DOCUMENTS_RECEIVED events
  → Frontend groups them into resubmission cycles
```

---

## Safety Confirmation

- ✅ No false waiting time for initial uploads (Test 1 + Test 6)
- ✅ No fabricated history events (Test 5)
- ✅ No database migration needed
- ✅ Existing access control unchanged
- ✅ Existing OCR/extraction untouched
- ✅ Existing AMC extraction untouched
- ✅ Frontend tests: 97/97 passing
- ✅ ESLint: 0 errors (4 pre-existing warnings)
- ✅ Build: clean
- ✅ No commit
- ✅ No push

---

## Baseline Failures (Pre-existing, Unrelated)

The `test_document_analysis_api.py` 13-failure `TECH_BLANK_PAGE` baseline (documented in CONTEXT.md) is unchanged and unrelated to this fix.

---

## Existing Test Results

| Suite | Result |
|-------|--------|
| `test_resubmission_workflow.py` (new) | **8/8 passed** |
| `test_performance_api.py` (existing) | **9/9 passed** |
| `test_application_history_api.py` (existing) | **24/24 passed** |
| `test_operator_workflow_api.py` (existing) | **13/13 passed** |
| Frontend (all) | **97/97 passed** |

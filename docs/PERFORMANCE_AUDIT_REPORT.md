# Performance Waiting-Time Audit Report

**Date:** 2026-08-20
**Scope:** Diagnostic — no code changes made.

---

## 1. Root Cause

**Classification: C — Correct behavior.**

Application #9619 (GDC Madyan Swat) genuinely has no `DOCUMENTS_REQUESTED` → `DOCUMENTS_RECEIVED` cycle data. The `application_validation_history` table contains **zero events** for this application. The backend correctly reports what exists; there is no calculation bug or frontend consumption bug.

### Why no validation_history events exist

The bulk-upload path in `upload/services.py::upload_bulk()` does the following:

1. Creates the application with status `SUBMITTED`
2. Creates a `BULK_UPLOAD` placeholder document
3. Enqueues splitting/OCR jobs
4. **Transitions `SUBMITTED → PROCESSING`** (line 277-280)
5. Calls `_record_documents_received()` — but this method **returns immediately** when `application.status is not NEEDS_DOCUMENTS` (line 298-299)

The status was already changed to `PROCESSING` in step 4, so step 5 never records anything. This is by design: `DOCUMENTS_RECEIVED` only fires when an operator explicitly requests documents (setting status to `NEEDS_DOCUMENTS`) and the applicant then uploads them.

`DOCUMENTS_REQUESTED` events are only created by the operator workflow (`operator_workflow/services.py::request_documents()`), which was never invoked for either application.

**Both applications in the dev database followed the same path:** bulk upload from `SUBMITTED` → `PROCESSING`, no operator intervention, no document requests, no receipts, no reviews.

---

## 2. Evidence — Data Comparison

### Raw database state

| Table | App #9618 | App #9619 |
|-------|-----------|-----------|
| `application_validation_history` | 0 events | 0 events |
| `human_reviews` | 0 reviews | 0 reviews |
| `queue_jobs` | 1 (PROCESSING, open) | 6 (1 COMPLETED, 5 QUEUED) |
| `documents` | 1 (BULK_UPLOAD) | 6 (1 BULK_UPLOAD + 5 split) |
| `applications.status` | PROCESSING | PROCESSING |

### Performance API response (masked)

| Field | App #9618 | App #9619 |
|-------|-----------|-----------|
| `waiting_seconds` | null | null |
| `processing_seconds` | null | 98 |
| `review_seconds` | null | null |
| `total_turnaround_seconds` | null | null |
| `resubmissions` | 0 | 0 |
| `missing_document_cycles` | 0 | 0 |
| `waiting_spans` | (empty) | (empty) |
| `processing_spans` | 1 (open, DOCUMENT_OCR) | 1 (closed, DOCUMENT_OCR, 98s) |
| `review_spans` | (empty) | (empty) |

### Application History timeline (masked)

**App #9618** — 2 events:
1. `APPLICATION_CREATED` @ submitted_at
2. `DOCUMENT_UPLOADED` (BULK_UPLOAD copy 1)

**App #9619** — 7 events:
1. `APPLICATION_CREATED` @ submitted_at
2. `DOCUMENT_UPLOADED` (BULK_UPLOAD copy 1)
3-7. `DOCUMENT_UPLOADED` × 5 (split documents: AMC ×1, ONE_LINK_LETTER ×3, OTHER ×1)

Zero `DOCUMENTS_REQUESTED`, zero `DOCUMENTS_RECEIVED`, zero `PROCESSING_COMPLETED`, zero `REVIEW_DECISION` events in either timeline.

---

## 3. Performance vs Application History Consistency

**Both layers agree.** There are no cycle events, so:
- Application History shows no cycle grouping (correct — no `DOCUMENTS_REQUESTED` events to group)
- Performance shows no waiting spans (correct — `_waiting_spans()` finds no `DOCUMENTS_REQUESTED` entries)
- Performance shows processing spans from queue jobs (correct — `_processing_spans()` reads `queue_jobs`)
- Performance shows no review spans (correct — no `APPLICATION_PIPELINE` completed job, no `human_reviews`)

The two views are telling the same factual story. The issue is not a data inconsistency — it is a **data scarcity** problem: the dev database lacks applications that have been through the operator document-request workflow.

---

## 4. Backend Cycle-Matching Implementation

Reading `performance/services.py::_waiting_spans()`:

- **Matching logic:** Iterates chronological `ValidationHistoryEntry` list. `DOCUMENTS_REQUESTED` opens a span; the next `DOCUMENTS_RECEIVED` closes it.
- **Multiple requests:** A second `DOCUMENTS_REQUESTED` while one is open supersedes it — the earlier span is closed as open/unanswered, and a new span starts.
- **Superseded requests:** Explicitly handled — the earlier span is recorded with `open=True` and detail "Request unanswered; superseded by a later request".
- **Unmatched/open requests:** An unmatched `DOCUMENTS_REQUESTED` at the end of the list becomes an open span (`end=None, duration_seconds=None, open=True`).
- **Processing applications:** Open spans are included (they appear in `waiting_spans` with `open=True`). The `now` parameter is used as the reference time.
- **Timestamp used:** `application.submitted_at` is the application creation time. `DOCUMENTS_REQUESTED.created_at` starts waiting spans. `DOCUMENTS_RECEIVED.created_at` closes them.
- **Completed application required?** No. The function works on any application's history entries regardless of status.
- **Status filtering:** The `list_applications` endpoint accepts an optional `status` filter, but the breakdown calculation itself does not filter by status.

This implementation is consistent with the cycle semantics in `docs/PHASE2_CHECKPOINT.md` and the Application History service.

---

## 5. Loading UX Audit

### Current behavior

The `usePerformance` hook fires two parallel requests on mount:
1. `GET /performance/overview` → sets `overviewLoading` / `overview`
2. `GET /performance/applications` → sets `loading` / `rows`

The page renders:
- **Summary cards:** Spinner shown only when `overviewLoading && !overview` (first load). Once `overview` arrives, cards render even during refresh.
- **Table:** Spinner shown only when `loading && rows.length === 0` (first load). Once rows arrive, the table renders even during refresh.

### Findings

1. **The whole page is NOT blocked unnecessarily.** The overview and table have independent loading states. The summary cards can render before the table finishes, and vice versa.
2. **The overview endpoint is heavier than necessary.** `PerformanceService._load_all()` (used by `overview()`) fetches ALL applications with limit=10,000, plus all their history/reviews/jobs — a single bulk query per table. The per-application endpoint (`list_applications`) uses the more efficient `search()` with pagination. For a small dev database (2 apps) this is negligible; at production scale the overview could become the bottleneck.
3. **Cause is API architecture, not latency.** Both endpoints return quickly for 2 applications. The loading state is correct — it just happens to be brief. No improvement needed for the current scale.

---

## 6. Recommended Fix

### 1. Backend fix: None required

The backend calculation is correct. The data simply does not contain cycle events. No code change is needed for the calculation itself.

### 2. Frontend fix: None required

The frontend correctly displays what the API returns. No consumption bug exists.

### 3. Data improvement (the actual gap)

To validate cycle-grouping UX, the dev database needs applications that have been through the operator document-request workflow. Options:

- **Manual test:** Use the operator workflow API (`POST /applications/{id}/operator/request-documents`) to create `DOCUMENTS_REQUESTED` events on an existing application, then upload documents to trigger `DOCUMENTS_RECEIVED`.
- **Seed script:** Create a dedicated test-data seed that inserts validation_history events covering all 8 checkpoint scenarios (clean, 1 cycle, multiple cycles, open request, rejected, approved, many documents, no cycle data).

### 4. Loading UX improvement (optional, future)

The `overview()` endpoint could be made lighter by computing aggregates from the paginated `search()` results instead of loading all 10,000 applications. This is a performance optimization, not a correctness fix.

---

## 7. Files That Would Need Changing (if fixes are implemented)

For data seeding (recommended next step):
- `backend/scripts/seed_cycle_test_data.py` (new file)

For overview optimization (optional future):
- `backend/app/performance/services.py` — `PerformanceService.overview()` and `_load_all()`

For loading UX improvement (optional future):
- `frontend/src/hooks/usePerformance.js` — could split overview/table into independent mount effects

---

## 8. Tests Required

| Scenario | Expected behavior |
|----------|-------------------|
| No cycle events | Zero applicant waiting, zero cycles |
| One completed `DOCUMENTS_REQUESTED → DOCUMENTS_RECEIVED` | Waiting duration appears, resubmissions=1, cycles=1 |
| Multiple completed cycles | All waiting spans represented, resubmissions=N, cycles=N |
| Open `DOCUMENTS_REQUESTED` (no receipt) | Open span shown, not counted in closed total |
| Processing application with cycle data | Waiting spans shown alongside open processing spans |
| Application History and Performance agree | Same cycle count, same waiting duration |

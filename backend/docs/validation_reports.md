# Validation Report Module (Phase 11)

## Overview

The validation report turns the **stored results of every earlier pipeline
stage** into a structured, printable document for the employee review desk.
Where each earlier phase answers one question ("can we trust the bytes? the
text? the fields? the canonical values? the business rules?"), this module asks
*"what do all of them say about this application, taken together?"*.

It lives in `backend/app/reports/` and is deliberately **read-only**:

- it never runs a rule, never runs a detection, never re-scans an image;
- it never writes to the database (no new tables, no migration, no status
  updates);
- it is generated on demand and deterministically — calling it twice with the
  same stored data yields the same report (only the timestamp differs).

The report is the seam between the automated pipeline and the human decision.
Phase 12 (human verification) will consume the same view: the report tells the
reviewer *what* to look at and *why*, and the reviewer's decisions flow back
through the existing `human_reviews` / `human_corrections` / `feedback_dataset`
tables.

## Why a separate module

- The pipeline stages write raw facts; the report is a presentation and
  decision-support layer with its own vocabulary (report version, overall
  status, groups, recommendations).
- Aggregation logic is pure and database-free where possible, so the status
  derivation, the category grouping and the recommendation table are unit-testable
  without fixtures.
- Reusing the existing repositories behind a single facade keeps the module
  self-contained without owning any data.
- The report does not leak storage or internal details: the API contract
  (`schemas.py`) is independent of the ORM.

## Architecture

```
reports/
  constants.py    REPORT_VERSION, ReportOverallStatus + precedence, the 8 groups,
                  category-to-group mapping, recommendation table (13 codes)
  exceptions.py   ReportError, ApplicationNotFound, NoValidationResults,
                  ReportGenerationFailed, InvalidReportRequest
  schemas.py      Pydantic request/response models (report, summary, error)
  validators.py   Pure helpers: group_label(), derive_overall_status(),
                  build_recommendations()  -- no database access
  repositories.py Read-only facade re-exporting the existing repositories
  services.py     ValidationReportService (aggregation, status, HTML rendering)
  routes.py       GET validation-report, validation-report/html, validation-summary
templates/
  validation_report.html   Printable HTML report (Jinja2)
```

### Data sources (all read-only)

| Report section | Stored data |
| --- | --- |
| Application information | `applications` |
| Document summary | `documents`, `ocr_results`, `document_analysis_results`, technical `validation_results` |
| Extraction summary | `extracted_fields` (verification status, confidence) |
| Business rule summary | `validation_results` rows in the eight rule-engine categories |
| Visual detection summary | `visual_detection_results` |
| Overall status + recommendations | derived from the above |

The eight business rule groups are a reorganization of the eight rule-engine
categories. `field_presence` folds into `document_completeness` (the "Document
Validation" group); the `visual` category splits by rule-id prefix into
"Signature Validation" and "Stamp Validation". The mapping lives in
`RULE_CATEGORY_GROUPS` and `VISUAL_SIGNATURE_PREFIX` / `VISUAL_STAMP_PREFIX`
in `constants.py`.

## Overall status

`ReportOverallStatus` has four values with strictest-first precedence:

```
REJECTED > FAILED > MANUAL_REVIEW_REQUIRED > APPROVED
```

- **REJECTED** — `applications.status == REJECTED`. This is an external human
  decision and always wins, regardless of the stored validation rows. The
  report derives the verdict but never writes it: status transitions are owned
  by the review flow, not by the report.
- **FAILED** — any stored rule row **or** technical validation row has status
  `FAIL` (or `ERROR`).
- **MANUAL_REVIEW_REQUIRED** — any stored rule row has status
  `PENDING_MANUAL_REVIEW`.
- **APPROVED** — everything else. **Warnings are informational and never block
  approval.**

The precedence and the REJECTED-wins rule are unit-tested in
`tests/test_reports_engine.py`.

## Recommendations

`build_recommendations()` returns a deterministic, ordered list of actionable
recommendations. The 13 codes and their messages are data in
`RECOMMENDATION_TEMPLATES` / `RECOMMENDATION_ORDER`; each entry expands at
generation time with the affected document types (e.g. the missing-document
recommendation lists which required documents are absent). `NO_ACTION_REQUIRED`
appears only when no other recommendation applies (i.e. an approved report).

Recommendation triggers are computed from the stored data in `services.py`:

- `MISSING_REQUIRED_DOCUMENT` — any `DOC_*` rule failed;
- `MISSING_SIGNATURE` / `MISSING_STAMP` — any `VIS_SIGNATURE_*` / `VIS_STAMP_*`
  rule failed;
- `*_INCONSISTENCY` — the corresponding `CROSS_*` rule failed;
- `BALANCE_RECONCILIATION` — `POL_BALANCE_RECONCILIATION` failed;
- `VERIFY_BLURRED_DOCUMENTS` — a technical validation row failed with a message
  containing `"Blur score"` (`BLUR_MESSAGE_MARKER`);
- `CORRECT_LOW_CONFIDENCE` — any field is below `CONFIDENCE_FLOOR` (0.5) or is
  `PENDING_REVIEW` / `CANNOT_VERIFY`;
- `REVIEW_DATES` — any date-category rule failed;
- `COMPLETE_PENDING_REVIEW` — any rule row is `PENDING_MANUAL_REVIEW`
  (independent of the overall status, so a failed-and-pending application still
  tells the reviewer the pending items exist);
- `NO_ACTION_REQUIRED` — approved, nothing else applies.

## API

All endpoints live under `/api/v1/applications/{application_id}` and are
registered through `app/api/__init__.py` as the `reports` router.

| Endpoint | Description |
| --- | --- |
| `GET .../validation-report` | Full structured report (JSON). |
| `GET .../validation-report/html` | Same report rendered from the Jinja2 template (printable HTML). |
| `GET .../validation-summary` | Condensed headline totals + overall status for dashboards. |

Error behaviour (via `_handle_report_errors`):

| HTTP | Meaning |
| --- | --- |
| 404 | `ApplicationNotFound` — application id does not exist. |
| 422 | `NoValidationResults` — no business rule rows stored; run `POST .../validate` first. Technical-validation rows alone do not satisfy the report. |
| 500 | `ReportGenerationFailed` — aggregation or template rendering failed. |

## HTML report

The printable report (`templates/validation_report.html`) is styled for A4
with `@media print` rules. It shows the status banner, application information,
document table, extraction stats, the per-group business rule table, the visual
detection summary and the recommendation list. The same Pydantic model that the
JSON endpoint returns is passed to the template, so a future PDF exporter can
consume either representation without the aggregation logic changing.

## Phase 12 integration

Phase 12 (Human Verification) will reuse this read-only view as its starting
point. Nothing in the report writes back; reviewer decisions continue to be
persisted through the existing `human_reviews`, `human_corrections` and
`feedback_dataset` tables, and the report regenerates to reflect them.

## Future work

- PDF export (wkhtmltopdf / weasyprint) from the existing HTML.
- Caching/versioning of generated reports for a permanent audit trail.
- Drill-down links from group totals to the underlying validation rows.

# Feedback Module (Phase 13)

## Overview

The feedback module is the system's **continuous learning dataset interface**:
it exposes the human-corrected field data that accumulated during Phases 8-12 so
it can be inspected, aggregated, exported, and eventually used to improve the
extraction pipeline. It is deliberately read-mostly — it performs no OCR,
validation, normalization, or review of its own; it reads the `feedback_dataset`
table that the confidence and human-verification modules write to.

Every time an employee corrects or approves a field during human review, the
pipeline appends a feedback entry capturing the original OCR value, the
normalized value, and the human-corrected value side by side. This is the raw
material for future AI training / fine-tuning.

It lives in `backend/app/feedback/`.

## Architecture

```
feedback/
  constants.py   Versions, origins, decision sets, export formats, CSV contract
  exceptions.py  FeedbackError(500), FeedbackNotFound(404), InvalidFilter(422), ExportFailed(500)
  schemas.py     Pydantic request/response models (FeedbackEntry, FeedbackSummary, ...)
  validators.py  Pure filter validation, ORM->dict mapping, CSV serialization
  repositories.py  Facade re-exporting the FeedbackRepository
  services.py    FeedbackService: listing, single lookup, statistics, exports
  routes.py      GET /feedback, GET /feedback/{id}, GET /feedback/statistics,
                 GET /feedback/export/json, GET /feedback/export/csv
```

Pure helpers (filter validation, datetime normalization, entry mapping, CSV
building) live in `validators.py` so they are unit-testable without a database;
the service orchestrates them against the repository.

## Data model & provenance

The module reuses the single existing `feedback_dataset` table — it does not
create another feedback table and never duplicates stored corrections. Each row
exposes these fields:

| Field | Meaning |
| --- | --- |
| `id` | Feedback entry id |
| `application_id` | Application the entry belongs to |
| `document_id` | Document the corrected field came from (nullable) |
| `ocr_result_id` | OCR result the field came from (nullable) |
| `field_name` | The extracted field name (e.g. `account_number`) |
| `original_ocr_value` | Raw value as OCR/extraction produced it |
| `normalized_value` | Normalized form used for comparison |
| `human_corrected_value` | Final value after human review (or the original if approved) |
| `confidence_score` | Field confidence at evaluation time |
| `confidence_source` | Dominant confidence source (`regex`/`template`/`ocr`/`ai`) |
| `correction_reason` | Why the field was corrected (nullable) |
| `reviewer` | The human reviewer who reviewed the field |
| `decision` | `APPROVE`, `CORRECT`, `REJECT`, or legacy `CORRECTED` |
| `origin` | `LOW_CONFIDENCE_REVIEW` or `FINAL_HUMAN_REVIEW` |
| `recorded_at` | When the entry was recorded (UTC) |

Provenance (`document_id`, `ocr_result_id`) is captured at write time by the
confidence and human-verification modules; a one-time migration enriched the
legacy rows best-effort from the `extracted_fields` / `human_reviews` tables.

### Lifecycle

1. **Low-confidence review** (Phase 8 `confidence/services.py`): when a critical
   field fails the confidence threshold and an employee confirms or corrects it,
   an entry is written with `origin = LOW_CONFIDENCE_REVIEW`.
2. **Final human review** (Phase 12 `human_verification/services.py`): on the
   per-document final review, approved/corrected/rejected fields are written with
   `origin = FINAL_HUMAN_REVIEW`, the human `decision`, and the `correction_reason`.
3. **Future use**: exported datasets feed AI training / fine-tuning. Because every
   entry pairs the noisy `original_ocr_value` with the trusted
   `human_corrected_value`, it is a ready-made labelled corpus.

## Endpoints

| Endpoint | Description |
| --- | --- |
| `GET /feedback` | List entries with optional filters + pagination |
| `GET /feedback/{feedback_id}` | Fetch a single entry (404 if missing) |
| `GET /feedback/statistics` | Aggregations over the (optionally filtered) dataset |
| `GET /feedback/export/json` | Download the full (filtered) dataset as JSON |
| `GET /feedback/export/csv` | Download the full (filtered) dataset as CSV |

### Filters

All filters on `GET /feedback` (and reused by `statistics`/`export`) are AND-ed:

`application_id`, `reviewer`, `document_type` (`DocumentType` enum),
`field_name`, `decision`, `date_from`, `date_to`, `min_confidence`.

Invalid combinations (inverted date range, unknown decision) return 422.

### Pagination

`offset` (default 0) and `limit` (default 50, max 500) with a `FeedbackSummary`
of `{total, offset, limit, returned, items}`. Results are ordered by
`recorded_at DESC, id DESC`.

## Aggregation (`GET /feedback/statistics`)

Deterministic aggregations computed over the full filtered population:

- `total_entries`, `total_corrected_fields` (human value differs from OCR value)
- `most_corrected_fields`: top 10 field names by corrected count, ties broken by name
- `average_confidence`: mean of non-null confidence scores (null if none)
- `corrections_by_reviewer`, `corrections_by_document_type`,
  `corrections_by_decision`: sorted dictionaries, `UNKNOWN` fallback for missing values
- `correction_frequency`: daily time-series of `{date, count}`
- `generated_at`: UTC timestamp of when the report was produced

## Exports

Both exports return an `ExportResponse` JSON body
`{format, filename, record_count, generated_at, content}`:

- `GET /feedback/export/json` — `content` is a JSON array of entries.
- `GET /feedback/export/csv` — `content` is a CSV text blob; the column order is
  the canonical field contract: `id`, `application_id`, `document_id`,
  `ocr_result_id`, `field_name`, `original_ocr_value`, `normalized_value`,
  `human_corrected_value`, `confidence_score`, `confidence_source`,
  `correction_reason`, `reviewer`, `decision`, `origin`, `recorded_at`.

Filenames follow `feedback_YYYYMMDD_HHMMSS.{json,csv}`. Failures raise
`ExportFailed` (500).

# Confidence Scoring & Human Verification Module (Phase 8)

## Overview

The confidence module answers one question: **which extracted fields can the
pipeline trust?** Every field that Phase 7 extracted and validated receives a
field-level confidence score, blended from the sources that produced it. When a
*critical* field scores below a configured threshold, the pipeline pauses for a
human employee to review the low-confidence fields and either confirm or
correct them; a field an employee cannot verify halts processing entirely.

It lives in `backend/app/confidence/` and reads from (but never modifies) the
Phase 6 OCR results and Phase 7 analysis results. Human decisions are persisted
on the Phase 7 `extracted_fields` table so a re-evaluation can never silently
overwrite a completed review.

## Architecture

```
confidence/
  constants.py   Evaluation/verification statuses, critical fields, sources, reasons
  exceptions.py  ApplicationNotFound, NoAnalysisResults, ReviewNotRequired, ...
  schemas.py     Pydantic request/response models
  validators.py  Pure review-payload validation (decision set == flagged set)
  services.py    Scoring math (pure functions) + ConfidenceService orchestration
  routes.py      POST /confidence/evaluate, POST /confidence/review
```

Scoring math is written as module-level pure functions (`compute_field_confidence`,
`template_coverage`, `regex_source_confidence`, `decide_processing_status`,
`build_confidence_reason`) so it is unit-testable without a database; the service
orchestrates them and persists the outcome.

## Scoring model

### Confidence sources

Every field is scored from up to four sources:

| Source | Value | Availability |
| --- | --- | --- |
| `regex` | 1.0 valid, 0.25 invalid, 0.0 missing | Always (field extraction + validation) |
| `template` | fraction of the document's expected fields extracted (coverage) | Always |
| `ocr` | the document's OCR `overall_confidence` | Only when OCR ran (scans/images) |
| `ai` | model-provided confidence | Not yet available (weight 0.0) |

The blend (`compute_field_confidence`) only lets sources with **both a configured
weight above zero and a produced value** contribute; the contributing weights are
renormalized so a missing source never drags a score down. The dominant
contributor becomes the field's `confidence_source` (ties broken by a
deterministic `regex > template > ocr > ai` preference).

The threshold and the weights are configuration, not code, so they can be tuned
per deployment without a release:

- `confidence_threshold = 0.85` (field confidence below which a *critical* field
  forces human review)
- `confidence_weights = {"regex": 0.50, "template": 0.30, "ocr": 0.20, "ai": 0.00}`

Each field also carries an explainable `confidence_reason` string assembled from
the contributors, e.g. `"Low OCR confidence"` or `"Regex pattern mismatch;
Template mismatch"`.

### Critical fields

`CRITICAL_FIELDS` classifies the fields whose correctness is non-negotiable
(IBAN, account number, account holder, bank name, document number and the date
fields). **Only a critical field below the threshold forces human review** — if
merely non-critical fields are low, the application is ready for normalization
(e.g. a suspicious `transaction_count` must not block the whole application).

### Status derivation

```
decide_processing_status:
  fields below threshold and not yet human-verified  -> low
  any critical field in low                          -> REQUIRES_HUMAN_REVIEW
  otherwise                                          -> READY_FOR_NORMALIZATION
```

`fields_requiring_review` in the response contains **all** low fields (critical
and non-critical) so the reviewer sees the complete picture; `critical_failures`
names the critical ones that forced the review. `overall_confidence` is the mean
field confidence across the application.

## Human review workflow

### `POST /api/v1/applications/{id}/confidence/review`

The reviewer submits one decision for **every** flagged field (no partial
reviews — `validate_review_request` rejects missing or duplicated decisions):

| Decision | Effect |
| --- | --- |
| `VERIFIED` | Field becomes human-verified ground truth: `human_verified`, `reviewer`, `reviewed_at` recorded, status `VERIFIED`, confidence set to 1.0 |
| `CORRECTED` | Same, with status `CORRECTED`; the `extracted_value` is replaced by the corrected value, the original value + confidence are stored in the feedback table as a training sample |
| `CANNOT_VERIFY` | Status `CANNOT_VERIFY`; **processing is halted** → status `PROCESSING_HALTED` |

A corrected value is required for `CORRECTED` and rejected otherwise. After a
complete non-halting review the application becomes `READY_FOR_NORMALIZATION`.

Every decision (and every evaluation) is written to the audit log with the
reviewer name and affected field, so the human-review trail is fully auditable.

### `POST /api/v1/applications/{id}/confidence/evaluate`

Idempotent and re-runnable. It recomputes every field's confidence and upserts
the per-field rows, but **never touches a row a human already verified**
(`_mark_human_resolved` preserves the stored score, source, reason, status and
corrected value). Running evaluation again after a review therefore keeps the
completed review and simply re-derives the status — typically
`READY_FOR_NORMALIZATION` once every low field has been resolved.

## Persistence

No new table was created. Phase 7's `extracted_fields` table was extended
(migration `c9146e38b398`) with:

- `confidence_score` (float), `confidence_source` (str), `confidence_reason`
  (text) — the scoring result
- `verification_status` (str) — `AUTO_VERIFIED`, `PENDING_REVIEW`, `VERIFIED`,
  `CORRECTED`, `CANNOT_VERIFY`
- `human_corrected_value` (text), `human_verified` (bool), `reviewer` (str),
  `reviewed_at` (timestamptz) — the human-review state

Rows are keyed on `(ocr_result_id, field_name)`, so re-evaluation updates in
place. A corrected field additionally writes one `feedback` row
(`field_name`, `human_value`, `ocr_value`, `confidence_score`) — the seed of a
future ML-correction training dataset. Audit entries use
`confidence.evaluated`, `confidence.field_verified`, `confidence.field_corrected`,
`confidence.field_cannot_verify`, `confidence.reviewed` and
`confidence.processing_halted`.

## API

### `POST /api/v1/applications/{id}/confidence/evaluate`

Scores every extracted field of the application's analyzed documents, persists
the per-field result and decides the status.

```json
{
  "application_id": 1,
  "processing_status": "REQUIRES_HUMAN_REVIEW",
  "overall_confidence": 0.83,
  "threshold": 0.85,
  "critical_failures": ["iban"],
  "fields_requiring_review": [
    {
      "document_id": 5,
      "file_name": "scan.pdf",
      "field_name": "iban",
      "extracted_value": "DE89...",
      "normalized_value": null,
      "confidence_score": 0.84,
      "confidence_source": "ocr",
      "confidence_reason": "Low OCR confidence",
      "verification_status": "PENDING_REVIEW",
      "critical": true,
      "human_corrected_value": null,
      "human_verified": false,
      "reviewer": null,
      "reviewed_at": null
    }
  ]
}
```

### `POST /api/v1/applications/{id}/confidence/review`

```json
{
  "reviewer_name": "jane.doe",
  "decisions": [
    {"field_name": "iban", "decision": "VERIFIED"},
    {"field_name": "account_number", "decision": "CORRECTED", "corrected_value": "9999999999"}
  ]
}
```

```json
{"application_id": 1, "processing_status": "READY_FOR_NORMALIZATION"}
```

Errors: `404` application not found, `409` review already applied, `422` no
analysis results / review not required / invalid payload (missing fields,
duplicated fields, missing corrected value), `500` scoring failure. These map to
the module's domain exceptions.

## Integration with the pipeline

- **Document Analysis (Phase 7)**: consumes `document_analysis_results`
  (extracted fields, validation results, document type) and `ocr_results`
  (OCR confidence); runs only after analysis.
- **Normalization (next phase)**: receives the application either
  `READY_FOR_NORMALIZATION` (with any human-verified/corrected values already
  applied to `extracted_fields`) or `PROCESSING_HALTED` (must not proceed).
- **Rule Engine / reports**: reads `verification_status` and
  `confidence_score` per field and the audit trail.

## Out of scope

The AI confidence source is wired into the weights but contributes nothing until
a model exists (weight `0.0`). Field normalization itself is not implemented
here — only the review decisions that gate it. Signature/stamp checks and
business-rule verification belong to later phases.

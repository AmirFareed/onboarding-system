# Continuous Learning Dataset Module (Phase 14)

## Overview

The continuous learning module is the **final phase of the document
verification pipeline**: it turns the verified feedback recorded during
Phases 8-13 into a clean, versioned, machine-learning-ready dataset. The goal is
explicitly **not** to train AI models — it is to prepare a reproducible labelled
corpus that *future* OCR, extraction and document-AI improvements can consume.

Every curated record pairs the noisy `original_ocr_value` (the model input) with
the trusted `human_corrected_value` (the label), together with the provenance
and quality context needed to filter and weight training samples.

It lives in `backend/app/continuous_learning/`.

## Architecture

```
continuous_learning/
  constants.py   Dataset-schema version, export formats, confidence buckets, record contract
  exceptions.py  ContinuousLearningError(500), DatasetNotFound(404),
                 DatasetValidationError(422), DatasetExportError(500)
  schemas.py     LearningDatasetEntry, LearningDataset, DatasetStatistics,
                 DatasetMetadata, ExportResponse
  validators.py  Pure curation rules, duplicate signatures, record building,
                 canonical serialization, completeness, CSV serialization
  repositories.py  Facade re-exporting the read-only FeedbackRepository
  services.py    ContinuousLearningService: curate, hash, version, statistics, export
  routes.py      GET /continuous-learning/{dataset,statistics,export/json,export/csv,version}
```

Pure helpers carry no I/O and are unit-tested without a database; the service
orchestrates them against the existing `feedback_dataset` table.

## Dataset generation pipeline

```
feedback_dataset ──read──▶ curate ──validate──▶ curated records ──hash──▶ version ──▶ dataset/statistics/exports
     (Phase 8-12)          dedupe        exclude invalid       SHA-256       cl-1.0.0-<hash12>
```

1. **Read** — every feedback sample is read via `FeedbackRepository.all_matching()`.
   The module reuses the existing table; it creates no new table and never
   modifies a completed module.
2. **Deduplicate** — exact-duplicate signatures
   `(application_id, document_id, field_name, ocr_value, human_value, recorded_at)`
   collapse to the lowest dataset id.
3. **Validate** — samples must satisfy strict provenance (see below); excluded
   samples are counted by reason and logged.
4. **Resolve** — each valid sample's `document_type` is resolved from its
   document (an `UNKNOWN` fallback covers legacy rows without a document).
5. **Hash** — a deterministic SHA-256 digest is computed over the canonical JSON
   serialization (records ordered by id, `sort_keys=True`, compact separators,
   ISO-8601 timestamps).
6. **Version** — `dataset_version = cl-<schema-version>-<hash[:12]>`, e.g.
   `cl-1.0.0-a1b2c3d4e5f6`. Identical content produces an identical version.

## Quality validation (curation rules)

A feedback sample is included only when **all** of these hold:

- `application_id` is present (strict provenance)
- `field_name` is non-empty
- `original_ocr_value` is non-empty
- `human_corrected_value` is non-empty (the required corrected label)
- `confidence_score` is present and within `[0.0, 1.0]`
- `decision` is either absent or one of `APPROVE`, `CORRECT`, `REJECT`, `CORRECTED`

Optional context fields (`document_type`, `normalized_value`, `confidence_source`,
`correction_reason`, `decision`, `origin`, `reviewer`) fall back to `UNKNOWN`/`None`
and their coverage is reported as **dataset completeness**. The results are fully
deterministic: the same source rows always produce the same records, hash and
version.

## Versioning

Versioning is implemented **without a new table**: the version is derived
deterministically from the dataset content hash and the dataset-schema version.
`GET /continuous-learning/version` returns:

- `dataset_version` — `cl-1.0.0-<hash[:12]>`
- `project_version` — the software version that produced the dataset
- `created_at` — generation timestamp (UTC)
- `record_count` — number of curated records
- `dataset_hash` — full SHA-256 hex digest of the canonical serialization

The hash is **format-independent**: JSON and CSV exports of the same curated
dataset carry the same digest, so a consumer can verify that any export matches
the published version without re-running the pipeline.

## Statistics

`GET /continuous-learning/statistics` returns deterministic distributions over
the curated dataset:

- `total_records`
- `document_distribution` — counts per document type
- `field_distribution` — counts per field name
- `correction_distribution` — counts per review decision
- `confidence_distribution` — counts per confidence bucket
  (`0.00-0.20` ... `0.80-1.00`)
- `average_confidence`
- `reviewer_distribution` — counts per reviewer (`UNKNOWN` fallback)
- `dataset_completeness` — fraction of records carrying each optional field
- `metadata` — the same version/hash metadata as `/version`

Every distribution is a sorted dictionary so output is reproducible.

## Export formats

Both exports return an `ExportResponse` with the version metadata and the payload:

- `GET /continuous-learning/export/json` — `content` is a JSON array of records.
- `GET /continuous-learning/export/csv` — `content` is CSV text; the column
  order is the canonical 12-field contract: `application_id`, `document_type`,
  `field_name`, `original_ocr_value`, `normalized_value`,
  `human_corrected_value`, `confidence_score`, `confidence_source`,
  `correction_reason`, `decision`, `origin`, `recorded_at`.

The architecture is prepared for future **Parquet** and **HuggingFace Dataset**
exporters by adding a new format branch in the export flow; they are intentionally
not implemented yet.

## Future fine-tuning workflow

1. Export the curated dataset (`/export/json` or `/export/csv`).
2. Verify the payload against `dataset_hash` (recompute SHA-256 over the canonical
   records or trust the embedded version metadata).
3. Load the labelled pairs (`original_ocr_value` → `human_corrected_value`) into
   the fine-tuning pipeline of choice.
4. Use `application_id`, `document_type`, `confidence_score`, `decision` and
   `origin` to filter or re-weight training samples.
5. Re-export when new verified feedback accumulates; the hash/version changes
   only when the content changes.

## Why the system does NOT automatically retrain models

- **No training code lives here**: the module contains no model definitions,
  no training/fine-tuning routines, no YOLO or LLM training, and no scheduling.
- **Retraining is a separate, human-gated process**: an automatic retrain can
  silently regress a production verifier. Curated datasets must be inspected,
  versioned and validated by engineers before use.
- **Data quality precedes model quality**: the pipeline first ensures the
  labelled corpus is clean and reproducible; only then can a future training
  job consume it deliberately.
- **Determinism by design**: because every export is hash-versioned, a training
  run can always be traced to the exact dataset it consumed.

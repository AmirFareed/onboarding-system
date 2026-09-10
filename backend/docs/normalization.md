# Data Normalization Module (Phase 9)

## Overview

The normalization module answers one question: **what is the canonical form of
every verified extracted field?** The extraction engine produces values in many
shapes — `DE89 3704 0044 0532 0130 00` and `DE89370400440532013000` for the same
IBAN, `HBL` and `HABIB BANK LIMITED` for the same bank, `31/01/2026` and
`2026-01-31` for the same date. Downstream business validation can only compare
like-for-like, so every verified field is run through its configured normalizer
and the deterministic result is stored as the field's `normalized_value`.

It lives in `backend/app/normalization/` and reads from (but never modifies) the
Phase 7 `extracted_fields` table. It deliberately re-runs no extraction and no
scoring: it only canonicalizes the values that the confidence module already
settled as trustworthy.

## Why a separate module

Normalization is a *pure transformation* — it must be deterministic, idempotent
and database-independent. Keeping it in its own package means:

- the normalizers are pure functions of their input, unit-testable without a
  database (they raise `ValueError` and never decide business outcomes);
- the field-to-normalizer mapping and the alias tables are **data** in
  `constants.py`, so expanding a bank alias or accepting a new date format is a
  data change, not a logic change;
- a normalizer can be reused later by business validation without importing the
  pipeline orchestration.

## Architecture

```
normalization/
  constants.py   Statuses, outcomes, bank/branch aliases, date formats, field mapping
  exceptions.py  ApplicationNotFound, NoExtractedFields
  schemas.py     Pydantic request/response models
  validators.py  Canonical-shape predicates + eligibility check
  normalizers.py Pure normalizer classes + NormalizerRegistry (field -> normalizer)
  services.py    NormalizationService orchestration (value choice, eligibility, persistence)
  routes.py      POST /normalize, GET /normalized-fields
```

## Value selection and eligibility

For every field the module feeds the normalizer the **verified value**:

```
verified_value = human_corrected_value if set else extracted_value
```

`human_corrected_value` wins because a reviewer explicitly confirmed or corrected
it; it is the ground truth. The `extracted_value` column is **never** mutated —
only `normalized_value` is ever written.

A field is eligible only when its `verification_status` is `VERIFIED`,
`CORRECTED` or `AUTO_VERIFIED`. `PENDING_REVIEW` and `CANNOT_VERIFY` fields are
**skipped** (logged, not canonicalized): a pending field may still change after
review and a halted field has no dependable value. Each field ends up in exactly
one per-field outcome:

| Outcome | Meaning |
| --- | --- |
| `NORMALIZED` | The verified value was canonicalized and `normalized_value` persisted |
| `SKIPPED` | Not eligible (unverified) or empty value; nothing written |
| `FAILED` | The value does not match the field's shape (e.g. malformed IBAN); nothing written |

A `SKIPPED` or `FAILED` field never overwrites a previously stored
`normalized_value`, so re-running normalization after a partial review never
clobbers good canonical data.

## Normalizers

Each normalizer is a small class with a stable `identifier`, registered in the
`NormalizerRegistry` via the `FIELD_NORMALIZERS` mapping. Fields without an
entry fall back to the general-text normalizer.

| Normalizer | Fields | Canonical form | Notes |
| --- | --- | --- | --- |
| `iban` | `iban` | `[A-Z]{2}\d{2}[A-Z0-9]{11,30}` | strips spaces/hyphens, uppercases, validates structure; malformed values fail loudly |
| `account_number` | `account_number` | digits/letters, no spaces/hyphens/slashes/dots | **leading zeros preserved** — they are significant |
| `title` | `account_holder`, `employee_name`, `employer_name`, `full_name`, `taxpayer_name` | uppercased, collapsed | |
| `bank_name` | `bank_name` | `BANK_ALIASES` canonical name | unknown banks keep their cleaned, uppercased name |
| `cnic` | `document_number`, `employee_id`, `tax_reference_number` | `XXXXX-XXXXXXX-X` | only 13-digit values are formatted; anything else (e.g. passports) gets general-text cleanup |
| `date` | `date_of_birth`, `issue_date`, `expiry_date`, `payment_date` | `YYYY-MM-DD` | accepts every `DATE_FORMATS` entry; already-ISO values pass through (idempotent) |
| `statement_period` | `statement_period` | `YYYY-MM-DD - YYYY-MM-DD` | handles both raw ranges and the extractor's `"{'start': …, 'end': …}"` dict-string |
| `salary_month` | `salary_month` | `YYYY-MM` | accepts `2026-01`, `01/2026`, `January 2026`, … |
| `branch` | `branch`, `branch_name` | abbreviation-expanded, title-cased | `M. TOWN BR ISB` → `Model Town Branch Islamabad` |
| `vendor` | `vendor_name`, `payee` | uppercased, collapsed | |
| `general_text` | *fallback* | control chars stripped, whitespace collapsed | NFKC-normalized; case preserved |

Common text cleanup (`clean_text`) applies Unicode NFKC normalization, collapses
every whitespace run to a single space (tabs and newlines act as separators) and
drops control characters.

### Configurable mappings

The bank and branch alias tables and the accepted date formats are plain data in
`constants.py`:

- `BANK_ALIASES` maps normalized input forms to canonical legal entity names
  (`HBL`, `Habib Bank`, `HABIB BANK LTD` → `HABIB BANK LIMITED`).
- `BRANCH_ALIASES` expands abbreviations (`BR` → `BRANCH`, `H.O` → `HEAD OFFICE`,
  `LHR` → `LAHORE`) and corrects common misspellings.
- `DATE_FORMATS` lists `strptime` formats tried in order; the ambiguous slash
  format resolves day-first to match the extraction engine's `_parse_date`.

Changing these tables is a deploy-time configuration change and does not touch
business logic. `NORMALIZATION_VERSION` identifies the exact logic that produced
a stored `normalized_value`, so data can be traced to its generating rules.

## API

### `POST /api/v1/applications/{id}/normalize`

Runs every eligible field through its normalizer, persists `normalized_value`
for `NORMALIZED` fields and sets the application status to
`READY_FOR_BUSINESS_VALIDATION`. Idempotent and re-runnable.

```json
{
  "application_id": 1,
  "processing_status": "READY_FOR_BUSINESS_VALIDATION",
  "normalization_version": "1.0.0",
  "summary": {"total": 11, "normalized": 11, "skipped": 0, "failed": 0},
  "items": [
    {
      "document_id": 5,
      "file_name": "statement.pdf",
      "field_name": "iban",
      "source_value": "DE89 3704 0044 0532 0130 00",
      "normalized_value": "DE89370400440532013000",
      "normalizer": "iban",
      "status": "NORMALIZED"
    },
    {
      "document_id": 5,
      "file_name": "statement.pdf",
      "field_name": "statement_period",
      "source_value": "{'start': '2026-01-01', 'end': '2026-01-31'}",
      "normalized_value": "2026-01-01 - 2026-01-31",
      "normalizer": "statement_period",
      "status": "NORMALIZED"
    }
  ]
}
```

### `GET /api/v1/applications/{id}/normalized-fields`

Returns every stored field of the application with its persisted
`normalized_value` (and `verification_status`), ordered by document and field
name. Useful for the business-validation stage to read canonical values without
re-normalizing.

Errors: `404` application not found, `422` no extracted fields (run analysis
first), `500` normalization failure. These map to the module's domain
exceptions. A single field can also be canonicalized without the database via
the public service method `NormalizationService.normalize_field(...)`.

## Persistence

**No migration was needed**: the `normalized_value` column already exists on
`extracted_fields` (added in the initial schema). The module only writes that
column for `NORMALIZED` fields and reuses the existing `ExtractedFieldRepository`
(row mutations + a single commit, matching the confidence module's pattern).

Each run writes one audit entry (`normalization.completed`) with the run's
summary and version. Per-field logging records started / normalized / skipped /
failed, and a completion log summarizes the run.

## Integration with the pipeline

- **Confidence (Phase 8)**: consumes `extracted_fields` after evaluation/review;
  only fields in `VERIFIED` / `CORRECTED` / `AUTO_VERIFIED` are normalized, so a
  `PROCESSING_HALTED` application's halted fields are skipped, not trusted.
- **Business validation (next phase)**: receives the application
  `READY_FOR_BUSINESS_VALIDATION` with canonical `normalized_value` per field, and
  can read them via `GET /normalized-fields` or the public `normalize_field`
  method.
- **Rule engine / reports**: reads `normalized_value` to compare across documents
  and applications.

## Out of scope

Business rules (e.g. "the salary on the payslip matches the bank statement
credit"), cross-document reconciliation, report generation and approval
workflows belong to later phases. This module only canonicalizes; it does not
judge. The `AI` confidence source, signature/stamp checks and any model-driven
normalization are likewise out of scope.

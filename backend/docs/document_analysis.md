# Document Analysis Module (Phase 7)

## Overview

The document analysis module turns the raw OCR text produced by Phase 6 into
structured financial data, validates it, checks cross-field consistency and
produces an explainable verification result for every document. It lives in
`backend/app/document_analysis/` and is deliberately decoupled from the OCR
layer: the OCR layer produces text, the analysis layer consumes text. The only
interface between the two is the `ocr_results` table read through
`OCRRepository`.

The pipeline is fully deterministic — no external LLM is involved. Every field
is extracted by a regex and normalized by a parser, every validation is a pure
function and every score is the same weighted sum of the same inputs. Results
can therefore be reproduced and audited.

## Architecture

```
document_analysis/
  constants.py    Analysed document types, verification statuses, scoring weights
  exceptions.py   OCRResultNotFound, UnsupportedDocumentType, AnalysisFailed, ...
  schemas.py      Pydantic request/response models
  extractors.py   Document type detection + regex field extraction per type
  validators.py   Reusable pure field validators + ValidatorEngine
  rules.py        Cross-field consistency rules + scoring + status derivation
  services.py     Orchestration service (analyze / get_results)
  routes.py       POST /analyze-documents, GET /analysis-results
```

The analysis layer is independent from the OCR internals: it never imports from
`document_processing`, and only touches the database through its own repository
plus the read-only `OCRRepository`.

## Extraction pipeline

1. **Load text** — the service reads the document's stored `OCRResult`.
2. **Detect type** — `detect_document_type` scores keywords in the text and
   returns one of `BANK_STATEMENT`, `PAYSLIP`, `ID_DOCUMENT`, `TAX_DOCUMENT` or
   `UNKNOWN`. Documents with an undeterminable type fail with
   `UnsupportedDocumentType`.
3. **Extract fields** — a regex extractor per type produces normalized values:
   amounts become floats (`1,250.50` and `1.250,50` both parse to `1250.5`),
   dates become ISO strings, the statement period becomes
   `{"start": ..., "end": ...}` and counts become integers.
4. **Validate** — `ValidatorEngine` runs every expected field through its
   validator, producing `valid`, `invalid` or `missing` results (see below).
5. **Consistency** — `RulesEngine` runs the cross-field checks for the type.
6. **Score** — the components are combined into a confidence score and status.
7. **Persist** — one `document_analysis_results` row per document.

### Supported document types and fields

| Type | Fields |
| --- | --- |
| Bank statement | `account_holder`, `account_number`, `iban`, `bank_name`, `statement_period`, `opening_balance`, `closing_balance`, `total_credits`, `total_debits`, `currency`, `transaction_count` |
| Payslip | `employee_name`, `employee_id`, `employer_name`, `gross_salary`, `net_salary`, `salary_month`, `payment_date` |
| ID / passport | `full_name`, `date_of_birth`, `document_number`, `nationality`, `issue_date`, `expiry_date` |
| Tax document | `taxpayer_name`, `tax_reference_number`, `tax_year`, `gross_income`, `total_tax`, `currency` |

The analysed document type is independent of the storage-level `DocumentType`
enum (which only holds upload checklist categories); it is inferred from the
text, so the same uploaded category can be recognised as any analysed type.

## Verification logic

### Validators

Each validator is a pure function returning `(status, message)`. Absent expected
fields are reported as `missing`; present fields are `valid` or `invalid`.

| Validator | Checks |
| --- | --- |
| `validate_iban` | ISO 13616 format and mod-97 checksum |
| `validate_amount` / `validate_balance` | Finite non-negative number |
| `validate_currency` | Three-letter ISO 4217 code |
| `validate_account_number` | 4-30 digits |
| `validate_date` | Parseable ISO date (future dates allowed — expiry dates) |
| `validate_date_not_future` | Parseable ISO date in the past or today |
| `validate_statement_period` | Both bounds parse |
| `validate_salary_month` / `validate_tax_year` | Format and plausible range |
| `validate_document_number` | 4-20 alphanumeric characters |

### Consistency rules

Stored separately from field validations:

| Rule | Type | Behaviour |
| --- | --- | --- |
| `STMT_PERIOD_VALID` | Bank statement | start ≤ end, else `fail` |
| `OPENING_LE_CLOSING` | Bank statement | closing below opening → `warning` |
| `CLOSING_MATCHES_TRANSACTIONS` | Bank statement | with credits/debits: closing ≈ opening + credits − debits; with zero transactions: closing == opening; otherwise `warning` |
| `BALANCES_NON_NEGATIVE` | Bank statement | negative balance → `fail` |
| `NET_LE_GROSS` / `NET_POSITIVE` | Payslip | net ≤ gross and net ≥ 0 |
| `PAYMENT_WITHIN_MONTH` | Payslip | payment date in salary month or the following month |
| `EXPIRY_AFTER_ISSUE` / `AGE_REASONABLE` | Identity | expiry after issue; derived age 0-120 |
| `GROSS_POSITIVE` / `TAX_NOT_EXCEEDING_GROSS` | Tax | income ≥ 0; tax ≤ income |

### Scoring

```
confidence = 0.5 * field_coverage + 0.3 * validation_rate + 0.2 * consistency_rate
```

- `field_coverage` = expected fields extracted / expected fields
- `validation_rate` = passing validations / total validations
- `consistency_rate` = passing checks / applicable checks (non-applicable rules
  are neutral)

Status derivation:

- any missing **critical** field, failed validation of a critical field, or
  failed consistency check → `NEEDS_REVIEW`
- score ≥ 0.80 → `VERIFIED`
- score ≥ 0.60 → `PARTIALLY_VERIFIED`
- score ≥ 0.40 → `NEEDS_REVIEW`
- otherwise → `FAILED`

The `issues` list in the report is the human-readable explanation: every
non-passing validation and consistency message (e.g. "IBAN missing", "Closing
balance does not reconcile with opening balance and transaction totals").

## Persistence

`document_analysis_results` (migration `7d5f0708871e`) stores one row per
document (unique `document_id`). Re-analysing a document updates the existing
row. The JSONB columns hold the full explainable report so the review dashboard
can render it without recomputation. `analysis_version` records the exact logic
version that produced the result.

## API

### `POST /api/v1/applications/{id}/analyze-documents`

Analyzes every document of an application and persists the results. Documents
without an OCR result (processing never ran or failed) are reported as
`FAILED` with `OCRResultNotFound`; failures never abort the run.

Response:

```json
{
  "application_id": 1,
  "items": [
    {
      "document_id": 5,
      "file_name": "statement.pdf",
      "document_type": "BANK_STATEMENT",
      "outcome": "ANALYZED",
      "verification_status": "VERIFIED",
      "confidence_score": 1.0,
      "extracted_fields": {
        "account_holder": "John A. Doe",
        "account_number": "1234567890",
        "iban": "DE89370400440532013000",
        "opening_balance": 1250.5,
        "closing_balance": 3200.75,
        "total_credits": 2500.0,
        "total_debits": 549.75,
        "transaction_count": 23,
        "currency": "EUR",
        "bank_name": "Sparkasse",
        "statement_period": {"start": "2026-01-01", "end": "2026-01-31"}
      },
      "validation_results": [
        {"field": "iban", "validator": "iban_checksum", "status": "valid", "message": "IBAN checksum passed"}
      ],
      "consistency_results": [
        {"rule_id": "CLOSING_MATCHES_TRANSACTIONS", "rule_name": "Closing balance matches transactions", "status": "pass", "message": "Closing balance reconciles with credits and debits"}
      ],
      "issues": [],
      "processing_time_ms": 4
    }
  ],
  "total_analyzed": 1,
  "total_failed": 0
}
```

### `GET /api/v1/applications/{id}/analysis-results`

Returns every stored analysis result with the verification status, confidence
score, extracted fields, validations, consistency checks and derived issues.
`issues` is reconstructed from the stored JSONB so the dashboard gets the same
explainable list without a recomputation.

Errors: `404` (application not found), `422` (document type undetermined),
`500` (analysis failure). These map to `ApplicationNotFound`,
`UnsupportedDocumentType` and `AnalysisFailed`/`ValidationFailed`.

## Logging

Structured logs cover analysis start/completion, per-document extraction
duration, computed score and status, invalid/missing field counts and
persistence. Raw document contents are never logged.

## Out of scope

Field extraction is deterministic (regex) only — no LLM, no learned extraction.
The module does not perform business-rule verification, extracted-value
cross-document matching, or signature/stamp checks; those belong to later
phases.

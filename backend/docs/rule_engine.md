# Business Rule Engine Module (Phase 10)

## Overview

The rule engine turns the **normalized, verified data** of an application into a
business verdict. Where earlier phases ask *"can we trust the bytes / the text /
the extracted fields / the canonical values?"*, this module asks the business
questions: *"are all required documents present? is the account holder
consistent across them? do the balances reconcile? is the statement period
recent? is the document signed?"*.

It lives in `backend/app/rule_engine/` and is deliberately **deterministic,
explainable and configurable**:

- deterministic — the same inputs always produce the same outcomes;
- explainable — every rule returns a structured result (`rule_id`, `rule_name`,
  `category`, `status`, `message`, related documents and fields, timestamp);
- configurable — all thresholds, tolerances and document mappings are data in
  `constants.py`, not logic;
- independent — each rule is a class with a single `evaluate(context)` entry
  point, registered once, and no rule can affect another rule's outcome.

It consumes only two sources of truth and writes nothing back into them:
`extracted_fields.normalized_value` (the canonical values the Phase 9
normalization module settled) and the `visual_detection_results` table (the
detection outcomes a future YOLO/Qwen pipeline persists). No OCR, no extraction,
no scoring and no re-normalization happen here.

## Why a separate module

- The business rules are the product's decision layer; they must not be tangled
  with pipeline orchestration.
- Rules are pure functions of a `RuleContext`; unit tests can drive every rule
  with an in-memory context and no database.
- The rule registry is a single deterministic list, so a run is auditable in a
  stable order and coverage is easy to reason about.
- The mappings and thresholds live as data, so product changes (a new required
  document, a wider reconciliation tolerance) are data edits.

## Architecture

```
rule_engine/
  constants.py   Versions, categories, severities, document/field mappings, thresholds
  exceptions.py  RuleEngineError, ApplicationNotFound
  schemas.py     RuleContext (input) + RuleResult + Pydantic response models
  validators.py  Format predicates reused by the format rules
  services.py    RuleEngineService (context assembly, execution, persistence, response)
  routes.py      POST /validate, GET /validation-results
  rules/
    __init__.py           RuleRegistry (47 rules, registration order)
    base.py               BaseRule + context/rule-result helpers
    document_rules.py     8 document-completeness rules
    field_rules.py        6 field-presence rules
    format_rules.py       5 format rules
    cross_document_rules.py  4 cross-document consistency rules
    date_rules.py         5 date rules
    visual_rules.py       11 visual rules
    policy_rules.py       4 policy rules
    quality_rules.py      4 data-quality rules
```

## The rule contract

Every rule returns a `RuleResult`:

| field | meaning |
| --- | --- |
| `rule_id` | stable machine id (e.g. `FMT_IBAN`) |
| `rule_name` | human-readable description |
| `category` | one of the 8 `RULE_CATEGORIES` keys |
| `status` | `PASS`, `FAIL`, `WARNING` or `PENDING_MANUAL_REVIEW` |
| `message` | short explainable statement of the outcome |
| `related_document_ids` | documents the rule examined |
| `related_field_names` | fields the rule examined |
| `validated_at` | shared run timestamp |

Statuses map to the existing severity vocabulary when persisted: `PASS` ->
`INFO`, `WARNING`/`PENDING_MANUAL_REVIEW` -> `WARNING`, `FAIL` -> `ERROR` — the
same mapping the technical-validation module uses.

A **rule that raises** during execution never aborts the run: the exception is
logged and the rule reports `FAIL` with `"Rule execution failed
unexpectedly: ..."`. A run always produces one result per registered rule.

## Rule categories

1. **document_completeness** — the 8 required documents are present (exactly one
   each; missing or duplicated is a `FAIL`).
2. **field_presence** — the AMC's key fields (`iban`, `account_number`,
   `account_holder`, `bank_name`, `statement_period`, `balances`) are present and
   normalized; a present-but-not-normalized field is a `WARNING`.
3. **format** — every normalized value matches the field's canonical shape
   (IBAN, CNIC, account number, amount, date). No values to check warns.
4. **cross_document** — values that must agree across documents
   (account holder, account number, IBAN, statement period) are compared and a
   disagreement is a `FAIL` with a preview of the distinct values.
5. **date** — statement period sequencing/recency, issue-before-expiry,
   payment recency and date-of-birth sanity, all evaluated against the current
   UTC date.
6. **visual** — signature/stamp detection outcomes per document type.
7. **policy** — holder-name sanity, opening/closing balance reconciliation,
   single currency, salary-alignment.
8. **quality** — no placeholder/empty values, confidence floor, transaction
   count sanity.

The registry executes them in that fixed order
(`document -> field -> format -> cross_document -> date -> visual -> policy ->
quality`).

## Cross-document consistency

`_CrossDocumentRule` compares a single field name across the participating
documents of an application (e.g. `account_holder` on the AMC, bilateral and
tripartite agreements). The rule:

- `FAIL`s when a required participant document is absent;
- `FAIL`s when a participant is present but has no normalized value for the
  field;
- `FAIL`s when the participants disagree, showing the distinct values in the
  message;
- `PASS`es when every present participant holds the same normalized value.

## Visual rules and the YOLO/Qwen integration

The rule engine does **not** run any detection. It reads the
`visual_detection_results` table (per `(document_id, detection_type)`) that a
future detection pipeline writes via `VisualDetectionRepository.upsert` — the
same upsert contract makes detection idempotent on re-runs.

For each document type the rules expect a signature and/or stamp
(`SIGNATURE_DOCUMENT_TYPES`, `STAMP_DOCUMENT_TYPES`):

- detection row present and `is_present=True` -> `PASS`;
- detection row present and `is_present=False` -> `FAIL`
  ("{signature|stamp} not detected on document id=...");
- **no detection row** -> `PENDING_MANUAL_REVIEW` (a human must confirm);
- document missing -> `FAIL`.

A 0.50 confidence floor (`CONFIDENCE_FLOOR`) governs the quality rules.

## Policy rules and configurability

Policy thresholds and mappings live in `constants.py`:

| constant | meaning |
| --- | --- |
| `PLACEHOLDER_ACCOUNT_HOLDERS` | holder names that are placeholders (e.g. `TBD`) |
| `RECONCILIATION_TOLERANCE` | allowed drift for opening/credits/debits vs closing |
| `STATEMENT_MAX_AGE_DAYS` | how old a statement may be (365) |
| `MIN_BIRTH_YEAR` | date-of-birth sanity floor (1900) |
| `REQUIRED_DOCUMENT_TYPES` | the 8 documents every application must contain |

> **Known discrepancy:** the Phase 4 completeness module treats the Bilateral
> Agreement as *optional* (`completeness/constants.py`), while Phase 10's
> specification requires it. The rule engine implements the Phase 10 contract,
> so `REQUIRED_DOCUMENT_TYPES` includes the bilateral agreement. Alignment of
> the completeness stage is a product decision tracked outside this module.

## Persistence and status derivation

A validation run **replaces** the stored outcome: the service deletes the
application's existing rows in the 8 rule categories, then inserts one row per
rule with a single shared `validated_at`. Rows land in the existing
`validation_results` table (Phase 10 added the nullable `related_document_ids`
and `related_field_names` JSON columns) and an audit log entry with action
`rule_engine.validated`, the `RULE_ENGINE_VERSION`, the overall status and the
summary is written by user `system`.

The overall status follows the precedence
`FAIL > PENDING_MANUAL_REVIEW > WARNING > PASS`. It is reported in the response
and recorded in the audit log only — **the rule engine never writes
`applications.status`**; deciding whether an application is approved remains the
reporting stage's job.

The rule engine also ignores a stored `normalized_value` that belongs to a
field whose `verification_status` is `PENDING_REVIEW` or `CANNOT_VERIFY`: the
normalization module never clobbers a previous value when it skips a field, so
an old canonical value can linger on a halted field, and such a value is not
trustworthy for a business verdict.

## API

- `POST /api/v1/applications/{application_id}/validate` — run the 47 rules and
  return `RuleRunSummary` (overall status, per-category counts) plus every
  `RuleResultItem`. `404` when the application does not exist.
- `GET /api/v1/applications/{application_id}/validation-results?category=...` —
  return the stored per-rule rows. `category` filters to one of the 8 rule
  categories; without it all rule-engine rows are returned. Technical-validation
  rows are never included (filtering uses the rule engine's own category set).

## Testing

- `tests/test_rule_engine_rules.py` — 61 unit tests driving every rule with an
  in-memory `RuleContext` (no database).
- `tests/test_rule_engine_api.py` — 14 end-to-end tests through the HTTP API,
  covering the full digital-statement flow, persistence idempotency, auditing,
  visual/cross-document passes and failures, skipped (unverified) fields,
  empty applications and 404 paths.

The full backend suite (362 tests) runs green, `alembic check` reports no
pending migrations and the package compiles cleanly.

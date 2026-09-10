# Final Human Verification Module (Phase 12)

## Overview

Final human verification is the **last decision stage** of the verification
pipeline. The employee reviews the generated Validation Report together with the
uploaded documents, signatures, stamps, normalized fields, confidence results
and OCR results, completes the mandatory manual checklist and records the final
business decision. The system **never overrides the employee's decision**.

This module is deliberately **not another extraction or correction stage**:

- it performs **no OCR**, no normalization, no rule validation and no report
  generation;
- it consumes **only the outputs of previous phases** (documents, OCR,
  extracted fields, confidence, normalization, validation results, visual
  detections, the aggregated report);
- it writes **only the review**: the decision, the checklist state, the
  corrections, the application status and the audit trail.

It lives in `backend/app/human_verification/` and reuses the existing
`human_reviews`, `human_corrections`, `manual_checklists`, `audit_logs` and
`feedback_dataset` tables.

## Architecture

```
human_verification/
  constants.py    REVIEW_VERSION, DECISIONS, DECISION_TO_STATUS, CHECKLIST_ITEMS
                  (14 mandatory items), audit action identifiers
  exceptions.py   HumanReviewError + ApplicationNotFound(404),
                  ReviewAlreadyCompleted(409), InvalidDecision(400),
                  ChecklistIncomplete(422), MissingRejectionReason(422),
                  InvalidCorrection(422), ReviewPersistenceError(500)
  schemas.py      Pydantic models: HumanReviewRequest/Response, CorrectionItem,
                  ChecklistItem, ReviewSummary, ReviewHistory, ReviewScreen,
                  ErrorResponse
  validators.py   Pure decision rules: decision_to_status(),
                  validate_decision_rules(), checklist_state()
  repositories.py Facade re-exporting the existing repositories
  services.py     HumanVerificationService (get_review, submit_review,
                  get_history)
  routes.py       GET/POST /applications/{id}/human-review,
                  GET /applications/{id}/human-review/history
```

The module mirrors the `reports/` and `confidence/` architecture: thin routes
that translate domain exceptions into documented HTTP errors, a service that
orchestrates repositories, and pure validators that are unit-testable without a
database.

## Decision workflow

The employee opens the review screen, reviews the evidence and submits exactly
one of three decisions:

| Decision | Requirements | Application status |
| --- | --- | --- |
| `APPROVE` | Every manual checklist item checked; no corrections, no rejection reason | `APPROVED` |
| `CORRECT` | At least one corrected value; no rejection reason | `CORRECTED` |
| `REJECT` | Mandatory rejection reason (optional notes via `comments`); no corrections | `REJECTED` |

An application can be reviewed **only once**. There is no reopen workflow, so a
second submission is rejected with `409 ReviewAlreadyCompleted` and the stored
decision is never overwritten.

## Checklist workflow

`CHECKLIST_ITEMS` defines the fourteen mandatory items. Each item is stored
individually in `manual_checklists` (unique per application and item name) with
its own checked state, reviewer and timestamp:

1. Bank Maintenance Certificate originality confirmed
2. Authority Letter signature confirmed
3. Account Maintenance Certificate signature confirmed
4. 1-Link Application signature confirmed
5. Tripartite Agreement signature confirmed
6. Business Requirement Document signature confirmed
7. Formal Request Letter signature confirmed
8. Schedule of Charges / Bilateral signature confirmed
9. Account Maintenance Certificate stamp confirmed
10. 1-Link Application stamp confirmed
11. Tripartite Agreement stamp confirmed
12. Schedule of Charges / Bilateral stamp confirmed
13. Critical validation errors reviewed
14. Validation report reviewed

The review screen always returns the full checklist with the current state
(default: all unchecked). An `APPROVE` decision requires every item to be
checked; a partial checklist raises `422 ChecklistIncomplete` and nothing is
persisted. The checklist state is also recorded for `CORRECT` and `REJECT`
decisions whenever the employee submits items.

## Application state transitions

```
                      ┌──────── APPROVE ──▶ APPROVED
pipeline results ───▶ │
(SUBMITTED / ...)     ├──────── CORRECT ──▶ CORRECTED
                      │
                      └──────── REJECT ──▶ REJECTED
```

`DECISION_TO_STATUS` maps the three decisions onto the application status. The
`CORRECTED` value was added to the `applicationstatus` enum by migration
`b2f8c4d1e3a9` (PostgreSQL `ALTER TYPE ... ADD VALUE`). The report module
treats `REJECTED` as an external decision that always wins the overall verdict;
an `APPROVED` or `CORRECTED` status never overrides the derived report verdict.

## Correction handling

A `CORRECT` decision stores one `human_corrections` row per corrected field:

- `field_name`, `original_value`, `corrected_value`, `reason` — the original
  value is read from the application's stored extracted field (its
  human-corrected value if one exists, otherwise the extracted value).
- Reviewer and timestamp live on the owning `human_reviews` row.

When a matching extracted field exists **and** the corrected value actually
differs from the stored value, the field's human-corrected state is updated
(`human_corrected_value`, `human_verified`, `reviewer`, `reviewed_at`) and a
`feedback_dataset` sample is appended so the ground-truth dataset is never
duplicated for an unchanged value. This keeps responsibility clean: field-level
correction during low-confidence review happens in Phase 8
(`/confidence/review`); this phase records the **final** confirmed values of
any remaining field as part of the final decision.

## Audit trail

Every decision writes audit entries (username = reviewer, JSON details) into
`audit_logs`:

- `human_review.submitted`
- `human_review.application_approved` | `human_review.application_corrected` |
  `human_review.application_rejected`
- `human_review.checklist_completed` (approvals)

Module logging additionally records `Review opened`, `Review submitted`,
`Application approved/corrected/rejected`, `Checklist completed` and
`Audit record created` at `INFO` level.

## API

| Endpoint | Method | Purpose | Errors |
| --- | --- | --- | --- |
| `/applications/{id}/human-review` | GET | Full review screen (report, documents, fields, detections, checklist, previous review) | 404, 422 (no validation results), 500 |
| `/applications/{id}/human-review` | POST | Submit the final decision | 400, 404, 409, 422, 500 |
| `/applications/{id}/human-review/history` | GET | Stored reviews, most recent first | 404 |

Request shape (POST):

```json
{
  "reviewer_name": "employee",
  "decision": "APPROVE",
  "comments": "All documents verified",
  "checklist": [{"item_name": "Validation report reviewed", "is_checked": true}],
  "corrections": [],
  "rejection_reason": null
}
```

Error mapping: 400 internally inconsistent payload, 404 unknown application,
409 double review, 422 no validation results / incomplete checklist / missing
rejection reason / missing corrections, 500 persistence failure.

## Integration with Validation Reports

The review screen embeds the full `ValidationReport` produced by Phase 11
(`/applications/{id}/validation-report`). Loading the report is a hard
prerequisite for both the screen and the decision: an application with no
business-rule results cannot be reviewed (`422`). The report is regenerated
deterministically on demand; the module never re-runs rules or detections.

## Integration with the Feedback Module

Corrections append ground-truth pairs (`ocr_value` vs `human_value`) to
`feedback_dataset`, the same table Phase 8 writes for low-confidence fields.
Only value changes are recorded, so the dataset accumulates unique human
confirmations across both phases for future model training.

## Testing

- `tests/test_human_verification_engine.py` — pure decision rules: status
  mapping, checklist completeness, mandatory rejection reason, correction
  requirements, internal consistency and checklist vocabulary.
- `tests/test_human_verification_api.py` — end-to-end approve / correct /
  reject flows, checklist enforcement, double-review prevention, history,
  404s, payload validation, audit actions, status transitions and idempotent
  reads.

Run the full suite with `pytest`, verify migrations with `alembic check`, and
byte-compile with `compileall`.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A full-stack FinTech document-verification system (FastAPI + PostgreSQL backend, React 19 + Vite frontend) for banks/KPITB to onboard merchants: upload a fixed checklist of onboarding documents per application, run them through a staged pipeline (OCR → field extraction → confidence scoring → normalization → business rules → human review), and curate corrections into a versioned ML dataset. See `README.md` for the full feature list, API surface and getting-started steps — this file only covers what README doesn't: commands you'll actually run and architecture that spans multiple files.

**`CONTEXT.md` (project root) is the authoritative, continuously-updated log of what's actually true about this project right now** — real bugs found, fixes applied/pending, department decisions, and known gaps, each with dated evidence. It is far more current than README.md in places. Read it before assuming any module's behavior; don't trust a prior session's chat summary over it.

## Commands

**Backend** (from `backend/`, with `.venv` activated):
```bash
pip install pip-tools && pip-sync requirements-lock.txt   # install exact pinned deps
alembic upgrade head                                       # apply migrations
python -m app.auth.seed                                    # seed default accounts

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload   # API (Swagger at /docs)
python -m app.bulk_queue                                   # queue worker -- REQUIRED for bulk PDF uploads to ever process; without it a bulk upload sits at "UPLOADED" forever with no visible error

pytest -q                        # full suite
pytest tests/test_upload_api.py  # one file
pytest tests/test_upload_api.py::test_get_application  # one test
ruff check app                   # lint (config: backend/ruff.toml)
mypy --config-file mypy.ini      # type check
```

**Frontend** (from `frontend/`):
```bash
npm install
npm run dev        # Vite dev server, localhost:5173, proxies /api/v1 to :8000
npm run build       # production build -> frontend/dist
npm run lint        # eslint .
npm run test        # vitest (watch)
npm run test:ci     # vitest run (single pass, what CI uses)
```

`.github/workflows/ci.yml` is the exact source of truth for what CI runs (`ruff check app` + `mypy`, `pytest -q` against a real Postgres 15 service container, `npm run lint && npm run test:ci && npm run build`) — check it directly rather than assuming.

## Architecture

### Backend: feature-module layout, staged pipeline

Every pipeline stage under `backend/app/` is a self-contained package (`routes.py`, `services.py`, `schemas.py`, `repositories.py`, `constants.py`, `exceptions.py`). The pipeline is staged and **not automatically chained end-to-end by a single call** for most of its history — each stage is a separate API call/queue step whose output is persisted before the next stage reads it:

```
Upload → Completeness → Operator Triage (app/operator_workflow) → Technical Validation
  → Processing (OCR, app/document_processing) → Document Analysis (field extraction,
  app/document_analysis) → Confidence → Normalization → Rule Engine (business rules)
  → Reports → Human Verification → Feedback → Continuous Learning
```

**`app/operator_workflow`** is the real first-level triage stage, sitting between Completeness and the rest of the pipeline: an operator queue (`GET /validation/applications`, business-completeness state per application — status, required/received/missing document counts) plus three OPERATOR-gated actions (`request-documents`, `operator-reject`, `operator-submit`) that move an application through `SUBMITTED`/`NEEDS_DOCUMENTS` toward processing or rejection. Every action writes an immutable validation-history entry plus the shared audit log. A same-named but unrelated `app/validation` module existed alongside this one and shared its URL prefix (`/validation/...`) until it was deleted for having zero real callers (see the Frontend section below and `CONTEXT.md`) — if you find a stray reference to it, it's leftover, not live.

For **bulk PDF uploads** specifically, `PipelineRunnerService` (driven by `app/bulk_queue`) does chain analysis → confidence → normalization → rule validation automatically once OCR finishes, landing the application at `PENDING_REVIEW` with no manual per-stage calls needed — this is newer and different from the single-document manual-call path; don't assume one call pattern from reading only one path.

**The splitter (`app/preprocessing/splitter.py`) and the field extractors (`app/document_analysis/extractors.py`) are two separate concerns solved by two different mechanisms**, and bugs in this codebase's history routinely turn out to be in one but get misdiagnosed as the other:
- The splitter decides where one logical document ends and the next begins inside a multi-page bulk PDF, using title-phrase matching (`_STRONG_TITLE_PHRASES`) confined to a header zone, plus a "continuation absorption" fallback for anything that doesn't independently title-match (silently merged into whichever document group is still open). This fallback is the single most common root cause of "document type X returns zero/wrong fields" bugs — always check whether the raw cached OCR text actually contains unrelated content merged in before assuming the extractor itself is broken.
- Extractors are per-document-type regex/structural parsers, one class per checklist type in `_EXTRACTORS`/`_CHECKLIST_TYPE_MAP`. `AccountMaintenanceCertificateExtractor`/`TripartiteAgreementExtractor` share a structural bank-account-block parser (positional column-block + interleaved label/value passes) rather than plain regex, because real bank-detail layouts vary too much for a single pattern.
- **Never build or tune an extractor pattern against a synthetic fixture alone or against one atypical real sample without checking it generalizes** — this codebase has a documented, named cautionary history of exactly that mistake (see `CrossPeriodRule`/`CrossBranchCodeRule` in `CONTEXT.md`). Real-sample validation before any extractor/rule change is a hard project norm, not a suggestion.

**Real-sample validation workflow**: `Confidential Data/` (gitignored, real onboarding PDFs) and `backend/scripts/ocr_cache.py`'s `get_ocr_text(source_file, document_type, copy_number)` cache real OCR'd text to `Confidential Data/.ocr_cache/*.txt`, keyed by (source file, detected type, copy number) so a given document is only ever OCR'd once (OCR is the dominant cost of any real-file work — minutes per page on a CPU-only machine). Any extraction/splitter change should be checked against this cache before being trusted.

**Roles are a real backend authorization model, not just a UI concern** (`app/auth/roles.py`, `app/auth/dependencies.py`): `EMPLOYEE` (the seeded default account, deliberately all-access — authorized for every operator/reviewer/IT guard by design so one account can exercise the whole app), `OPERATOR` (first-level document/completeness checks only via `app/operator_workflow`, never sees OCR/extraction internals), `REVIEWER` (opens human-verification, approves/corrects/rejects), `IT` (application history, performance metrics). `effective_role()` normalizes legacy stored role strings (e.g. `"Verification Officer"` → `EMPLOYEE`). Frontend role gating in `frontend/src/utils/roles.js` mirrors this but is UI/UX only — the backend guard is the real security boundary.

**Database**: PostgreSQL with native ENUM types. `backend/tests/conftest.py` auto-derives and auto-creates an isolated `<database>_test` database before the suite runs (requires the app DB role to have `CREATEDB`) and refuses to wipe anything whose name doesn't contain `"test"` — the test suite does **not** touch your real dev database. `PaddleOCREngine` is a process-wide singleton with no internal locking around `.predict()`; concurrent calls from multiple workers can crash the process (a real, previously-confirmed PaddlePaddle bug), which is why `bulk_queue_workers` defaults to 1 (`app/core/config.py`).

**`ENVIRONMENT` defaults to `production`** (fail-closed) — an omitted value never silently enables dev-mode behavior (insecure cookies, dev secret key, debug mode, the dev seed password). Local dev and tests must set it explicitly (`.env.example` ships `ENVIRONMENT=development`; CI uses `testing`).

### Frontend

Role-aware sidebar (`frontend/src/data/navigation.js`) built from section groups, each item optionally gated by `roles`/`strictRoles`. `frontend/src/store/ApplicationsContext.jsx` is the single shared source of truth for applications/documents across Dashboard, Applications and Upload pages. `app/operator_workflow` (operator task queue, `/validation`) and `human_verification` (`/human-review`, final reviewer decision) are two distinct, both-live workflows covering the two real stages of the pipeline's human side — first-level triage, then final decision. (A same-named but unrelated `app/validation` module, `ValidationTask`/`ValidationRun`/`ValidationLog`, had zero real callers and was deleted outright — see `CONTEXT.md` for that history if you find stray references to it anywhere.) Internal pipeline stages (technical validation, extraction, confidence, normalization, rule engine) intentionally have no sidebar surface — they run automatically as part of verification.

### Root-level layout beyond `backend/`/`frontend/`

- `Confidential Data/` (gitignored) — real onboarding documents + `.ocr_cache/`; never assume it exists on a fresh checkout.
- `docs/` — `Master_Rules_Combined.md` (the business-rules spec extractors/rules are validated against), audit reports, implementation roadmap.
- `demo/`, `Individual PDFs/`, `data/samples/` — sample/demo PDFs for manual testing (mostly gitignored).
- `scratch/` — this session's convention for throwaway verification scripts; not part of the shipped codebase.
- `storage/`, `logs/` — runtime output, gitignored.

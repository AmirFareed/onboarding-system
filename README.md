# FinTech — Financial Document Verification System

A full-stack enterprise platform for banks and compliance teams to onboard
merchants and process **confidential financial documents**. Employees upload a
fixed checklist of documents per application, and the system runs a staged,
rule-driven verification pipeline — OCR, field extraction, confidence scoring,
normalization, business rules and human review — then curates the verified
corrections into a versioned, machine-learning-ready dataset.

The frontend presents a professional FinTech workspace (sidebar navigation,
dark/light/system themes, responsive layout) where finance employees process
applications, while AI/dataset management is intentionally hidden under
**Settings → Administration**.

---

## Table of contents

- [Key features](#key-features)
- [Technology stack](#technology-stack)
- [Architecture](#architecture)
- [Verification pipeline](#verification-pipeline)
- [Repository structure](#repository-structure)
- [Database schema](#database-schema)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Running the application](#running-the-application)
- [Testing](#testing)
- [API overview](#api-overview)
- [Frontend overview](#frontend-overview)
- [Security](#security)
- [Module documentation](#module-documentation)

---

## Key features

**Employee workflow (finance/compliance focus)**

- **Dashboard** — recent applications, document-upload progress, quick actions.
  No AI metrics leak into the employee view.
- **Applications** — searchable, filterable, sortable list of verification
  cases; create, view details, track status.
- **Upload Documents** — fixed per-application slot checklist (18 uploads):
  7 required document families with per-category copy counts, plus CNIC
  front/back. Slots are numbered (`Copy 1 … Copy N`), empty slots stay visible,
  replace is scoped to its own slot, and per-category caps are enforced by the
  backend.
- **Batch Upload PDFs** — select 30+ separate combined-PDF onboarding
  packages at once from the Applications page; each becomes its own
  application (auto-named from its filename) and is processed one at a time,
  automatically, with a live Pending / Processing / Completed / Failed status
  per file. A failed file never blocks the rest of the queue, and progress
  survives navigating away from the page.
- **Validation Reports & Human Review** — rule-driven validation results and a
  human review workspace per application.
- **Settings → Administration** — Feedback analytics and Continuous Learning
  dataset management, marked as restricted/admin-only.

**Document verification pipeline (backend)**

- **Upload & storage** — type-aware, extension + MIME + magic-byte validated
  uploads streamed to a filesystem storage root.
- **Document completeness** — verifies the full fixed checklist is present.
- **Technical validation** — validates file bytes, structure and content.
- **Document processing & text extraction** — OCR via PaddleOCR + PyMuPDF.
- **Document analysis & field extraction** — visual detection and field
  extraction from scanned documents.
- **Confidence scoring** — per-field confidence from OCR, extraction and
  analysis; critical low-confidence fields force human review.
- **Normalization** — canonical values for names, dates, CNICs, etc.
- **Business rule engine** — deterministic rule evaluation (PASS / FAIL /
  WARNING / PENDING_MANUAL_REVIEW) with severities.
- **Validation reports** — structured, printable per-application reports.
- **Human verification** — reviewer approves, corrects or rejects; corrections
  are recorded with the original OCR value.
- **Feedback dataset** — the human-corrected field data, queryable and
  exportable.
- **Continuous learning** — curates verified corrections into a versioned,
  SHA-256-hashed, ML-ready labelled dataset with JSON/CSV export.

---

## Technology stack

| Layer    | Technology                                                                                       |
| -------- | ------------------------------------------------------------------------------------------------ |
| Backend  | Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, Uvicorn                                |
| Database | PostgreSQL (native ENUM types, full-text search,`UNIQUE` constraints)                          |
| OCR/ML   | PaddleOCR, PaddlePaddle, PyMuPDF, OpenCV                                                         |
| Frontend | React 19, React Router 7, Axios, Vite 8, lucide-react icons                                      |
| Styling  | CSS Modules + design tokens (sky/light/dark blue FinTech palette), dark/light/system themes      |
| Auth     | Cookie-based sessions (short-lived access JWT + rotating refresh token), bcrypt password hashing |
| Tests    | pytest (backend), Playwright-style headless Chrome/CDP checks (manual verification scripts)      |
| Tooling  | Alembic migrations,`python-dotenv`, ESLint-free Vite build, git                                |

---

## Architecture

```
                        ┌────────────────────────────────────────────┐
 Browser (React SPA)   │  /api/v1   (Vite dev proxy → FastAPI)      │
  ┌──────────────┐     └──────────────┬─────────────────────────────┘
  │  Dashboard   │                    │
  │  Applications│─── JSON ──────────▶│  FastAPI (app.main:app)
  │  Upload      │                    │  ┌───────────────────────────┐
  │  Settings    │◀─── JSON ──────────│  │ auth, upload, completeness │
  └──────────────┘                    │  │ technical_validation,      │
                                      │  │ document_processing,       │
  storage/ (files) ◀─────────────────▶│  │ document_analysis,         │
                                      │  │ confidence, normalization, │
                                      │  │ rule_engine, reports,      │
                                      │  │ human_verification,        │
                                      │  │ feedback, continuous_learning
                                      │  └────────────┬──────────────┘
                                      │               │ SQLAlchemy
                                      └───────────────▼────────────────┐
                                        PostgreSQL (finance_verification)│
                                        └────────────────────────────────┘
```

The backend follows a **feature-module** layout: every pipeline stage is a
self-contained package with `routes.py` (thin HTTP layer), `services.py`
(business logic), `schemas.py` (pydantic contracts), `repositories.py`,
`validators.py`, `constants.py` and `exceptions.py`. Routes translate module
domain exceptions into documented HTTP errors.

---

## Verification pipeline

The pipeline is staged so each phase answers one question; results accumulate
in the database and feed the next stage.

```
 Upload ─▶ Completeness ─▶ Technical Validation ─▶ Processing (OCR)
   │            │                  │                     │
   ▼            ▼                  ▼                     ▼
 Human Review ◀─ Confidence ──── Normalization ──── Document Analysis
   │            (low confidence                       (field extraction)
   ▼            forces review)
 Feedback ─────────────────────▶ Continuous Learning (curated ML dataset)
```

- Documents are uploaded into a fixed checklist of required types with copy
  slots (e.g. 3 × 1-Link forms, 6 × Schedule of Charges, 1 × Authority Letter,
  CNIC front + back).
- Each pipeline stage stores its outputs (OCR text, extracted fields,
  confidences, validation results, human reviews) in dedicated tables so the
  full history is reproducible.
- Human reviewers **approve, correct or reject**; every correction records the
  original OCR value alongside the trusted corrected value.
- The **continuous learning** stage folds only validated, complete records into
  a versioned dataset with a reproducible content hash — ready for future model
  improvements.

---

## Repository structure

```
finance-verification-system/
├── backend/
│   ├── app/
│   │   ├── api/                 # Router aggregation + health endpoint
│   │   ├── auth/                # Login, session, refresh, logout, seed script
│   │   ├── core/                # Settings, logging, security (JWT, hashing)
│   │   ├── database/            # Engine, session, Base, models, enums
│   │   ├── completeness/        # Document completeness classification
│   │   ├── technical_validation/
│   │   ├── document_processing/ # OCR + text extraction
│   │   ├── document_analysis/   # Visual detection + field extraction
│   │   ├── confidence/          # Confidence scoring & review
│   │   ├── normalization/       # Canonical value normalization
│   │   ├── rule_engine/         # Business rule evaluation
│   │   ├── reports/             # Validation report generation
│   │   ├── human_verification/  # Human review workflow
│   │   ├── feedback/            # Feedback (corrections) dataset API
│   │   ├── continuous_learning/ # Curated ML dataset API
│   │   ├── upload/              # Applications + document upload/storage
│   │   ├── ocr/ preprocessing/ utils/ templates/
│   │   ├── main.py              # create_app() factory + uvicorn entry
│   │   └── __init__.py          # __version__ (0.1.0)
│   ├── alembic/                 # Migration environment + versions/
│   ├── tests/                   # 544 pytest cases across all modules
│   ├── docs/                    # Per-module design docs (phases 5-14)
│   ├── alembic.ini
│   ├── pytest.ini
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── pages/               # Login, Dashboard, Applications, Create, Details,
│       │                        # UploadDocuments, Verification, Settings
│       ├── components/          # layout/, dashboard/, applications/, documents/,
│       │                        # verification/, common/, auth/, theme/
│       ├── data/                # navigation model, document catalogue, statuses
│       ├── services/            # axios clients (api, applications, documents, verification)
│       ├── store/               # ApplicationsContext (shared state)
│       ├── hooks/  routes/  auth/  theme/  utils/  styles/  assets/
│       ├── App.jsx
│       └── main.jsx
├── storage/                     # Uploaded files (gitignored): applications/APP-xxxxxx/
├── scripts/                     # Operational scripts
├── docs/                        # Top-level docs
└── tests/                       # Top-level integration tests
```

---

## Database schema

All domain enums (`ApplicationStatus`, `DocumentType`, `DocumentProcessingStatus`,
`ValidationStatus`, `Severity`, `ReviewDecision`) are native PostgreSQL ENUMs.

| Table                         | Purpose                                                                 |
| ----------------------------- | ----------------------------------------------------------------------- |
| `users`                     | Employee accounts (employee_id, email, role, bcrypt password hash).     |
| `refresh_tokens`            | Rotating, revocable session tokens.                                     |
| `applications`              | Verification cases and their lifecycle status.                          |
| `audit_logs`                | Action history.                                                         |
| `documents`                 | Uploaded files; unique`(application_id, document_type, copy_number)`. |
| `ocr_results`               | Raw OCR text per document.                                              |
| `visual_detection_results`  | Visual/object detection output.                                         |
| `document_analysis_results` | Analysis summary per document.                                          |
| `extracted_fields`          | Extracted field values + confidence inputs.                             |
| `validation_results`        | Rule-engine outcomes (rule, status, severity, message).                 |
| `manual_checklists`         | Manual checklist state.                                                 |
| `human_reviews`             | Review decisions per application/document.                              |
| `human_corrections`         | Original → corrected value pairs.                                      |
| `feedback_dataset`          | Human-corrected field data (OCR value vs trusted value).                |

> `documents` enforces a unique index on `(application_id, document_type, copy_number)` so each numbered slot can hold exactly one file. The per-type
> copy cap lives in `backend/app/upload/constants.py`
> (`MAX_COPIES_BY_DOCUMENT_TYPE`: 1-Link 3, Tripartite 3, Schedule of Charges 6,
> everything else 1).

---

## Getting started

### Prerequisites

- **Python 3.12+**
- **PostgreSQL 15+** (native enum support)
- **Node.js 20+** and npm
- (Optional) GPU/CPU builds of PaddlePaddle/PaddleOCR for the OCR pipeline.

### 1. Database

Create the database and a role:

```sql
CREATE USER finance_app WITH PASSWORD 'finance-app-local-password';
CREATE DATABASE finance_verification OWNER finance_app;
```

### 2. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate

# Reproducible install (recommended): installs the exact versions this
# project is tested against, from the pip-compile-generated lock file.
pip install pip-tools
pip-sync requirements-lock.txt

# Configure environment
cp .env.example .env    # then edit DATABASE_URL, SECRET_KEY, etc.

# Apply migrations
alembic upgrade head

# Seed the default employee account (EMP-1001)
python -m app.auth.seed
```

The default seeded account (development only):

```
Employee ID : EMP-1001
Email       : employee@fintech.local
Password    : Welcome@123
```

**`requirements.txt` vs `requirements-lock.txt`**: `requirements.txt` declares loose, compatible version ranges (the source of truth for what this project needs); `requirements-lock.txt` is a `pip-compile`-generated, fully pinned resolution of that file, committed so every install — local, CI, or production — gets the exact same dependency versions instead of whatever a range happens to resolve to on a given day. Use `pip-sync requirements-lock.txt` for installs (recommended, especially for production); regenerate the lock file with `pip-compile requirements.txt -o requirements-lock.txt` after changing `requirements.txt`, and commit both files together.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server runs on `http://localhost:5173` and proxies `/api/v1` to
the FastAPI backend on `http://localhost:8000`.

---

## Configuration

Backend settings are defined in `backend/app/core/config.py` and loaded from
environment variables / `.env` (see `backend/.env.example`):

| Variable                 | Default                                                                        | Purpose                                                      |
| ------------------------ | ------------------------------------------------------------------------------ | ------------------------------------------------------------ |
| `ENVIRONMENT`          | `production`                                                                 | dev/testing/production; defaults to production (fail closed) |
| `DEBUG`                | `false`                                                                      | Never enable in production                                   |
| `SECRET_KEY`           | dev placeholder (rejected in prod)                                             | Token signing & crypto derivation                            |
| `DATABASE_URL`         | `postgresql+psycopg://postgres:postgres@localhost:5432/finance_verification` | DB connection                                                |
| `LOG_LEVEL`            | `INFO`                                                                       | Root log level                                               |
| `API_PREFIX`           | `/api/v1`                                                                    | URL prefix for all routers                                   |
| `MAX_UPLOAD_SIZE_MB`   | `25`                                                                         | Per-file upload limit                                        |
| `CONFIDENCE_THRESHOLD` | `0.85`                                                                       | Critical fields below this force review                      |
| `DEFAULT_EMPLOYEE_*`   | `EMP-1001` etc.                                                              | Seeded account credentials                                   |

> `ENVIRONMENT` defaults to `production` so an omitted value never silently
> enables development behaviour (insecure cookies, dev secret key, debug mode).
> Local development and tests set it explicitly: `backend/.env.example` ships
> `ENVIRONMENT=development`, and CI runs with `ENVIRONMENT=testing`.
>
> The seed script **refuses to run** with the development default password when
> `ENVIRONMENT=production`.

---

## Running the application

Local development requires **two backend processes**, not one. `uvicorn`
alone accepts uploads and serves the API, but it does not process bulk PDF
uploads on its own — without the dedicated queue worker, a bulk upload is
accepted (HTTP 201) and then sits at `processing_status: "UPLOADED"`
indefinitely, with no error surfaced anywhere in the UI. See
`backend/docs/phase15e-reliability.md` for the full worker execution model
(in-process background draining vs. dedicated worker processes).

**Single command (recommended for local dev):** a root-level `package.json`
runs the API, the queue worker and the frontend together in one terminal,
labeled and color-coded, stopped together with one Ctrl+C:

```bash
npm install   # one-time, installs concurrently
npm run dev
```

This still requires Postgres running and the one-time `alembic upgrade head`
/ `python -m app.auth.seed` steps done first (see Getting Started above). The
three processes can also be run individually, as below.

**Backend API (API + OpenAPI docs):**

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# Swagger UI: http://localhost:8000/docs
```

**Backend queue worker (required — processes bulk PDF uploads):**

```bash
cd backend
python -m app.bulk_queue
```

**Frontend (dev server):**

```bash
cd frontend
npm run dev
```

**Production build:**

```bash
cd frontend && npm run build   # outputs to frontend/dist
```

---

## Testing

The backend suite runs against the **real FastAPI app and the real development
database**, with the storage backend redirected to a per-test temporary
directory. `tests/conftest.py` wipes the database before/after every test and
re-seeds the default employee account at the end of the session so local
logins keep working after test runs.

```bash
cd backend
pytest -q                 # 544 tests
pytest tests/test_upload_api.py
```

Frontend verification uses headless Chrome via the Chrome DevTools Protocol
(scripts in `/tmp` during development) to assert sidebar structure, routes,
themes, responsive behavior and the upload-slot workflow end-to-end.

---

## API overview

All endpoints are mounted under `/api/v1`. Interactive docs at `/docs`.

| Module                | Endpoints                                                                                                                                                                                                          |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Health                | `GET /health`                                                                                                                                                                                                    |
| Auth                  | `POST /auth/login`, `GET /auth/me`, `POST /auth/refresh`, `POST /auth/logout`                                                                                                                              |
| Upload / Applications | `POST/GET /applications`, `GET /applications/{id}`, `POST /applications/{id}/documents`, `GET/PUT/DELETE /applications/{id}/documents/{doc_id}`, `GET /documents/{id}`, `GET /documents/{id}/download` |
| Completeness          | `GET/POST /applications/{id}/completeness[/verify]`                                                                                                                                                              |
| Technical validation  | `GET/POST /applications/{id}/technical-validation[/validate]`                                                                                                                                                    |
| Document processing   | `POST /applications/{id}/process-documents`, `GET .../ocr-results`                                                                                                                                             |
| Document analysis     | `POST .../analyze-documents`, `GET .../analysis-results`                                                                                                                                                       |
| Confidence            | `POST .../confidence/evaluate`, `POST .../confidence/review`                                                                                                                                                   |
| Normalization         | `POST .../normalize`, `GET .../normalized-fields`                                                                                                                                                              |
| Rule engine           | `POST .../validate`, `GET .../validation-results`                                                                                                                                                              |
| Reports               | `GET .../validation-report`, `GET .../validation-report/html`, `GET .../validation-summary`                                                                                                                  |
| Human verification    | `GET/POST .../human-review`, `GET .../human-review/history`                                                                                                                                                    |
| Feedback              | `GET /feedback`, `GET /feedback/{id}`, `GET /feedback/statistics`, `GET /feedback/export/json`, `GET /feedback/export/csv`                                                                               |
| Continuous learning   | `GET /continuous-learning/dataset`, `/statistics`, `/version`, `/export/json`, `/export/csv`                                                                                                             |

---

## Frontend overview

**Sidebar navigation (employee-facing):**

```
MAIN         Dashboard · Applications
DOCUMENTS    Upload Documents
VERIFICATION Validation Reports · Human Review
SYSTEM       Settings
```

**Settings → Administration** carries the internal Feedback and Continuous
Learning tools, visually marked **Restricted** — they are not shown as main
sidebar entries. The navigation model lives in
`frontend/src/data/navigation.js` (`NAVIGATION`, `ADMIN_NAV_ITEMS`,
`INTERNAL_ROUTES`).

**Shared state:** `frontend/src/store/ApplicationsContext.jsx` is the single
source of truth for applications and their documents. The Dashboard recent
list, Applications page and Upload page all read from the same store, so a new
application or upload appears everywhere immediately.

**Document catalogue:** `frontend/src/data/documents.js` defines the fixed
required checklist — 9 required entries, 18 total slots — with
`computeDocumentProgress()` powering the X/18 progress bar on the dashboard and
upload page, and the per-category Complete / Incomplete / Missing checklist.

**Themes:** `frontend/src/theme/` provides Light / Dark / System via CSS
variables; the sidebar is collapsible on desktop, an icon rail on tablet and a
drawer with backdrop on mobile.

---

## Security

- **Authentication**: bcrypt-hashed passwords; short-lived JWT access cookie
  plus rotating, revocable refresh cookie; 401 handling transparently refreshes
  and replays requests.
- **Uploads**: validated by extension, MIME type *and* magic-byte sniffing;
  streamed in chunks to a storage root outside the source tree
  (`storage/`, gitignored); per-type copy caps enforced server-side.
- **Secrets**: `.env` is gitignored; production refuses the development secret
  key and default seed password.
- **Privacy**: document payloads are never stored in `localStorage`; no OCR
  text or confidence internals are exposed in the employee UI; internal AI
  functionality is hidden under restricted Administration settings.

---

## Module documentation

Per-module design docs live in `backend/docs/`:

| File                        | Phase / topic                                  |
| --------------------------- | ---------------------------------------------- |
| `technical_validation.md` | Phase 5 — technical validation                |
| `document_processing.md`  | Phase 6 — OCR & text extraction               |
| `document_analysis.md`    | Phase 7 — visual detection & field extraction |
| `confidence.md`           | Phase 8 — confidence scoring                  |
| `normalization.md`        | Phase 9 — normalization                       |
| `rule_engine.md`          | Phase 10 — business rules                     |
| `validation_reports.md`   | Phase 11 — validation reports                 |
| `human_verification.md`   | Phase 12 — human verification                 |
| `feedback.md`             | Phase 13 — feedback dataset                   |
| `continuous_learning.md`  | Phase 14 — curated ML dataset                 |
| `phase15e-reliability.md` | Phase 15E — bulk queue worker execution model |

---

## Roadmap / status

- **F1** Dashboard layout shell, auth + theme system ✅
- **F2** Application management (list/search/filter/sort, create, details) ✅
- **F3** Document upload & management with fixed slot checklist ✅
- **F4** Verification workspace + shared applications store ✅
- **Pipeline (F5–F14)** Completeness → technical validation → processing →
  analysis → confidence → normalization → rule engine → reports → human
  verification → feedback → continuous learning ✅
- **Frontend navigation redesign** — employee-only sidebar, admin tools moved
  under Settings ✅
- **Multi-PDF batch upload** — select 30+ separate PDFs in one action from
  the Applications page ("Batch Upload PDFs"); each file automatically
  creates and processes its own application (named from its filename),
  queued and processed strictly one at a time, with live Pending / Processing
  / Completed / Failed status per file, continuing past any individual
  failure, and surviving navigation away from the page ✅

**Still not built:** six other department-requested features (conditional/
special approval, richer report remediation detail, editable report
commentary, an AMC "originality" check, and others) are logged as
scoped-or-pending-clarification backlog items, not shipped. See
`CONTEXT.md`'s 2026-08-25/26 entries for the real detail — this file only
points at it.

- **Backlog**: Six department-requested features (conditional approvals, report remediation details, etc.) are documented and scoped in `CONTEXT.md`, pending product clarification.

---

## License

Proprietary internal project. All data shown is fictional; do not upload real
customer documents to this system without authorization.

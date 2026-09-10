# OCR Model — Full-Stack Trust Audit (2026-08-17)

A full-stack cross-check of every claim made about this project so far this session — backend, frontend, the backend/frontend contract, the test suites, and the documentation. Every finding below was re-derived from the actual current state of the repo at audit time (commands run, output read), not assumed from CONTEXT.md, a commit message, or an earlier conversation turn.

Ground rules that shaped this audit: it is an audit, not a fix (findings are documented, not fixed inline, except one trivial, pre-approved CONTEXT.md wording correction); every claim needed a receipt (an actual command/output, not a restated conclusion); no real multi-page OCR job was re-run as part of it (everything answerable from already-cached OCR text, the existing test suites, static code reading, and git history); pre-flight checks (`tasklist`/`ps aux | grep python`) ran before every pytest run or real-data operation; Confidential Data/ PII rules applied throughout (structure/presence only, never real extracted values).

---

## Part A — Git / GitHub Ground Truth

**A.1 — Local vs. origin/main:** Clean tree (`git status --porcelain` empty). `HEAD == origin/main == 6676a6d6d5f170eda1729006d9c8d08bb68511f0`. Confirmed match, no drift.

**A.2 — Commit inventory since `726a607`:** 92 total commits. 64 touch `backend/`, 19 touch `frontend/`, 29 are docs-only-relevant (`docs/`, `CONTEXT.md`, `IMPLEMENTATION_ROADMAP.md`). Full list produced and reviewed (92 entries, chronological, not truncated).

**A.3 — Commit-message-vs-diff spot check (6 most recent backend commits):**

| Commit | Claim | Verified |
|---|---|---|
| `f708acc` (CNIC front) | "6 files changed, 346 insertions(+), 1 deletion(-)" | **Exact match** — `CONTEXT.md`, `constants.py`, `extractors.py`, `services.py`, `test_document_analysis_api.py`, `test_document_analysis_engine.py` |
| `20b9dd0` (1-Link Letter) | Touches 9 files incl. 3 cascaded test files | Matches stat exactly |
| `5ae7542` (AMC/BRD reconcile) | "Documentation and shared test-fixture correction only — no production code changes" | **Confirmed** — only `CONTEXT.md`, `test_reports_api.py` (test), `docs/TEAMMATE_BUG_TRIAGE.md` touched. No production source. |
| `6b78301` (BRD) | 6 files, extractor + constants + tests | Matches |
| `fcc9fda` (Zarghuna, blank-page/completeness) | "ink-ratio measurement" for blank-page detection | **Confirmed** — `is_blank_image()` diff in `technical_validation/utils.py` does exactly this via `BLANK_INK_GRAY_THRESHOLD`/`BLANK_INK_RATIO` |
| `95b3053` (Zarghuna, rule drop) | Removes `FieldStatementPeriodPresenceRule`/`FieldBalancesPresenceRule`, 49→47 rules | **Confirmed** by diff — both classes cleanly deleted |

No mismatches found in any of the 6.

**A.4 — Uncommitted/untracked drift + PII safety:** Tree clean. `Confidential Data/` confirmed genuinely gitignored (`.gitignore:80`, live match via `check-ignore`, not just read from the file's text). One correction to the audit's own premise: `git log --all --diff-filter=A --name-only -- "Confidential Data/*"` returns empty — not because there's no incident, but because the known incident file (`demo/TMA Khal Dir Lower .pdf`, added `ad9a47d`, untracked at `bc57cff`, 2026-08-13) was never tracked under a `Confidential Data/` path — it was at `demo/`. Broader scan (`*.pdf`, `*.docx`, all history) confirms exactly one real-PII incident, already fully remediated, plus 6 project-specification PDFs/docx under `docs/` (Master Rules, business rules docs) which are legitimate tracked documentation, not applicant data. No new incident.

**A.5 — Teammate branch/PR state:** `git branch -a` shows only the 3 already-known feature branches (`afsana-validation-logs`, `samad-doc-splitter`, `zarghuna-bulk-queue`), all already merged and accounted for in CONTEXT.md. No new commits beyond current `HEAD`. No new teammate activity.

---

## Part B — Backend: Document Analysis Module

**B.1 (type inventories):** 11 `AnalyzedDocumentType` members (4 legacy + 7 checklist-mapped + `UNKNOWN`), 12 `DocumentType` members (`backend/app/database/models/enums.py:26`). Both enums use identical `NAME = "NAME"` values throughout — zero string-value drift for any of the 7 checklist-mapped types.

**B.2/B.3:** `_CHECKLIST_TYPE_MAP` — exactly 7 entries, matches CONTEXT.md's claim by name, not just count. `CNIC_BACK`/`SCHEDULE_OF_CHARGES`/`FORMAL_REQUEST_LETTER` genuinely absent (honest fallthrough, not silent misclassification). `_EXTRACTORS` — 11 entries (4 legacy unchanged + 7 checklist), every `_CHECKLIST_TYPE_MAP` value has a matching key. Failure mode on a missing extractor is a clean `UnsupportedDocumentType()` raise, not a silent no-op.

**B.4 (field consistency) — 2 real, previously-undocumented mismatches, both pre-existing/legacy, not from this session:**
- `BankStatementExtractor` extracts `total_credits`/`total_debits` (with real `_post` normalizers) — neither is in `EXPECTED_FIELDS[BANK_STATEMENT]`. Both extract successfully and are silently never scored.
- `IdentityExtractor` (ID_DOCUMENT) extracts `issue_date` — not in `EXPECTED_FIELDS[ID_DOCUMENT]`. Same silent-waste pattern.
- All 7 checklist-mapped types checked clean; `TripartiteAgreementExtractor`'s `party_1link` initially looked missing from a grep pass (a digit-in-key regex false negative, not a code issue) — confirmed present and correctly listed by direct read.

**B.5 (real-sample re-verification) — 1 new finding, rest confirmed accurate:**
- **B.5.1 Authority Letter — discrepancy found.** 2 of 5 real cached samples (`DG_Sports…copy1`, `TMA_Khal_Dir_Lower…copy1`) extract nothing at all. Structural inspection (redacted, no PII read) shows these are numbered-list/checklist-style content (S.No/Yes-No columns), not actual Authority Letter body text — plausibly a splitter misclassification, not an extractor bug. Never mentioned in CONTEXT.md's "two confirmed structural variants" claim, which only accounted for the 2 samples that do extract cleanly (`copy2` for each org) plus a third partial case (`GDA_Abbotabad`, organization_name only).
- **B.5.2 BRD — confirmed accurate.** 3/3 real samples extract both fields, matches claim exactly.
- **B.5.3 AMC — confirmed accurate, both documented issues still present unfixed.** Re-ran extraction: `GDA_Abbotabad` copy1 still returns `account_number == '/IBAN'` (garbage capture); `DG_Sports` copy1 still returns all three critical fields empty.
- **B.5.4 Tripartite — confirmed unchanged.** Zero real samples; class body added once (`bb3ebfb`), never touched since.
- **B.5.5 1-Link Letter — confirmed accurate.** 4/4 samples extract `organization_name`; `branch_code` extracts only on the single-account-sentence variant (1 of 4), exactly as documented.
- **B.5.6 Bilateral Agreement — confirmed unchanged.** Zero real samples; class body added once (`08bec31`), never touched since.
- **B.5.7 CNIC Front — confirmed exact match.** 2/3 fully verified, 1/3 missing only `date_of_expiry`, identical to the build-time result.

**B.6 (Formal Request Letter / Schedule of Charges):** Fresh zero-sample confirmation for both. The true current "checked/untouched" split is 11 of 21 checked (via the cheaper split-only method), 10 of 21 genuinely untouched — CONTEXT.md's per-entry counts for these two types were stale at audit time (said "5 processed"/"16 of 21"), a documentation lag, not a wrong conclusion (zero samples holds regardless).

**B.7 (rule engine) — 1 real finding:** `FormatCnicRule.field_names` confirmed matching. `CrossBranchCodeRule`'s non-registration comment is now partially stale: it claims `branch_code` has "no extraction... support anywhere in the pipeline," but `OneLinkLetterExtractor` (this session) and `TripartiteAgreementExtractor` both produce it. Normalization is still genuinely absent, so the practical conclusion (don't register yet) likely still holds — but the stated justification no longer matches the code. Also noted: `VisualSignatureFormalRequestRule` is registered and active for Formal Request Letter, even though CONTEXT.md frames that type as having "no extractor... at all" — that's true for the text-field layer but doesn't mention the visual-signature layer already exists.

**B.8:** `%.3f`-on-possibly-`None` bug confirmed still live, unfixed, at `confidence/services.py:339,342`. Cross-reference against a fresh full-suite run (Part F.1): zero occurrences of `"must be real number, not NoneType"` anywhere in the output — confirmed dormant in tests, live in code.

**B.9 (splitter):** Watermark/OCR-fallback fix and checklist-cover-page exclusion both confirmed present and unchanged. CNIC merge-artifact root cause identified (not just re-confirmed): reading the actual grouping loop (`splitter.py:230-259`) shows it's a structurally different failure from the already-fixed checklist bug — a *false negative* (a page with no header-zone title match gets unconditionally absorbed as a continuation of the preceding document) rather than a *false positive* (a listing page wrongly title-matched). This is a general limitation affecting any document type absent from the splitter's title table, not CNIC-specific.

**B.10:** Blank-page regression's origin (`fcc9fda`) confirmed untouched by any later commit — regression still live on `origin/main` by construction. Fresh full-suite run (Part F.1) confirms the exact same 13 named failures.

**B.11:** Cache-hit skip-logic confirmed genuinely incremental (early `return` on hit, never re-OCRs). Cache holds exactly 4 distinct source-file prefixes (`DG_Sports_KP_Onboarding_Documents`, `GDA_Abbotabad`, `GDC_Alpurai_Shangla`, `TMA_Khal_Dir_Lower`) — independently reconfirms the Conservator Wildlife Peshawar Zoo anomaly resolved below.

---

## Part C — Backend: Other Modules

**C.1:** `MAX_COPIES_BY_DOCUMENT_TYPE` confirmed (3 entries: `ONE_LINK_LETTER`:3, `TRIPARTITE_AGREEMENT`:3, `SCHEDULE_OF_CHARGES`:6 — highest). `REQUIRED_DOCUMENT_TYPES` confirmed (exactly 8 types, excludes CNIC). No application runtime logs exist in the repo to check for an actual cap-hit — still purely theoretical. `GDA_Abbotabad.pdf`'s real split produced exactly 3 `ONE_LINK_LETTER` copies (right at that type's cap, never exceeding it); zero real `SCHEDULE_OF_CHARGES` samples have ever turned up, so that cap has never been tested against real data.

**C.2:** Both `human_verification` and `validation` routers are registered on `protected_router`. Rigorously re-verified the "vestigial" claim at its exact stated granularity: `createValidationTask` has exactly one match in the entire frontend (its own definition in `services/validation.js:39`), and `useValidationTask.js` imports only the read-side functions. Claim holds precisely.

**C.3:** Reviewer-identity gap confirmed still open — zero reviewer/operator/user_id fields on `ValidationTask`/`ValidationLog`, and no migration in the 10 most recent touches this area.

**C.4 — one precision correction:** The frontend "audit" grep hits (`ValidationTaskDetailPanel.jsx`, `useValidationTask.js`, `OperatorDashboardPage.jsx`, `services/validation.js`) are a naming collision — all reference `ValidationLog`/the UI's "Audit Log" label for a `ValidationTask`'s history, not the actual `AuditLog` model. The "zero frontend consumers of `AuditLog`" claim still holds. Separately: the roadmap's "5 call sites" is accurate only as a **file count** (5 distinct modules write `AuditLog` entries) — the actual invocation count is **12** individual `.create()` calls (`confidence/services.py` alone has 6).

**C.5 — nuanced, not a contradiction:** A `_validate_environment` guard does exist (`config.py:142-151`, predates this session — present since `726a607`) — but it only fires when `ENVIRONMENT` is explicitly set to `"production"`. It does nothing to prevent the actual risk the roadmap flags: `ENVIRONMENT` defaulting to `"development"` with zero forcing function to ever set it correctly in a real production deployment. The roadmap's specific wording holds exactly as written.

**C.6:** `bulk_queue`'s `FOR UPDATE SKIP LOCKED` claim is real, implemented in `queue_job_repository.py:136` (`.with_for_update(skip_locked=True)` on PostgreSQL, plain `.with_for_update()` fallback for non-Postgres dialects). PR #7's `eba4e63` re-diff against `backend/` returns genuinely empty — zero backend overlap, confirmed.

**C.7:** PyMuPDF (`pymupdf>=1.24,<2.0`, locked at `1.28.2`) still the PDF library in use. No licensing resolution, swap, or new comment found anywhere.

---

## Part D — Frontend Audit

**Premise check:** Zero frontend-touching commits since `53cc394` — confirmed, holds.

**D.1 — per-type frontend footprint, 10 types:** All 7 backend-checklist-matched types + CNIC (as a combined front/back entry) appear in `frontend/src/data/documents.js` — the frontend's own single-source-of-truth upload/progress catalogue. **`FORMAL_REQUEST_LETTER` has zero hits anywhere in the frontend, including this catalogue.** The backend's `REQUIRED_DOCUMENT_TYPES` (8 types, includes `FORMAL_REQUEST_LETTER`, excludes CNIC) and the frontend's `DOCUMENT_TYPES` (8 entries, includes CNIC, excludes `FORMAL_REQUEST_LETTER`) are two **different** 8-item sets. Severity is nuanced, not a hard blocker: the separate `BulkUploadZone`/`uploadBulk` path (the one actually used for every real file this session) bypasses this catalogue entirely and lets the backend splitter classify pages into any `DocumentType`, including `FORMAL_REQUEST_LETTER` — so a real one can enter the system. But `computeDocumentProgress` only counts against the frontend's own catalogue, so the checklist/progress UI would never register a `FORMAL_REQUEST_LETTER` document even if the backend stored one and required it for completeness.

**D.2:** Given D.1's finding that `documents.js` only carries type/label/copy-count metadata (not per-field labels), and no dedicated per-type result-rendering component was found for any of the 7 extractor types, this session's new field names rely entirely on generic key-iteration rendering, not type-specific display — consistent across all 7, not a per-field gap.

**D.3:** 4 test files / 14 tests, all passing. Apparent growth over an assumed "3 files/8 tests" baseline is fully explained by `eba4e63` (2026-08-16, part of already-merged PR #6, already in CONTEXT.md) — not undocumented drift; the baseline assumption itself was stale.

**D.4 — major finding:** Full lint output is **27 errors + 5 warnings = 32 problems**, not the 5 previously catalogued. All 5 known errors confirmed present, unfixed, unsuppressed. ~22 more errors were never documented anywhere, including two different, more serious rule categories never mentioned before: `react-hooks/static-components` (`ApplicationTable.jsx` — a `SortIcon` component defined inside the render function, ×3 call sites) and `react-hooks/purity` (`SessionTimeoutModal.jsx` — impure `Date.now()` called during render via `useRef(Date.now())`). Confirmed this isn't a dependency-version drift — `eslint-plugin-react-hooks@7.1.1` is identically pinned in `package.json`, the lockfile, and installed `node_modules`. The "5 known errors" list was simply an incomplete snapshot from whenever it was last written, not a full inventory.

Full list of the ~22 previously-uncatalogued errors/warnings, by file:
- `AuthProvider.jsx:50` — setState-in-effect (`checkAuthentication()`)
- `ApplicationTable.jsx:58,70,80` — "Cannot create components during render" (`SortIcon`, `react-hooks/static-components`)
- `SessionTimeoutModal.jsx:15` — "Cannot call impure function during render" (`Date.now()` in `useRef`, `react-hooks/purity`)
- `BulkUploadZone.jsx:1` — `'React' is defined but never used`
- `DashboardLayout.jsx:29` — setState-in-effect (`setDrawerOpen(false)`)
- `ReportIssues.jsx:4` — `'getRuleResultStatus' is defined but never used`
- `DocumentDetailPanel.jsx:9` — `'entry' is assigned a value but never used`
- `useApplication.js:29` — setState-in-effect (`reload()`)
- `useDocuments.js:118` — warning, unnecessary `useCallback` dependency
- `useHumanReview.js:75,115` — setState-in-effect ×2
- `useLastOpenedApplication.js:3` — `'setPreference' is defined but never used`
- `useProcessingOverview.js:76` — setState-in-effect
- `useProcessingProgress.js:69` — setState-in-effect
- `useValidationReport.js:87,151` — setState-in-effect ×2
- `useValidationTask.js:51` — setState-in-effect
- `useValidationTasks.js:39` — setState-in-effect
- `useVerification.js:109` — setState-in-effect
- `ApplicationsContext.jsx:128,146` — warnings (unnecessary dependency, fast-refresh export)
- `ThemeProvider.jsx:5` — warning (fast-refresh export)

**D.5:** Build succeeds cleanly. Two previously-undocumented items: an `INEFFECTIVE_DYNAMIC_IMPORT` warning (`services/documents.js` both statically and dynamically imported, no actual code-splitting benefit), and a **43MB video file** (`8387491-uhd_3840_2160_30fps.mp4`) bundled directly into `dist/assets/`.

**D.6:** Focus-trap gap re-confirmed present, unchanged, in both `SessionTimeoutModal.jsx` and `ConfirmDialog.jsx` — zero focus/autoFocus/trapFocus references in either.

**D.7:** Established as plain fact — `BulkUploadZone` strictly handles one file at a time (`e.dataTransfer.files[0]`/`e.target.files[0]`), no multi-file queueing exists in the current UI.

---

## Part E — Backend-Frontend Contract Consistency

**E.1:** `document_analysis` schema (`schemas.py:88-129`) exposes `verification_status: str` directly, but the frontend never consumes this raw field for document-level status display — `useVerification.js:178` always substitutes a client-side-derived value (`deriveDocumentStatus`, built from raw rule results) before anything reaches `VerificationStatusBadge`. The backend field isn't silently dropped so much as silently bypassed by a parallel client-side computation.

**E.2:** Backend `VerificationStatus` has 4 values (`VERIFIED`, `PARTIALLY_VERIFIED`, `NEEDS_REVIEW`, `FAILED`). Frontend's `VERIFICATION_STATUSES` catalogue has 6 different, client-invented values (`VERIFIED`, `REVIEW_REQUIRED`, `FAILED`, `MISSING`, `PENDING`, `REJECTED`). `getVerificationStatus`'s `default` case safely falls back to `REVIEW_REQUIRED` for anything unrecognized — no crash risk today. But since the raw backend field is never actually wired into this badge (per E.1), `PARTIALLY_VERIFIED`/`NEEDS_REVIEW` are latent gaps, not active ones — they'd only matter if someone later connects the raw field directly.

**E.3:** The `ONE_LINK_LETTER` frontend label (`"1-Link Application Form"`, `documents.js:31`) is stale, confirmed directly against this session's own finding — real samples are a Participation Memorandum, not the Application Form.

---

## Part F — Test Suite Accuracy Audit

**F.1:** Fresh full suite: **765 passed, 13 failed**, all in `test_document_analysis_api.py`. Failing test names, name-for-name identical to the session's established baseline (no new failures, none of the known 13 now passing):
- `test_analyze_unknown_document_type_persists_needs_review`
- `test_analyze_recognized_checklist_type_stores_real_type_not_unknown`
- `test_analyze_every_checklist_type_is_recognized_not_unknown[BILATERAL_AGREEMENT / ACCOUNT_MAINTENANCE_CERTIFICATE / ONE_LINK_LETTER / AUTHORITY_LETTER / SCHEDULE_OF_CHARGES / BUSINESS_REQUIREMENT_DOCUMENT / FORMAL_REQUEST_LETTER / CNIC_FRONT / CNIC_BACK]` (9 parametrized cases — `TRIPARTITE_AGREEMENT` correctly absent, per its own dedicated test)
- `test_analyze_other_supporting_document_still_reports_unknown`
- `test_analyze_partial_unknown_type_does_not_block_known_documents`

B.8's confidence-bug cross-reference: zero hits for its error signature anywhere in this run. B.10's blank-page regression cross-reference: `TECH_BLANK_PAGE` appears 42 times, consistent with it still being the shared failure mechanism.

**F.2 (fixture realism, 3 extractors checked):** Authority Letter, CNIC Front, and 1-Link Letter fixtures all confirmed to precisely and genuinely mirror their extractors' own docstring claims about real-sample structure — zero drift found in any of the three. The Authority Letter docstring's explicit "only the prose-embedded variant is validated... a non-matching document extracts nothing" note independently cross-validates B.5.1's finding: the two empty-extraction real samples don't match either of the two documented real variants, reinforcing that they're a splitter misclassification rather than a third legitimate Authority Letter shape.

**F.3 (placeholder re-sweep, all 8 types):** Full re-sweep confirms both previously-fixed placeholder cases (`test_analyze_payslip_from_scanned_image`, `test_confidence_api.py`'s helper) hold up correctly — both swapped to `SCHEDULE_OF_CHARGES`, still genuinely unmapped, with accurate docstrings explaining the swap. Zero new placeholder-fixture-trap usages found across any of the 8 checklist types.

---

## Part G — Documentation Accuracy Audit

**G.1 — CONTEXT.md claim-verification table** (session boundary: `b040927`, Phase 0's splitter fix):

| CONTEXT.md claim | Verdict | Backing |
|---|---|---|
| `_CHECKLIST_TYPE_MAP` has exactly 7 entries (named) | Accurate | B.2 |
| `_EXTRACTORS` has 11 entries, sane failure mode | Accurate | B.3 |
| Authority Letter: "two confirmed structural variants," both extract cleanly | Incomplete — 2 of 5 real cached samples extract nothing and were never mentioned | B.5.1, F.2 |
| BRD: 3 real samples, 3 structural shapes, both fields extract | Accurate | B.5.2 |
| AMC: 2 documented issues (`/IBAN` garbage capture, all-3-fields-empty) | Accurate, both still present unfixed | B.5.3 |
| Tripartite: zero real samples, extractor unchanged since `bb3ebfb` | Accurate | B.5.4 |
| 1-Link Letter: 4 samples/2 orgs, `branch_code` only on 1 of 4 | Accurate | B.5.5, F.2 |
| Bilateral Agreement: zero real samples, extractor unchanged since `08bec31` | Accurate | B.5.6 |
| CNIC Front: 2/3 `VERIFIED`, 1/3 `PARTIALLY_VERIFIED` (missing only `date_of_expiry`) | Accurate, exact match | B.5.7, F.2 |
| Formal Request Letter / Schedule of Charges: zero real samples, "5 processed sources"/"16 of 21" | Stale count (true conclusion, outdated number) — real split at audit time was 11 checked / 10 untouched | B.6 |
| `CrossBranchCodeRule` unregistered because branch_code has "no extraction support anywhere" | Now partially stale — extraction exists, normalization doesn't | B.7 |
| `confidence/services.py` `%.3f`-on-`None` bug, unfixed | Accurate, and confirmed dormant (0 hits) in the fresh full-suite run | B.8, F.1 |
| Splitter fixes (watermark, checklist-cover-page) still in place | Accurate | B.9 |
| CNIC merge-artifact "shape-similar to the checklist bug, root cause not checked" | Superseded — root cause now identified as a genuinely different mechanism | B.9 |
| Blank-page regression (`fcc9fda`) still live, same 13 named failures | Accurate, exact name match | B.10, F.1 |
| AuditLog "5 call sites" | Imprecise — accurate as a file count, actual invocation count is 12 | C.4 |
| `ENVIRONMENT` defaults to development, no guard against unset value in prod | Accurate as literally worded | C.5 |
| `bulk_queue` `FOR UPDATE SKIP LOCKED` claim | Accurate | C.6 |
| PR #7 zero backend overlap | Accurate, re-diff confirmed empty | C.6 |
| PyMuPDF still in use, no licensing resolution | Accurate | C.7 |
| `validation` module "vestigial" | Accurate, re-verified at exact claimed granularity | C.2 |
| Bilateral Agreement search running total (8 files, "13 of 21" untouched, at audit time) | Corrected same day — batch 3 (3 more files) recorded, Conservator Wildlife Peshawar Zoo.pdf's check-depth corrected, running total now 11/21 checked, 10/21 untouched | commits `05dc1cc`, `baa0632` |
| "1-Link Letter is a Participation Memorandum, not the §4 Application Form" | Accurate, and the frontend's own checklist label was never updated to reflect it | E.3 |
| Teammate sign/stamp cross-check (6-of-7 resolved, 2 discrepancies, 2 omissions, "Onboarding" unresolved) | Accurate, not re-derived this pass, no contradicting evidence surfaced | — |

No entry in CONTEXT.md was found outright wrong — every deviation found is either a stale number/list, an incomplete claim missing a caveat, or something this audit's own findings superseded for the better (the CNIC root-cause writeup).

**G.2:** Roadmap staleness confirmed as predicted — status header (line 5, dated 2026-08-16) and CNIC scoping note (line 39) both predate BRD/1-Link/CNIC work and the CNIC scope decision. Line 25's "zero field extraction" claim is stale (7 of 9 types have it). Phase 4 items (AuditLog, `ENVIRONMENT`, reviewer-identity, focus-trap) all match what Parts C/D independently found.

**G.3:** First 5 still-unfixed bug-triage items (file order: refresh-cookie `remember=True` hardcoded, `ENVIRONMENT` guard gap, `useVerification.js` missing request-ID guard, `DOCUMENT_STATUSES` collapsing 3 states into "Uploaded," commit-before-audit-log in `confidence`/`normalization`) — all 5 confirmed still present, unchanged, accurately described.

**G.4:** `docs/Master_Rules_Combined.md` confirmed untouched by any commit since project inception (only 2 commits ever, both pre-dating the `726a607` restructure). No section-number-shift risk.

---

## Part H — Consolidated Report

### 1. Confirmed accurate

- `_CHECKLIST_TYPE_MAP` (7 entries) and `_EXTRACTORS` (11 entries) exactly as documented, with a sane failure mode on any gap
- BRD, Tripartite, Bilateral Agreement, 1-Link Letter, CNIC Front extractor claims — all exact matches against fresh real-sample re-runs
- Both AMC findings (`/IBAN` garbage capture, all-3-fields-empty) still present, unfixed, exactly as described
- Splitter fixes (watermark/OCR-fallback, checklist-cover-page exclusion) both confirmed in place
- Blank-page regression: same 13 named test failures, name-for-name, in a fresh full-suite run
- `bulk_queue`'s `FOR UPDATE SKIP LOCKED` claim, PR #7's zero-backend-overlap, PyMuPDF still in use — all confirmed
- `validation` module "vestigial" framing re-verified at its exact claimed granularity
- All 3 fixture-realism spot checks (Authority Letter, CNIC Front, 1-Link Letter) — zero drift
- Full placeholder-fixture-trap re-sweep across all 8 checklist types — zero new traps
- `docs/Master_Rules_Combined.md` genuinely untouched since project inception
- First 5 bug-triage items spot-checked — all still present, accurately described

### 2. Stale but not wrong

- Formal Request Letter / Schedule of Charges blockers cited "5 processed sources"/"16 of 21" at audit time — true conclusion (zero samples), outdated count (now corrected to 11/10 for the Bilateral Agreement entry; the other two entries' outer framing was explicitly left alone per earlier scope instructions)
- `IMPLEMENTATION_ROADMAP.md`'s status header and CNIC scoping note predate this session's BRD/1-Link/CNIC work
- AuditLog "5 call sites" — accurate as a file count, not a literal invocation count (actual: 12)
- `CrossBranchCodeRule`'s non-registration comment cites "no extraction support anywhere" — now half-true; extraction exists, normalization doesn't

### 3. Real discrepancies found

| Finding | Severity | Evidence |
|---|---|---|
| `FORMAL_REQUEST_LETTER` absent from the frontend's own upload/progress catalogue (`documents.js`) while present in the backend's `REQUIRED_DOCUMENT_TYPES` — the checklist/progress UI would never register one even if the backend produced and required it | Worth fixing soon (not a hard blocker — bulk upload bypasses the catalogue) | D.1 |
| Lint state far worse than documented: 27 errors vs. 5 previously catalogued, including two more serious never-mentioned categories | Worth fixing soon | D.4 |
| 43MB video bundled into the production build | Worth fixing before a demo if load time/deploy size matters | D.5 |
| Authority Letter: 2 of 5 real samples extract nothing, structurally a checklist/enclosures page, not Authority Letter content — plausible splitter misclassification never documented | Worth fixing soon | B.5.1, F.2 |
| Two pre-existing unexpected-field mismatches (`BankStatementExtractor`'s `total_credits`/`total_debits`, `IdentityExtractor`'s `issue_date`) silently never scored | Cosmetic | B.4 |
| `INEFFECTIVE_DYNAMIC_IMPORT` build warning | Cosmetic | D.5 |

### 4. New findings

- CNIC merge-artifact root cause identified: a genuinely different mechanism from the already-fixed checklist-cover-page bug — a structural "any page without its own header-zone title match gets silently absorbed as a continuation of the preceding document" limitation, not CNIC-specific (B.9)
- Backend/frontend `VerificationStatus` vocabularies are completely disjoint (4 backend values vs. 6 frontend-invented ones) — currently harmless because the raw backend field is never actually wired into the badge component, but latent (E.1, E.2)
- `ONE_LINK_LETTER`'s frontend label is stale ("1-Link Application Form") given this session's own Participation Memorandum finding (E.3)
- Conservator Wildlife Peshawar Zoo.pdf's check-depth was overstated across 3 CONTEXT.md entries — resolved and corrected same day (commit `baa0632`)

### Recommendation for an imminent demo

Two items from bucket 3 matter most if the demo touches the frontend at all: the 43MB bundled video (real load-time risk) and the `FORMAL_REQUEST_LETTER` catalogue gap (if the demo walks through a full checklist, this type will never show as fulfilled even if uploaded). The lint findings and Authority Letter misclassification are real but unlikely to surface visibly in a live walkthrough — safe to document and fix after. Everything in bucket 1/2 needs no action before a demo.

### Audit coverage

All of Parts A through H were completed in this pass, across two conversation turns. Nothing was skipped or cut short.

---

## Addendum — Remediation Pass (Phases 3-8, same day)

Bucket-3 findings above were addressed directly after this audit, same day, in a separate 8-phase pass. Phases 1-2 pushed the pending commits and persisted this document; this addendum covers what Phases 3-8 actually did to the findings in bucket 3. Several `react-hooks/set-state-in-effect` suppression comments elsewhere in the frontend point back to "the full-stack audit, Phase 8" — this section is what those comments resolve to.

**Phase 3 — field-scoring gaps (`f0c2e15`).** Added `total_credits`/`total_debits` to `EXPECTED_FIELDS[BANK_STATEMENT]` and `issue_date` to `EXPECTED_FIELDS[ID_DOCUMENT]` (`document_analysis/constants.py`), closing B.4's finding. Verified against the existing fixture text that both fields now extract and score; full suite re-run held at the same 765 passed / 13 failed baseline (Part F.1), confirming no side effects.

**Phase 4 — frontend catalogue gap (`0adc3df`).** Added `FORMAL_REQUEST_LETTER` to `DOCUMENT_TYPES` in `frontend/src/data/documents.js`, closing D.1's finding. Verified directly that `computeDocumentProgress` now registers a document of this type as complete; frontend suite unaffected (still 4 files / 14 tests passing).

**Phase 6 — dead dynamic import (`96e75c1`).** `services/documents.js`'s `uploadBulkDocument` was already imported statically elsewhere in `useDocuments.js`; the redundant `await import('../services/documents')` inside the upload-bulk handler could never actually be code-split by Vite, so it was pure runtime overhead. Folded into the existing static import; the `INEFFECTIVE_DYNAMIC_IMPORT` build warning from D.5 is gone.

**Phase 5 — 43MB video (investigated, no fix).** `LoginVideoBackground.jsx`, mounted unconditionally by `LoginPage.jsx`, is real feature code, not dead weight: it respects `prefers-reduced-motion`, uses `preload="metadata"` (so the full 43MB isn't pulled until playback actually starts), is muted/looped/controls-free, and has an error fallback. No fix was applied — genuinely shrinking the bundle would mean re-encoding the video or moving it to external/CDN hosting, and the app currently has no code-splitting infrastructure to extend for a lazy-load approach, so lazy-loading alone wouldn't move `dist/assets/`'s on-disk size, only defer a download that's already effectively deferred. Re-encoding/CDN hosting is a product decision (quality/cost tradeoffs) outside this pass's scope — left as an explicit open item, not silently dropped.

**Phase 7 — Authority Letter misclassification (investigated, unresolved).** B.5.1 found 2 of 5 real cached samples extracting nothing, structurally resembling a checklist/enclosures listing rather than Authority Letter body text. Read `splitter.py`'s classification/grouping loop (`_classify_page`, lines 272-328; grouping, lines 230-259) against the real samples' line-position evidence in the OCR cache (line numbers/positions only, no content quoted, per PII rules). Found a genuine contradiction: the `_CHECKLIST_PAGE_MARKER` exclusion should, on a naive reading of the code, have caught these pages before they could false-match on "AUTHORITY LETTER," since the checklist marker text appears at an earlier line than the false-matching title — but empirically it didn't fire. Two mechanisms remain equally plausible and could not be distinguished from plain-text OCR cache alone: (1) the checklist content spans multiple pages and the false-matching page is a continuation page the marker never appears on, or (2) OCR read-order diverges from true Y-position on these pages, the same phenomenon already documented for the CNIC scrambled-order sample (B.9) — meaning the "earlier line number" isn't actually "higher on the page." Distinguishing the two needs page-boundary/coordinate data the cached plain text doesn't carry. No fix was proposed or applied — stopping short of a guess, per the same discipline used for the CNIC root-cause writeup.

**Phase 8 — lint (27 errors + 5 warnings → 0 errors + 3 warnings).** Addressed by category, each its own commit:

- *Real behavioral fixes* — the cases where the underlying code was genuinely wrong, not just unsuppressed:
  - `SessionTimeoutModal.jsx` (`788dddf`) — `react-hooks/purity`: `Date.now()` was being called during render via `useRef(Date.now())`. Two approaches were tried and rejected before the fix that stuck: a guarded `if` around the ref assignment in render body still trips `react-hooks/purity` (the rule doesn't special-case idempotent-but-conditional impure calls in render); a `useState(() => ({ current: Date.now() }))` lazy initializer satisfied purity but tripped a separate rule against mutating a `useState`-held value directly instead of through its setter. The fix that worked: kept `useRef(null)`, moved the one-time `Date.now()` assignment into a mount-only `useEffect` (`[]` deps) — the pattern React's own lint rules actually accept for one-time impure initialization of a ref.
  - `DashboardLayout.jsx` (`003981a`) and `HumanReviewPage.jsx` (`dbfe266`) — `react-hooks/set-state-in-effect`, but not the fetch-on-mount kind: both were "reset state when a tracked value changes" patterns (route change closing a drawer; selected-item change resetting review form fields) miscoded as effects. Rewritten using React's documented render-time-adjustment pattern (compare a tracked "previous" value against the current one in the render body, call `setState` conditionally there instead of in an effect) — the officially correct fix, not a suppression.
  - `ApplicationTable.jsx` (`04e4a00`) — `react-hooks/static-components`: `SortIcon` was defined as a closure inside `ApplicationTable`'s render function, so React treated it as a new component type on every render and remounted instead of updating it. Hoisted to module scope as a standalone function, with `sortKey`/`sortDir` now passed explicitly as props at all 3 call sites instead of closed over.
- *Suppressed with reasoning, not fixed* (`14503ef`) — 11 call sites across `AuthProvider.jsx` and 9 hook files (`useApplication.js`, `useHumanReview.js` ×2, `useProcessingOverview.js`, `useProcessingProgress.js`, `useValidationReport.js` ×2, `useValidationTask.js`, `useValidationTasks.js`, `useVerification.js`) are genuine fetch-on-mount `useEffect`s — the standard "load data when this component/hook mounts" pattern, which `react-hooks/set-state-in-effect` flags unconditionally with no special case for it. Restructuring these to avoid the rule would mean inventing a non-standard data-fetching pattern with no real correctness benefit, so each carries an explicit `eslint-disable-next-line react-hooks/set-state-in-effect` with a comment pointing back to this addendum, rather than a silent blanket suppression.
- *Pure dead code, no behavior change* (`dbfe266`, `236fffa`) — 5 unused-import/unused-variable errors (`BulkUploadZone.jsx`'s unused `React` import, `ReportIssues.jsx`'s unused `getRuleResultStatus` import, `DocumentDetailPanel.jsx`'s dead `entry` IIFE, `useLastOpenedApplication.js`'s unused `setPreference` import, `UploadDocumentsPage.jsx`'s unused `getApiErrorMessage` import, `ValidationReportPage.jsx`'s unused `rules` destructure) plus 2 unnecessary `useCallback`/`useMemo` dependencies (`useDocuments.js`'s `uploadToSlot`, `ApplicationsContext.jsx`'s applications-list memo) and 3 redundant imports in `ApplicationsContext.jsx` (`replaceDocument`/`uploadDocument`/`deleteDocument`, never called from that file).
- *Deliberately left unfixed* — 3 `react-refresh/only-export-components` warnings remain (`ToastContext.jsx`, `ApplicationsContext.jsx`, `ThemeProvider.jsx`). These are dev-only HMR-smoothness concerns with zero production impact; a "proper" fix means splitting each into a component-only file and a separate hook/context file, touching every consumer of 3 app-wide core hooks — judged disproportionate blast radius for a cosmetic dev warning. This is a known, intentional gap, not an oversight.

Final verification after all of Phase 8: `npm run lint` → 0 errors, 3 warnings (the 3 listed above, nothing else); frontend suite → 4 files / 14 tests passing, unchanged; `npm run build` → succeeds, `dist/assets/`'s video entry unchanged in size as expected per Phase 5's no-fix decision.

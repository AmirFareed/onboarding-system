# Implementation Roadmap — Path to "Complete"

Last updated: 2026-08-15. Written after a foundation audit, a remediation phase (4 issues fixed and shipped), and a first real-data end-to-end test that surfaced a critical splitter bug. This is a forward-looking plan — for what already happened, see `CONTEXT.md`.

**Status as of 2026-08-16**: Phase 0 is done (verified on real data, `b040927`, plus a follow-up classifier fix `68d47d6` for a checklist-page false positive found while verifying it). Phase 1 is underway: item 1 (Bilateral Agreement) has a real extractor committed (`08bec31`), real-sample validation still pending; item 2 (Authority Letter) is in progress. See `CONTEXT.md` for the verified details — this file's phase descriptions below are left as originally written (the plan, not the log).

**How to use this document**: each phase has a concrete definition of done. Phases are ordered by dependency and risk, not by how interesting they are — later phases are often blocked on earlier ones actually working. "Complete" is defined at the bottom; nothing here should be treated as done until its own definition-of-done is met and verified, ideally against a real file from `Confidential Data/`, not just synthetic tests.

---

## Phase 0 — Fix the splitter threshold bug (BLOCKING, do this first)

**Found:** `app/preprocessing/splitter.py`'s OCR fallback only triggers when a page's native PDF text is under 10 characters (`len(full_text.strip()) < 10`). CamScanner-exported real scans carry a "CamScanner" watermark as native text — exactly 10 characters. `10 < 10` is `False`, so OCR never runs during splitting, and the splitter reads only the watermark as the entire page. No page ever matches a title phrase, so every page merges into one `OTHER_SUPPORTING_DOCUMENT`.

**Verified impact:** ran a real file (`TMA Khal Dir Lower.pdf`) through the live pipeline end-to-end. Result: 10 pages collapsed into 1 document; all 8 required-document-completeness rules FAILed as "missing," even though the actual content exists in the file. Checked all 21 real files in `Confidential Data/`: **12 of 21 (57%) hit this exact bug** (CamScanner exports with the 10-char watermark). The other 9 have zero native text and were not confirmed to split correctly either — untested, not verified-good.

**Fix:** change the threshold so a watermark-only page still triggers OCR. Don't just guess a new magic number — measure the actual native-text length of a representative sample of real non-CamScanner scans first (some scanning apps/watermarks may differ), then pick a threshold with real headroom (e.g. comparing against a small allowlist of known watermark strings, or a threshold like 30-50 chars, would be more robust than another exact-boundary guess).

**Definition of done:** re-run the same real file end-to-end. Splitting must produce a document per real document type present (not perfect classification of every page yet — that's Phase 1 — just correct *separation*, not one merged blob). Then run all 21 real files through splitting only (not full processing, to keep this fast) and confirm each produces more than 1 document. Add a regression test using a fixture with exactly 10 characters of native text, so this exact bug can never silently return.

---

## Phase 1 — Real field extraction for the 9 required-document checklist types

Today: `detect_document_type`/the 4 `RegexExtractor` classes only handle bank statement, payslip, ID document, tax document — none of which are actually in the required checklist. The 9 real checklist types (Tripartite Agreement, Bilateral Agreement, Account Maintenance Certificate, 1-Link Letter, Authority Letter, Schedule of Charges, BRD, Formal Request Letter, plus CNIC) get correctly *labeled* (fixed this session) but have zero field extraction.

**Why this can't be done blind:** confirmed by OCR'ing real samples — the same document type is worded completely differently between departments. One real Authority Letter used clean `Name:`/`Designation:`/`CNIC:` fields; a different department's real Authority Letter embedded the same information in a prose sentence. A single regex pattern per type will not reliably cover both. Each type needs patterns validated against **multiple** real samples, not one.

**Recommended sequence** (tractability, based on real samples already reviewed):
1. **Bilateral Agreement** — real sample shows a genuinely structured transaction-charge table (PKR tiers) and a bank name/account number table. Best-structured of the 9, start here.
2. **Authority Letter** — two real structural variants already identified; build extraction that handles both (labeled block AND prose-embedded), or falls back cleanly when neither matches.
3. **Business Requirement Document** — real sample shows a department-background paragraph plus a list of named revenue services; moderately structured.
4. **Formal Request Letter** — short, subject-line-driven; check the master rules requirement that the subject line state onboarding intent explicitly.
5. **Account Maintenance Certificate, Tripartite Agreement, 1-Link Letter, Schedule of Charges** — no real sample reviewed yet for these; get real examples from `Confidential Data/` before writing any pattern.
6. **CNIC** — see the scoping note below before doing any extraction work here.

**For each type, definition of done:** a `RegexExtractor` subclass, `EXPECTED_FIELDS`/`CRITICAL_FIELDS` entries, extraction validated against at least 2-3 real samples from `Confidential Data/` (not just synthetic test fixtures — real OCR noise and phrasing variation is exactly what breaks naive patterns), and unit tests using synthetic fixtures that mirror the real structural patterns found (never commit real extracted PII into test fixtures — paraphrase/fabricate equivalent-shape data instead).

**CNIC scoping decision needed:** `docs/Master_Rules_Combined.md` itself notes CNIC/Declaration is "excluded from current scope where specified, but CNIC copies... checked when present." No presence rule or extractor exists for CNIC today. Confirm with the department whether this is still the intended scope, or whether CNIC now needs full presence + format + expiry checking like the other 8.

---

## Phase 2 — Visual and structural verification (signatures, stamps, templates)

Re-reading `Master_Rules_Combined.md` carefully: **most of what it actually asks for isn't text extraction at all.** Signature presence, stamp color/authenticity, watermark texture (E-Stamp papers), notary seals, point-numbering conformance, exact template wording — none of this is answerable by regex over OCR text. This needs image-region analysis, not field extraction.

**What already exists:** `VisualSignature*`/`VisualStamp*` rules for 5 of the 9 types (Tripartite, Bilateral, AMC, Authority Letter, One-Link) are implemented and registered — worth checking exactly what evidence they currently look for and whether it's been validated against a real signed/stamped document.

**What doesn't exist at all:** Schedule of Charges, BRD, Formal Request Letter have no visual rules. E-Stamp visual authentication and Notary Public stamp detection have no implementation anywhere. Template point-numbering/wording conformance has no implementation.

**Important, and stated explicitly in the master rules document itself (Section 15):** *"The system checks signature presence and required location, not signature authenticity... The authorized employee remains the final decision-maker."* Full automation of this category was never the intent. The realistic goal here is presence/location detection to reduce manual review load, not a system that "approves" signatures — don't let this phase's scope quietly expand into something the business rules never asked for.

**Definition of done per document type:** signature-region and stamp-region detection (presence + rough location), tested against real signed/stamped samples, feeding into the same `PENDING_MANUAL_REVIEW`/`WARNING` pattern the existing visual rules already use (never a hard automated `PASS` on authenticity).

---

## Phase 3 — Cross-document consistency, completed

Already registered and working: IBAN, account holder, account number, and period consistency checks across documents (`cross_document_rules.py`). These will start actually firing meaningfully once Phase 1 gives them real fields to compare (Account Maintenance Certificate's account number vs. Bilateral/Tripartite Agreement's, per the master rules' explicit "must perfectly match" requirement).

**`CrossBranchCodeRule` exists but is deliberately unregistered** — no `branch_code` extraction/normalization exists anywhere yet. Register it only once branch-code extraction is real (likely falls out of Phase 1's Account Maintenance Certificate / Bilateral Agreement work, since branch name/number appears in both per the master rules doc).

**Definition of done:** run a real multi-document real application through the full pipeline once Phase 1 covers Account Maintenance Certificate + Tripartite + Bilateral, confirm consistency rules correctly PASS on a real matching set and correctly FAIL when a synthetic mismatch is introduced.

---

## Phase 4 — Remaining operational hardening (from the foundation audit, not yet fixed)

These were found during the earlier audit and are independent of the extraction work above — pick these up whenever, they don't block or get blocked by Phases 0-3:

- **`ENVIRONMENT` has no enforcement.** Defaults to `"development"`; a deployer who forgets to set it to `production` silently ships with debug mode, the dev secret key, and the dev seed password. Needs either a startup check that refuses to boot with unset `ENVIRONMENT` in an obviously-production-like deployment, or at minimum a loud, impossible-to-miss log warning.
- **`validation` module has no reviewer-identity field.** `ValidationTask`/`ValidationLog` record what happened, never who did it. Needs a migration (new column on both tables) plus wiring `current_user` through the module's routes, the same way it was already done for `human_verification`/`confidence`/`upload`.
- **Modal focus management missing.** `SessionTimeoutModal` and `ConfirmDialog` don't trap focus or move focus in on open — a keyboard/screen-reader user can tab through obscured background content. Isolated, low-risk fix.
- **`AuditLog` is write-only.** 5 call sites write to it, nothing reads it back — no route, no UI. Needs a product decision first: surface it (new read-only audit-log view) or explicitly document it as intentionally internal-only. Not a coding task until that decision is made.
- **PyMuPDF AGPL licensing** — still an open legal question, still not a code task. Needs a decision-maker to confirm whether a commercial Artifex license covers this deployment before any production launch, independent of everything else in this document.

---

## Phase 5 — Batch multi-bulk-upload (10-20 PDFs, processed sequentially)

**Not yet investigated.** The existing async queue (`bulk_queue`) already processes documents concurrently across applications with safe claiming (`FOR UPDATE SKIP LOCKED`), which suggests the backend may already tolerate many bulk uploads in flight — but this has never been tested at that scale, and the frontend upload flow has not been checked for whether it supports queuing multiple bulk PDFs in one sitting versus one-at-a-time.

**Before writing any code here:** confirm the actual intended UX (is this "upload 10-20 PDFs in one session, system works through them" a single multi-file upload UI, or 10-20 separate applications created one after another?), then check current frontend/backend support for that specific shape before assuming anything needs building. This phase is independent of Phases 0-4 and can be scoped in parallel once someone's available to investigate it.

---

## Phase 6 — LLM-assisted extraction (optional, pending decisions)

An extraction fallback interface already exists (`app/document_analysis/fallbacks.py`, `FieldFallback` protocol) — narrow, opt-in, only sends specific missing/invalid field names plus document text, never a whole document, never on by default. No provider is wired in.

**Two decisions needed before real data touches this, both non-technical:**
1. **Data policy**: real CNICs/IBANs/government correspondence going to any external LLM API is a data-protection decision for whoever owns KPITB's data policy — not a decision to make in code. Free-tier cloud APIs (Gemini, Groq) are explicitly not appropriate for this without that sign-off; their terms typically permit using input data to improve the provider's models.
2. **Model choice for the local option**: a teammate has a 7B-class local model (Ollama) on capable hardware — sidesteps the data-policy question entirely since nothing leaves the machine. Confirm the exact model name and whether it'll run on a shared/network-reachable host or per-developer locally, before wiring a provider implementation.

**Value if built:** directly solves the cross-department phrasing-variation problem from Phase 1 — an LLM reading "who is the authorized person" handles both the labeled-field and prose-sentence real-world variants without a bespoke regex per department. Worth prototyping with **synthetic data only** regardless of which decision above lands, since that validates the approach with zero data-sensitivity risk.

**Definition of done:** a working `FieldFallback` implementation, tested against synthetic documents mirroring the real structural variants found in Phase 1, with `ai_fallback_enabled` still defaulting to `False` and a documented, deliberate decision (not a default) required to turn it on for real data.

---

## Ongoing — real-data testing practice

The Phase 0 bug existed through 704+ passing tests and multiple audit passes because nothing had ever run against real scanned data until today. Synthetic fixtures cannot reproduce real OCR noise, real watermarks, real inter-departmental formatting variance — as proven today.

**Recommendation:** before considering any phase "done," run it against at least one real file from `Confidential Data/` end-to-end, not just synthetic unit tests. Never commit real extracted values (names, CNICs, IBANs, account numbers) into test fixtures, commit messages, or code comments — paraphrase or fabricate equivalent-shaped synthetic data instead, exactly as this session did.

---

## What "complete" or "approaching complete" actually means

Given everything above, here is an honest bar, not a marketing one:

- **Minimum bar for a department demo**: Phase 0 fixed and verified on multiple real files; Phase 1 done for at least the top 2-3 most tractable types (Bilateral Agreement, Authority Letter); document-completeness reporting (already solid) demonstrated correctly on a real, correctly-split application; every other document type honestly shown as "recognized, human review required" rather than silently missing or wrongly auto-approved.
- **"Approaching complete"**: Phase 0-3 fully done for all 9 types, validated against real samples; Phase 4's operational items closed out; a clear, department-confirmed answer on CNIC scope and PyMuPDF licensing.
- **What "fully complete" would require, honestly**: Phase 2 (visual/stamp/template verification) is a materially different engineering problem (computer vision, template diffing) from everything shipped so far, and Section 15 of the master rules document itself says full automation was never the goal — a human stays in the loop by design. "Complete" for this system realistically means *maximally assisting* the human reviewer with high-confidence, well-tested automation for what's genuinely automatable (document completeness, financial-field extraction, cross-document consistency) — not eliminating the reviewer.

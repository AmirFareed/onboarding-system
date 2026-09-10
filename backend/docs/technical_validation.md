# Phase 5: Technical Validation

Technical validation is the first automated gate every uploaded document passes
after upload and completeness checking. It inspects only the **file bytes and
basic structural properties** of a document — never its content — and produces
one validation report per document.

- Module: `backend/app/technical_validation/`
- Endpoints:
  - `GET  /api/v1/applications/{application_id}/technical-validation`
  - `POST /api/v1/applications/{application_id}/technical-validation/validate`
- Results table: `validation_results` (Phase 2, reused)

## 1. Why technical validation is a separate phase

A document can be present, attached to the right application, and complete from
a metadata standpoint — yet still be unusable for downstream processing (a
corrupted PDF, a blank or low-resolution scan, a blurry or sideways photo).
Separating technical validation into its own phase gives the pipeline a single,
deterministic quality gate before any expensive work happens:

- It fails fast: problems are caught before OCR, field extraction, or rule
  evaluation spend resources on files that cannot be read.
- It produces a stable per-document quality contract (`validation_status`,
  `readability_status`, blur/rotation scores) that every later phase and the
  final validation report can reference.
- It keeps concerns isolated: upload owns ingestion and format acceptance,
  completeness owns required-document coverage, technical validation owns file
  quality. Each module stays small and independently testable.

## 2. Why OCR is excluded

Technical validation deliberately does not extract text, run OCR, or interpret
document meaning. Reasons:

- OCR is expensive and slow; running it on every document before knowing the
  file is readable would waste significant compute on bad files.
- OCR belongs to a later, content-facing phase where the extracted text feeds
  field extraction and the rule engine. Technical validation only establishes
  the precondition (readable, oriented, sharp enough) under which OCR has a
  chance of succeeding.
- Keeping the phase content-free keeps it deterministic and fast, so it can be
  re-run cheaply after a user re-uploads a corrected scan.

Readability is therefore **derived** from objective physical metrics —
resolution, blur score, and file integrity — rather than from what the content
says.

## 3. How PyMuPDF is used

PyMuPDF (`fitz`) handles everything PDF-related, in `validators.py`:

- `validate_pdf` opens the file with `pymupdf.open(path)`. Empty files raise
  `EmptyFileError`; garbage bytes raise `FileDataError`; both are mapped to
  `CorruptedPDF`.
- `doc.needs_pass` detects password-protected PDFs. The `PDF_OPEN` check still
  passes ("the file is a readable PDF; encryption detected") while the
  `PDF_PASSWORD` check fails, because the file is unusable downstream even
  though it opened from a storage standpoint.
- `doc.page_count` must be >= 1; otherwise the PDF is treated as corrupted.
- Page dimensions are validated on the first page: width and height must be
  finite and greater than zero (`PDF_DIMENSIONS`).
- `render_pdf_first_page` (in `utils.py`) renders the first page at 150 DPI
  into a BGR numpy array using a `Matrix(150/72, 150/72)` zoom, so the same
  blur/rotation helpers used for images can analyze the PDF's visual quality.
  A render failure only degrades visual analysis (warning), never fails the
  PDF: the file opened, so only the rendering step is unavailable.

## 4. How OpenCV is used

OpenCV (`cv2`) handles everything image-related:

- `validate_image` loads the file with `cv2.imread(path, cv2.IMREAD_COLOR)`.
  A `None` result (undecodable bytes) maps to `InvalidImage`.
- The resolution check (`cv2.imread` gives width/height; `MIN_IMAGE_WIDTH` /
  `MIN_IMAGE_HEIGHT` = 800) fails low-resolution scans that would produce
  unreadable OCR output (`IMAGE_RESOLUTION`).
- `variance_of_laplacian` converts the image to grayscale, applies the
  Laplacian with `CV_64F`, and computes the variance of the result — the blur
  score.
- `estimate_rotation_angle` runs Canny edge detection, the probabilistic Hough
  transform (`cv2.HoughLinesP`), folds detected line angles onto their nearest
  axis (0/90/180/270), and averages them length-weighted into a single
  estimated rotation angle in the range [-45, +45] degrees.

## 5. How blur detection works

Blur detection uses the **Variance of Laplacian** method:

1. Convert the image (or the rendered PDF page) to grayscale.
2. Apply the Laplacian operator (`cv2.Laplacian(..., cv2.CV_64F)`) — this is a
   second-derivative filter that responds strongly to sharp edges.
3. Compute the variance of the Laplacian output. A sharp document has high
   variance because it contains many strong edges; a blurry image is mostly
   flat, so the Laplacian output is near zero everywhere and the variance
   collapses.

The score is compared against `BLUR_THRESHOLD = 100.0`. Probe measurements gave
clean separation: a sharp synthetic contract page scores ~1200-1600 while the
same page blurred with a 21x21 Gaussian scores ~3-6. The threshold and the
value live in `constants.py` as the single tuning point. Below the threshold the
`IMAGE_BLUR` check fails and readability drops to `UNREADABLE`.

## 6. How rotation detection works

Rotation is **detected only — never corrected** (the phase has no
preprocessing step by design). The estimate pipeline:

1. Canny edge detection isolates long straight edges (table lines, text
   baselines) from noise.
2. `HoughLinesP` finds line segments; each segment's angle is computed from its
   endpoints.
3. Angles are folded onto their nearest axis (0, 90, 180, 270 degrees) so
   horizontal and vertical content both contribute.
4. Deviations from the nearest axis are averaged, weighted by segment length,
   yielding one angle estimate in [-45, +45].

If `abs(angle) >= ROTATION_TOLERANCE_DEGREES = 3.0`, the document is flagged
`ROTATED`. The rotation check is a **warning**, not a failure: rotated content
is often still machine-readable, so the overall status becomes `WARNING` and
readability drops to `PARTIALLY_READABLE`, prompting a re-scan without hard-
blocking the document. Live verification recovered an 8-degree rotation as
-7.99 degrees.

## 7. Why results are stored in the database

Each check is persisted as one row in the existing Phase 2 `validation_results`
table, so:

- **History is kept**: every validation run is stored with its timestamp
  (`validated_at`). Re-running validation appends new rows; old results remain
  available for audit and diffing. The `GET` endpoint reconstructs reports from
  stored rows, so what you read back always matches what a fresh run would
  produce.
- **Downstream phases and the final report can read them**: the rule engine,
  OCR phase, and validation-reports aggregator can query per-document quality
  scores (blur, rotation, readability) without re-analyzing files.
- **No new table is needed**: the Phase 2 schema was extended with four
  additive nullable columns (`document_id`, `blur_score`, `rotation_angle`,
  `file_format`) via one Alembic migration. Rule-engine rows are untouched —
  those columns stay `NULL` for them, keeping the two kinds of results
  distinguishable by `rule_category`.

## 8. Integration with other phases

- **Upload (Phase 3)**: upload already validated content magic bytes before
  persistence, so technical validation trusts the stored file and detects the
  format from the stored path suffix. Files are resolved through the same
  `StorageService` that upload uses.
- **Completeness (Phase 4)**: completeness answers "are the required documents
  present?". Technical validation answers "are the present documents usable?".
  A complete application can still fail technical validation; both checks are
  prerequisites for processing.
- **OCR**: technical validation is the gate OCR runs behind — only documents
  that are `READABLE` and un-rotated are good OCR candidates. The rendered
  first-page image produced here could be reused, but OCR itself is a later,
  separate phase.
- **Field extraction**: relies on OCR output, and therefore transitively on
  technical quality (readability, resolution, orientation) established here.
- **Rule engine**: `validation_results` rows carry `rule_category =
  'technical_validation'`, so the engine can distinguish technical-quality
  failures from business-rule failures and weight them accordingly in
  workflows and the final report.
- **Validation reports**: the final aggregate report includes each document's
  technical findings (`failed_checks`, `warnings`, `recommendations`) because
  they are persisted as first-class validation results rather than transient
  in-memory facts.

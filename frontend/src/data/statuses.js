/**
 * Status labels and colour variants.
 *
 * The `variant` values map to StatusChip CSS classes (used by the documents
 * module); the `color` values map to ApplicationStatusBadge CSS classes.
 * Application statuses mirror the backend `ApplicationStatus` enum; document
 * statuses cover the backend `DocumentProcessingStatus` values plus
 * client-side states (MISSING and UPLOADING) that never leave the browser.
 */

export const APPLICATION_STATUSES = [
  { value: 'SUBMITTED', label: 'Pending', variant: 'info', color: 'blue' },
  { value: 'PROCESSING', label: 'Processing', variant: 'info', color: 'sky' },
  { value: 'PROCESSING_FAILED', label: 'Processing Failed', variant: 'danger', color: 'rose' },
  { value: 'PENDING_REVIEW', label: 'Under Review', variant: 'warning', color: 'orange' },
  { value: 'NEEDS_DOCUMENTS', label: 'Awaiting Documents', variant: 'warning', color: 'orange' },
  { value: 'APPROVED', label: 'Approved', variant: 'success', color: 'green' },
  { value: 'REJECTED', label: 'Rejected', variant: 'danger', color: 'red' },
  { value: 'CORRECTED', label: 'Corrected', variant: 'neutral', color: 'purple' },
];

/**
 * Verification workspace statuses.
 *
 * Raw rule-engine outcomes (PASS, WARNING, PENDING_MANUAL_REVIEW, FAIL,
 * REJECTED) are mapped to employee-facing labels and StatusChip variants.
 * Derived per-document statuses (Verified / Review Required / Failed /
 * Missing / Pending) share the same catalogue so one lookup serves both.
 */
export const VERIFICATION_STATUSES = [
  { value: 'VERIFIED', label: 'Verified', variant: 'success' },
  { value: 'REVIEW_REQUIRED', label: 'Review Required', variant: 'warning' },
  { value: 'FAILED', label: 'Failed', variant: 'danger' },
  { value: 'MISSING', label: 'Missing', variant: 'neutral' },
  { value: 'PENDING', label: 'Pending', variant: 'info' },
  { value: 'REJECTED', label: 'Rejected', variant: 'danger' },
];

/**
 * Verification issue severities shown in the issue list.
 *
 * Backend severities (ERROR / WARNING / INFO) map to the employee-facing
 * Critical / Warning / Review Required vocabulary. Pending-manual-review rows
 * surface as "Review Required" rather than a raw enum value.
 */
export const VERIFICATION_SEVERITIES = [
  { value: 'CRITICAL', label: 'Critical', variant: 'danger' },
  { value: 'WARNING', label: 'Warning', variant: 'warning' },
  { value: 'REVIEW_REQUIRED', label: 'Review Required', variant: 'neutral' },
];

/**
 * Validation task lifecycle statuses (operator dashboard queue).
 *
 * Mirrors the backend `ValidationTaskStatus` enum.
 */
/**
 * Operator validation workflow events shown in an application's history.
 *
 * Raw backend `ValidationEventType` values are mapped to operator-friendly
 * labels so the UI never exposes internal implementation detail. Severity
 * drives the badge tone used in the history timeline.
 */
export const VALIDATION_HISTORY_EVENTS = [
  { value: 'DOCUMENTS_REQUESTED', label: 'Documents requested', variant: 'warning' },
  { value: 'DOCUMENTS_RECEIVED', label: 'Documents received', variant: 'success' },
  { value: 'OPERATOR_SUBMITTED', label: 'Submitted for processing', variant: 'info' },
  { value: 'OPERATOR_REJECTED', label: 'Rejected', variant: 'danger' },
  { value: 'SUBMITTED_FOR_PROCESSING', label: 'Submitted for processing', variant: 'info' },
  { value: 'PROCESSING_FAILED', label: 'Processing failed', variant: 'danger' },
  { value: 'REVIEW_APPROVED', label: 'Approved', variant: 'success' },
  { value: 'REVIEW_CORRECTED', label: 'Corrected', variant: 'neutral' },
  { value: 'REVIEW_REJECTED', label: 'Rejected', variant: 'danger' },
];

export const DOCUMENT_STATUSES = [
  { value: 'UPLOADED', label: 'Uploaded', variant: 'success' },
  { value: 'PENDING', label: 'Pending', variant: 'info' },
  { value: 'PROCESSING', label: 'Processing', variant: 'info' },
  { value: 'COMPLETED', label: 'Completed', variant: 'success' },
  { value: 'FAILED', label: 'Failed', variant: 'danger' },
  { value: 'MISSING', label: 'Missing', variant: 'neutral' },
  { value: 'UPLOADING', label: 'Uploading', variant: 'info' },
];

/**
 * Rule-result outcomes shown in the validation report.
 *
 * Raw rule-engine validation statuses (PASS, FAIL, WARNING,
 * PENDING_MANUAL_REVIEW) are mapped to the report vocabulary
 * Passed / Failed / Warning / Pending.
 *
 * No REJECTED entry: the backend ValidationStatus enum
 * (database/models/enums.py) has never had one, and every evaluate()
 * method across all 8 rule categories only ever sets one of the 4 values
 * above (confirmed by grep, not assumed) -- there is no code path that
 * could produce it. ApplicationStatus.REJECTED and the REVIEW_REJECTED
 * history event are real, separate, application-level concepts; this
 * table is per-rule-result only. See docs/TEAMMATE_BUG_TRIAGE.md #23.
 */
export const RULE_RESULT_STATUSES = [
  { value: 'PASS', label: 'Passed', variant: 'success' },
  { value: 'FAIL', label: 'Failed', variant: 'danger' },
  { value: 'WARNING', label: 'Warning', variant: 'warning' },
  { value: 'PENDING_MANUAL_REVIEW', label: 'Pending', variant: 'neutral' },
];

/**
 * Semantic statuses for the redesigned validation report.
 *
 * These are derived by the view model from raw backend statuses plus context
 * (completeness data, related_document_ids). Components render these rather
 * than understanding backend business logic.
 *
 * The key distinction: NOT_VERIFIABLE means a check could not be performed
 * because a prerequisite document is missing. It is NOT a failure.
 */
export const REPORT_STATUSES = [
  { value: 'PASSED', label: 'Passed', variant: 'success', icon: '\u2713' },
  { value: 'FAILED', label: 'Failed', variant: 'danger', icon: '\u2715' },
  { value: 'NOT_VERIFIABLE', label: 'Not Verifiable', variant: 'neutral', icon: '\u2014' },
  { value: 'PENDING', label: 'Pending', variant: 'info', icon: '\u23F3' },
  { value: 'WARNING', label: 'Warning', variant: 'warning', icon: '\u26A0' },
  { value: 'NOT_APPLICABLE', label: 'Not applicable', variant: 'neutral', icon: '\u2014' },
];

/**
 * Icons for the "What Requires Attention" section groups.
 */
export const ATTENTION_ICONS = {
  failure: { icon: '\uD83D\uDD34', label: 'Actual Failure' },
  missingDoc: { icon: '\uD83D\uDCC4', label: 'Required Document Missing' },
  duplicate: { icon: '\uD83D\uDCCE', label: 'Duplicate' },
  pending: { icon: '\u23F3', label: 'Pending' },
};

/**
 * Humanize a raw enum value (e.g. "NOT_PROCESSED" -> "Not Processed").
 *
 * @param {string|null|undefined} value The raw value.
 * @returns {string} A readable label.
 */
function readableLabel(value) {
  if (!value) {
    return 'Unknown';
  }
  return value
    .toLowerCase()
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

/**
 * Look up a status entry by its value.
 *
 * @param {Array} statuses A status catalogue.
 * @param {string} value The raw status value.
 * @returns {object} The matching entry, or a neutral fallback.
 */
function findStatus(statuses, value) {
  return statuses.find((status) => status.value === value) ?? {
    label: value ?? 'Unknown',
    variant: 'neutral',
    color: 'gray',
  };
}

/**
 * Map a raw rule-engine validation status to the report vocabulary.
 *
 * @param {string} value A backend `ValidationStatus` value.
 * @returns {object} The corresponding report status entry.
 */
export function getRuleResultStatus(value) {
  return (
    RULE_RESULT_STATUSES.find((status) => status.value === value) ?? {
      label: readableLabel(value),
      variant: 'neutral',
    }
  );
}

export function getApplicationStatus(value) {
  return findStatus(APPLICATION_STATUSES, value);
}

export function getDocumentStatus(value) {
  return findStatus(DOCUMENT_STATUSES, value);
}

/**
 * Map a raw validation-history event type to an operator-friendly entry.
 *
 * @param {string} value A backend `ValidationEventType` value.
 * @returns {object} The corresponding history event entry.
 */
export function getValidationHistoryEvent(value) {
  return (
    VALIDATION_HISTORY_EVENTS.find((event) => event.value === value) ?? {
      label: readableLabel(value),
      variant: 'neutral',
    }
  );
}

/**
 * Map a raw rule-engine validation status to an employee-facing status entry.
 *
 * @param {string} value A backend `ValidationStatus` value.
 * @returns {object} The corresponding verification status entry.
 */
export function getVerificationStatus(value) {
  switch (value) {
    case 'PASS':
      return findStatus(VERIFICATION_STATUSES, 'VERIFIED');
    case 'FAIL':
      return findStatus(VERIFICATION_STATUSES, 'FAILED');
    case 'REJECTED':
      return findStatus(VERIFICATION_STATUSES, 'REJECTED');
    case 'WARNING':
    case 'PENDING_MANUAL_REVIEW':
    default:
      return findStatus(VERIFICATION_STATUSES, 'REVIEW_REQUIRED');
  }
}

/**
 * Map a stored rule severity to an employee-facing severity entry.
 *
 * @param {string} value A backend `Severity` value.
 * @returns {object} The corresponding verification severity entry.
 */
export function getVerificationSeverity(value) {
  switch (value) {
    case 'ERROR':
      return findStatus(VERIFICATION_SEVERITIES, 'CRITICAL');
    case 'WARNING':
      return findStatus(VERIFICATION_SEVERITIES, 'WARNING');
    case 'INFO':
    default:
      return findStatus(VERIFICATION_SEVERITIES, 'REVIEW_REQUIRED');
  }
}

/**
 * Map a semantic report status value to its display entry.
 *
 * @param {string} value One of the REPORT_STATUSES values.
 * @returns {object} The corresponding status entry with label, variant and icon.
 */
export function getReportStatus(value) {
  return (
    REPORT_STATUSES.find((status) => status.value === value) ?? {
      label: readableLabel(value),
      variant: 'neutral',
      icon: '',
    }
  );
}

/**
 * Status vocabulary for the batch PDF upload queue.
 *
 * Deliberately separate from `data/statuses.js` / `ApplicationStatusBadge`:
 * this feature needs a simpler, closed 4-state vocabulary (Pending /
 * Processing / Completed / Failed) for a queue of files being submitted one
 * at a time, not the richer 8-state `ApplicationStatus` vocabulary used by
 * the Applications list and Validation Report. Keeping this file separate
 * means the existing single-file upload UI stays completely untouched.
 */

export const BATCH_ITEM_STATUSES = {
  PENDING: { value: 'pending', label: 'Pending', variant: 'neutral' },
  PROCESSING: { value: 'processing', label: 'Processing', variant: 'info' },
  COMPLETED: { value: 'completed', label: 'Completed', variant: 'success' },
  FAILED: { value: 'failed', label: 'Failed', variant: 'danger' },
};

//: Sub-phase text shown under the Processing chip while a file is in flight,
//: keyed by the phase set in BatchUploadContext's run loop.
export const BATCH_PHASE_LABELS = {
  creating: 'Creating application…',
  uploading: 'Uploading…',
  starting: 'Starting processing…',
  polling: 'Processing…',
};

/**
 * `ApplicationStatus` values that mean the automated pipeline is still
 * running -- the batch item stays "Processing".
 */
const IN_PROGRESS_APPLICATION_STATUSES = new Set(['SUBMITTED', 'PROCESSING']);

/**
 * `ApplicationStatus` values that mean the automated pipeline is done, with
 * no technical failure -- the batch item is "Completed". Includes
 * NEEDS_DOCUMENTS: the split/completeness check finished, the single PDF
 * just didn't cover every required checklist document type. That's not a
 * technical error, and the application never transitions further on its
 * own, so it must be treated as terminal here or the queue would wait on it
 * forever.
 */
const COMPLETED_APPLICATION_STATUSES = new Set([
  'PENDING_REVIEW',
  'NEEDS_DOCUMENTS',
  'APPROVED',
  'REJECTED',
  'CORRECTED',
]);

/**
 * Map a raw backend `ApplicationStatus` value to a batch item status.
 *
 * @param {string|null|undefined} applicationStatus Raw `Application.status`.
 * @returns {'processing'|'completed'|'failed'} One of the terminal/
 *   non-terminal batch states (never 'pending' -- that only applies before
 *   an application exists at all, which this function has no way to know).
 */
export function mapApplicationStatusToBatchStatus(applicationStatus) {
  if (COMPLETED_APPLICATION_STATUSES.has(applicationStatus)) {
    return BATCH_ITEM_STATUSES.COMPLETED.value;
  }
  if (IN_PROGRESS_APPLICATION_STATUSES.has(applicationStatus)) {
    return BATCH_ITEM_STATUSES.PROCESSING.value;
  }
  // PROCESSING_FAILED, or any unrecognized future status: fail closed rather
  // than silently spin forever on a status this mapping doesn't know about.
  return BATCH_ITEM_STATUSES.FAILED.value;
}

/**
 * Look up display info (label, StatusChip variant) for a batch item status.
 *
 * @param {string} status One of BATCH_ITEM_STATUSES' `value`s.
 * @returns {{label: string, variant: string}}
 */
export function getBatchItemStatusDisplay(status) {
  const entry = Object.values(BATCH_ITEM_STATUSES).find((item) => item.value === status);
  return entry ?? { label: status ?? 'Unknown', variant: 'neutral' };
}

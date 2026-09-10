import api from './api';

/**
 * Fetch the operator validation queue.
 *
 * Every application is returned with business-level completeness details
 * (status, required/received/missing document counts, completion percentage,
 * needs-attention flag and the last workflow event). The backend deliberately
 * excludes OCR, confidence and processing internals from this payload.
 *
 * @param {object} [options]
 * @param {number} [options.offset] Number of applications to skip.
 * @param {number} [options.limit] Maximum number of applications to return.
 * @returns {Promise<{items: object[], total: number, offset: number, limit: number}>}
 */
export function listValidationQueue({ offset = 0, limit = 50 } = {}) {
  return api
    .get('/validation/applications', { params: { offset, limit } })
    .then((response) => response.data);
}

/**
 * Fetch an application's immutable validation history, newest first.
 *
 * @param {number|string} applicationId Application id.
 * @param {object} [options]
 * @param {number} [options.offset] Number of entries to skip.
 * @param {number} [options.limit] Maximum number of entries to return.
 * @returns {Promise<{application_id: number, entries: object[], total: number}>}
 */
export function getValidationHistory(applicationId, { offset = 0, limit = 50 } = {}) {
  return api
    .get(`/applications/${applicationId}/validation-history`, { params: { offset, limit } })
    .then((response) => response.data);
}

/**
 * Request missing documents from the applicant.
 *
 * @param {number|string} applicationId Application id.
 * @param {object} payload
 * @param {string[]} payload.missingDocumentTypes Document types being requested.
 * @param {string} [payload.reason] Optional free-form note for the applicant.
 * @returns {Promise<{application_id: number, status: string, message: string}>}
 */
export function requestDocuments(applicationId, { missingDocumentTypes, reason }) {
  return api
    .post(`/applications/${applicationId}/request-documents`, {
      missing_document_types: missingDocumentTypes,
      reason: reason || null,
    })
    .then((response) => response.data);
}

/**
 * Reject an application at the operator stage.
 *
 * @param {number|string} applicationId Application id.
 * @param {object} payload
 * @param {string} payload.reason Mandatory rejection reason.
 * @returns {Promise<{application_id: number, status: string, message: string}>}
 */
export function rejectApplication(applicationId, { reason }) {
  return api
    .post(`/applications/${applicationId}/operator-reject`, { reason })
    .then((response) => response.data);
}

/**
 * Submit a complete application for processing.
 *
 * The backend verifies document completeness first (422 if anything is
 * missing) and enqueues the application for processing.
 *
 * @param {number|string} applicationId Application id.
 * @returns {Promise<{application_id: number, status: string, message: string}>}
 */
export function submitApplication(applicationId) {
  return api.post(`/applications/${applicationId}/operator-submit`).then((response) => response.data);
}
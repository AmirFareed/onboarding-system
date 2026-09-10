import api from './api';

/**
 * List applications for the IT history view, newest submissions first.
 *
 * Business-facing only: application metadata plus the most recent workflow
 * event. Never raw document contents or extracted PII.
 *
 * @param {object} [filters]
 * @param {string} [filters.query] Free-text search on id/name/submitter.
 * @param {string} [filters.status] Backend application status to filter by.
 * @param {object} [options]
 * @param {number} [options.offset] Number of applications to skip.
 * @param {number} [options.limit] Maximum number of applications to return.
 * @returns {Promise<{items: object[], total: number, offset: number, limit: number}>}
 */
export function listApplicationHistory(
  { query, status } = {},
  { offset = 0, limit = 50 } = {}
) {
  return api
    .get('/applications/history', {
      params: {
        offset,
        limit,
        ...(query ? { query } : {}),
        ...(status ? { status } : {}),
      },
    })
    .then((response) => response.data);
}

/**
 * Fetch one application's full lifecycle timeline.
 *
 * @param {number|string} applicationId Application id.
 * @returns {Promise<object>} Timeline with a chronological event list.
 */
export function getApplicationTimeline(applicationId) {
  return api
    .get(`/applications/${applicationId}/timeline`)
    .then((response) => response.data);
}

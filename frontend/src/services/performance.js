import api from './api';

/**
 * Aggregate performance figures across all applications (IT view).
 *
 * Averages are computed only over applications that actually have the metric,
 * so an all-in-flight set reports no misleading "0 days" turnaround.
 *
 * @returns {Promise<object>} Aggregate performance with status counts.
 */
export function getPerformanceOverview() {
  return api.get('/performance/overview').then((response) => response.data);
}

/**
 * List per-application performance with supporting evidence (IT view).
 *
 * Every row carries the individual time spans behind its headline numbers
 * (document request/receipt pairs, queue-job runs, review windows) so the UI
 * can drill from a figure to the exact events that produced it.
 *
 * @param {object} [filters]
 * @param {string} [filters.query] Free-text search on id/name/submitter.
 * @param {string} [filters.status] Backend application status to filter by.
 * @param {object} [options]
 * @param {number} [options.offset] Number of applications to skip.
 * @param {number} [options.limit] Maximum number of applications to return.
 * @returns {Promise<{items: object[], total: number, offset: number, limit: number}>}
 */
export function listPerformanceApplications(
  { query, status } = {},
  { offset = 0, limit = 50 } = {}
) {
  return api
    .get('/performance/applications', {
      params: {
        offset,
        limit,
        ...(query ? { query } : {}),
        ...(status ? { status } : {}),
      },
    })
    .then((response) => response.data);
}

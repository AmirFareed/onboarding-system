import api from './api';

/**
 * Fetch the stored rule-engine validation results for an application.
 *
 * These are the business-level rule outcomes (rule name, category, status,
 * severity, message, related documents). The endpoint returns 200 with an
 * empty `results` list when no pipeline has run, so the workspace always has a
 * usable response.
 *
 * @param {number|string} applicationId Application id.
 * @returns {Promise<{application_id: number, total: number, results: object[]}>}
 */
export function getValidationResults(applicationId) {
  return api
    .get(`/applications/${applicationId}/validation-results`)
    .then((response) => response.data);
}

/**
 * Fetch the document completeness report for an application.
 *
 * @param {number|string} applicationId Application id.
 * @returns {Promise<object>} The completeness report.
 */
export function getCompleteness(applicationId) {
  return api
    .get(`/applications/${applicationId}/completeness`)
    .then((response) => response.data);
}

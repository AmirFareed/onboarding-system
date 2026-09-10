import api from './api';

/**
 * Fetch every stored document-analysis result for an application.
 *
 * Each item carries the detected document category, verification status,
 * confidence score, extracted fields, per-field validations, consistency
 * checks and issues. Returns 200 with an empty `items` list when no analysis
 * has run.
 *
 * @param {number|string} applicationId Application id.
 * @returns {Promise<{application_id: number, items: object[], total: number}>}
 */
export function getAnalysisResults(applicationId) {
  return api
    .get(`/applications/${applicationId}/analysis-results`)
    .then((response) => response.data);
}

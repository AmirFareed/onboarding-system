import api from './api';

/**
 * Fetch every stored extracted field with its persisted normalized value.
 *
 * @param {number|string} applicationId Application id.
 * @returns {Promise<object[]>} Per-field records with extracted and normalized
 *   values plus the verification status.
 */
export function getNormalizedFields(applicationId) {
  return api
    .get(`/applications/${applicationId}/normalized-fields`)
    .then((response) => response.data);
}

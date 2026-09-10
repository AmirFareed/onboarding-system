import api from './api';

/**
 * Fetch the stored technical validation reports for an application's documents.
 *
 * Returns 200 with an empty `items` list when no document has been technically
 * validated yet.
 *
 * @param {number|string} applicationId Application id.
 * @returns {Promise<{application_id: number, items: object[], total: number}>}
 */
export function getTechnicalValidation(applicationId) {
  return api
    .get(`/applications/${applicationId}/technical-validation`)
    .then((response) => response.data);
}

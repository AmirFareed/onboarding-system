import api from './api';

/**
 * List the documents belonging to an application.
 *
 * @param {number|string} applicationId Application id.
 * @returns {Promise<{items: object[], total: number}>}
 */
export function listDocuments(applicationId) {
  return api.get(`/applications/${applicationId}/documents`).then((response) => response.data);
}

/**
 * Upload a bulk PDF to be split into individual documents.
 *
 * @param {object} params
 * @param {number|string} params.applicationId Application id.
 * @param {File} params.file The selected bulk PDF file.
 * @param {Function} [params.onUploadProgress] Axios upload progress callback.
 * @returns {Promise<object>} The bulk upload response (including extracted documents).
 */
export function uploadBulkDocument({ applicationId, file, onUploadProgress }) {
  const formData = new FormData();
  formData.append('file', file);
  return api
    .post(
      `/applications/${applicationId}/bulk-upload`,
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress,
      }
    )
    .then((response) => response.data);
}

/**
 * Build the download URL for a document.
 *
 * The endpoint streams the original file with an attachment filename, so the
 * download works from a plain anchor (cookie auth, same origin). The internal
 * storage path stays on the server; only the public endpoint is exposed here.
 *
 * @param {number|string} applicationId Id of the owning application.
 * @param {number|string} documentId Document id.
 * @returns {string} Absolute download URL.
 */
export function getDocumentDownloadUrl(applicationId, documentId) {
  const baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1';
  return `${baseURL}/applications/${applicationId}/documents/${documentId}/download`;
}

/**
 * Build the inline view URL for a document.
 *
 * The endpoint streams the file with Content-Disposition: inline so the
 * browser renders it (e.g. built-in PDF viewer) instead of downloading.
 *
 * @param {number|string} applicationId Id of the owning application.
 * @param {number|string} documentId Document id.
 * @returns {string} Absolute view URL.
 */
export function getDocumentViewUrl(applicationId, documentId) {
  const baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1';
  return `${baseURL}/applications/${applicationId}/documents/${documentId}/view`;
}

import api from './api';

/**
 * Fetch the aggregated validation report for an application.
 *
 * The report is a read-only aggregation of stored pipeline results (documents,
 * OCR, extracted fields, business/technical validation and visual detections).
 * It returns 422 when the application has no validation results yet, which the
 * Validation Report page treats as an empty state.
 *
 * @param {number|string} applicationId Application id.
 * @returns {Promise<object>} The structured validation report.
 */
export function getValidationReport(applicationId) {
  return api
    .get(`/applications/${applicationId}/validation-report`)
    .then((response) => response.data);
}

/**
 * Build the download URL for the printable HTML validation report.
 *
 * The endpoint streams the same report rendered from a Jinja2 template; the
 * link is opened in a new tab (cookie auth, same origin).
 *
 * @param {number|string} applicationId Application id.
 * @returns {string} Absolute URL to the printable report.
 */
export function getValidationReportHtmlUrl(applicationId) {
  const baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1';
  return `${baseURL}/applications/${applicationId}/validation-report/html`;
}

/**
 * Build the download URL for the printable PDF validation report.
 *
 * The endpoint renders the same Jinja2 template as the HTML version and
 * converts it to PDF via WeasyPrint, so both formats are always consistent.
 *
 * @param {number|string} applicationId Application id.
 * @returns {string} Absolute URL to the PDF report.
 */
export function getValidationReportPdfUrl(applicationId) {
  const baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1';
  return `${baseURL}/applications/${applicationId}/validation-report/pdf`;
}

/**
 * Download the PDF validation report for an application.
 *
 * Fetches the PDF with cookie auth, creates a blob, and triggers a
 * browser download with a human-readable filename derived from the
 * Content-Disposition header.
 *
 * @param {number|string} applicationId Application id.
 * @returns {Promise<void>}
 */
/**
 * Save a reviewer-edited copy of the printable validation report.
 *
 * Once saved, this exact HTML is what both the report view (the HTML
 * endpoint the edit page's own iframe loads from) and the PDF download
 * serve, instead of the report regenerating fresh from live pipeline
 * data -- see backend/app/reports/services.py's render_html().
 *
 * @param {number|string} applicationId Application id.
 * @param {string|null} html The edited report HTML, or null to clear the
 *   saved edit and revert to always regenerating fresh.
 * @returns {Promise<{application_id: number, html: string|null}>}
 */
export function saveEditedReportHtml(applicationId, html) {
  return api
    .put(`/applications/${applicationId}/edited-report`, { html })
    .then((response) => response.data);
}

export async function downloadValidationReportPdf(applicationId) {
  const response = await api.get(
    `/applications/${applicationId}/validation-report/pdf`,
    { responseType: 'blob' },
  );

  const contentDisposition = response.headers?.['content-disposition'] || '';
  const filenameMatch = contentDisposition.match(/filename="?([^";\n]+)"?/);
  const filename = filenameMatch
    ? filenameMatch[1]
    : `Validation-Report-${applicationId}.pdf`;

  const blob = new Blob([response.data], { type: 'application/pdf' });
  const blobUrl = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = blobUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(blobUrl);
}

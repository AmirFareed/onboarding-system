import api from './api';

/**
 * Fetch the final review screen for an application.
 *
 * Assembles everything the reviewer needs for the decision: the validation
 * report, the uploaded documents with their OCR state, the normalized and
 * confidence-scored fields, the visual detection outcomes, the current
 * checklist state and any previous review.
 *
 * @param {number|string} applicationId Application id.
 * @returns {Promise<object>} The review screen payload.
 */
export function getReviewScreen(applicationId) {
  return api
    .get(`/applications/${applicationId}/human-review`)
    .then((response) => response.data);
}

/**
 * Submit the final review decision for an application.
 *
 * @param {number|string} applicationId Application id.
 * @param {object} payload
 * @param {string} payload.reviewer_name Reviewer name.
 * @param {string} payload.decision One of "APPROVE", "CORRECT" or "REJECT".
 * @param {string} [payload.comments] Optional free-form notes.
 * @param {string} [payload.rejection_reason] Mandatory reason when rejecting.
 * @param {object[]} [payload.checklist] Checklist state (item_name + is_checked).
 * @param {object[]} [payload.corrections] Field corrections (field_name +
 *   corrected_value + optional reason).
 * @returns {Promise<object>} The stored review summary.
 */
export function submitHumanReview(applicationId, payload) {
  return api
    .post(`/applications/${applicationId}/human-review`, payload)
    .then((response) => response.data);
}

/**
 * Fetch the final reviews recorded for an application, most recent first.
 *
 * @param {number|string} applicationId Application id.
 * @returns {Promise<{application_id: number, reviews: object[]}>}
 */
export function getReviewHistory(applicationId) {
  return api
    .get(`/applications/${applicationId}/human-review/history`)
    .then((response) => response.data);
}

/**
 * Fetch the saved reviewer comment for an application.
 *
 * @param {number|string} applicationId Application id.
 * @returns {Promise<{application_id: number, reviewer_comments: string|null}>}
 */
export function getReviewerComments(applicationId) {
  return api
    .get(`/applications/${applicationId}/reviewer-comments`)
    .then((response) => response.data);
}

/**
 * Save (or clear) the reviewer comment for an application.
 *
 * Empty or whitespace-only values are stored as null. Maximum length is
 * 5,000 characters.
 *
 * @param {number|string} applicationId Application id.
 * @param {string|null} comments The reviewer comment text, or null to clear.
 * @returns {Promise<{application_id: number, reviewer_comments: string|null}>}
 */
export function saveReviewerComments(applicationId, comments) {
  return api
    .put(`/applications/${applicationId}/reviewer-comments`, {
      reviewer_comments: comments,
    })
    .then((response) => response.data);
}

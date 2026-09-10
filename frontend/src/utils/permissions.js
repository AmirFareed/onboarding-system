/**
 * Centralized permission helpers for role-based access control.
 *
 * Every permission predicate mirrors the backend's authorization model:
 * - EMPLOYEE satisfies every role guard (all-access by design).
 * - OPERATOR can upload and manage documents.
 * - REVIEWER can access validation reports, human review, and reviewer comments.
 *
 * The backend 403 remains the authoritative security boundary.  These
 * predicates control UI visibility and frontend routing only.
 */
import { effectiveRole, isEmployee, isOperator, isReviewer } from './roles';

/**
 * Whether the user may open the Validation Report page and its APIs.
 *
 * REVIEWER and EMPLOYEE are allowed; OPERATOR and IT are not.
 *
 * @param {object|null|undefined} user
 * @returns {boolean}
 */
export function canAccessValidationReport(user) {
  return isReviewer(user) || isEmployee(user);
}

/**
 * Whether the user may open the Human Review page and its APIs.
 *
 * REVIEWER and EMPLOYEE are allowed; OPERATOR and IT are not.
 *
 * @param {object|null|undefined} user
 * @returns {boolean}
 */
export function canAccessHumanReview(user) {
  return isReviewer(user) || isEmployee(user);
}

/**
 * Whether the user may upload or replace documents.
 *
 * OPERATOR and EMPLOYEE are allowed; REVIEWER and IT are not.
 *
 * @param {object|null|undefined} user
 * @returns {boolean}
 */
export function canUploadDocuments(user) {
  return isOperator(user) || isEmployee(user);
}

/**
 * Whether the user may edit Reviewer Comments.
 *
 * REVIEWER and EMPLOYEE are allowed; OPERATOR and IT are not.
 *
 * @param {object|null|undefined} user
 * @returns {boolean}
 */
export function canEditReviewerComments(user) {
  return isReviewer(user) || isEmployee(user);
}

/**
 * Whether the user may submit a review decision (approve / correct / reject).
 *
 * REVIEWER and EMPLOYEE are allowed.
 *
 * @param {object|null|undefined} user
 * @returns {boolean}
 */
export function canSubmitReviewDecision(user) {
  return isReviewer(user) || isEmployee(user);
}

/**
 * Whether the user may permanently delete an application.
 *
 * EMPLOYEE-only: a destructive, irreversible action, not an everyday
 * operator/reviewer capability. Mirrors the backend's
 * `require_role(ROLE_EMPLOYEE)` guard on `DELETE /applications/{id}`
 * (backend/app/upload/routes.py). Also true under the local dev server
 * (`npm run dev`), matching the backend's own ENVIRONMENT=development
 * no-login bypass (backend/app/auth/dependencies.py) that lets every role
 * through in that mode -- never true in a production build.
 *
 * @param {object|null|undefined} user
 * @returns {boolean}
 */
export function canDeleteApplication(user) {
  return isEmployee(user) || import.meta.env.MODE === 'development';
}

/**
 * Return the path to redirect an unauthorized user to when they attempt
 * to access a page their role does not allow.
 *
 * REVIEWER-only pages → Operator Dashboard (or /applications).
 * OPERATOR-only pages → Reviewer Validation Report (or /reports).
 *
 * @param {object|null|undefined} user
 * @returns {string}
 */
export function unauthorizedRedirectPath(user) {
  const role = effectiveRole(user?.role);
  if (role === 'OPERATOR') return '/';
  if (role === 'REVIEWER') return '/reports';
  return '/';
}

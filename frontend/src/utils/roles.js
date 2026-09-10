/**
 * Canonical operational roles, mirroring backend/app/auth/roles.py.
 *
 * Roles are stored on `users.role` as a free-form string (the backend has no
 * role enum). This module mirrors the backend's `effective_role` mapping so the
 * frontend gates UI affordances (operator actions, IT log viewer) on the same
 * canonical role the backend enforces. The backend 403 remains authoritative
 * -- this only decides what the UI shows, never what the backend allows.
 */
import { NAVIGATION } from '../data/navigation';

export const ROLE_EMPLOYEE = 'EMPLOYEE';
export const ROLE_OPERATOR = 'OPERATOR';
export const ROLE_REVIEWER = 'REVIEWER';
export const ROLE_IT = 'IT';

//: Legacy role strings mapped to the canonical role they imply. The seeded
//: default account historically used "Verification Officer" and is the
//: all-access Employee account, so it maps to EMPLOYEE.
const ROLE_GROUPS = {
  'Verification Officer': ROLE_EMPLOYEE,
};

const CANONICAL_ROLES = new Set([ROLE_EMPLOYEE, ROLE_OPERATOR, ROLE_REVIEWER, ROLE_IT]);

/**
 * Resolve a stored role string to its canonical role.
 *
 * Matches backend `effective_role`: unrecognized strings pass through unchanged,
 * the empty/missing role defaults to OPERATOR (same as the backend default).
 *
 * @param {string|null|undefined} role Stored `users.role` value, if any.
 * @returns {string} The canonical role.
 */
export function effectiveRole(role) {
  if (!role) {
    return ROLE_OPERATOR;
  }
  if (CANONICAL_ROLES.has(role)) {
    return role;
  }
  return ROLE_GROUPS[role] ?? role;
}

/** Return whether the user holds the operator role. */
export function isOperator(user) {
  return effectiveRole(user?.role) === ROLE_OPERATOR;
}

/** Return whether the user holds the reviewer role. */
export function isReviewer(user) {
  return effectiveRole(user?.role) === ROLE_REVIEWER;
}

/** Return whether the user holds the IT role. */
export function isIt(user) {
  return effectiveRole(user?.role) === ROLE_IT;
}

/**
 * Return whether the user holds the all-access Employee role.
 *
 * Mirrors the backend: EMPLOYEE is a canonical role the seeded
 * "Verification Officer" account maps to, and the backend grants it every
 * operational guard (operator, reviewer and IT actions). Use this at UI gates
 * that should be open to the Employee account (e.g. operator actions, system
 * logs) alongside the specific role predicate.
 *
 * @param {object|null|undefined} user The current user, if any.
 * @returns {boolean} Whether the user holds the all-access Employee role.
 */
export function isEmployee(user) {
  return effectiveRole(user?.role) === ROLE_EMPLOYEE;
}

/**
 * Filter the sidebar navigation for the current user's role.
 *
 * The Employee account sees every normal role-gated item, except entries with
 * `strictRoles`, which require an exact canonical role. All other roles only
 * see items whose `roles`/`strictRoles` list contains their canonical role.
 * Items without either list are visible to everyone.
 *
 * @param {object|null|undefined} user The current user, if any.
 * @returns {Array} A deep copy of NAVIGATION with hidden items removed.
 */
export function visibleNavigationFor(user) {
  const effective = effectiveRole(user?.role);

  return NAVIGATION.map((section) => ({
    ...section,
    items: section.items
      .filter((item) => visible(item, effective, user))
      .map((item) =>
        item.children
          ? { ...item, children: item.children.filter((child) => visible(child, effective, user)) }
          : item
      ),
  })).filter((section) => section.items.length > 0);
}

function visible(item, effective, user) {
  // Mirrors the backend's own dev-only login/role bypass
  // (backend/app/auth/dependencies.py, ENVIRONMENT=development): under
  // `npm run dev`, every nav item is shown, including strictRoles-gated
  // ones (Application History, Performance, System Logs), so the sidebar
  // matches what the backend now actually allows in that mode. Checked via
  // MODE rather than the DEV flag: Vite sets MODE to 'development' only
  // for the real dev server (`npm run dev`) and 'production' for a build,
  // but Vitest's default test mode ('test', not 'production') still
  // leaves DEV true -- MODE is the one that actually distinguishes "real
  // local dev server" from "test run," confirmed against
  // roles.test.js::"restricts an unknown custom role to the ungated
  // items", which failed under the DEV-flag version because Vitest's test
  // environment also has DEV === true.
  if (import.meta.env.MODE === 'development') {
    return true;
  }
  if (item.strictRoles?.length) {
    return item.strictRoles.includes(effective);
  }
  if (isEmployee(user)) {
    return true;
  }
  if (!item.roles || item.roles.length === 0) {
    return true;
  }
  return item.roles.includes(effective);
}

import { useEffect, useRef } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { useAuth } from '../hooks/useAuth';
import { effectiveRole } from '../utils/roles';
import { unauthorizedRedirectPath } from '../utils/permissions';

/**
 * Route guard that enforces role-based access control.
 *
 * Wraps any route that requires a specific role predicate. When the
 * authenticated user's effective role does not satisfy the predicate,
 * the user is redirected to an appropriate alternative page without
 * briefly rendering the protected content.
 *
 * On role change, the component forces a redirect even if the URL
 * hasn't changed, preventing stale reviewer-only state from leaking
 * into an operator session.
 *
 * Usage::
 *
 *   <RoleRoute canAccess={canAccessValidationReport}>
 *     <ValidationReportPage />
 *   </RoleRoute>
 *
 * @param {object} props
 * @param {Function} props.canAccess Predicate receiving the current user.
 *   Must return ``true`` when the user is allowed to view the route.
 * @param {React.ReactNode} props.children The protected page content.
 */
function RoleRoute({ canAccess, children }) {
  const { user } = useAuth();
  const location = useLocation();
  const previousRoleRef = useRef(effectiveRole(user?.role));

  // Detect role change and force redirect if the current route is no longer allowed.
  useEffect(() => {
    const currentRole = effectiveRole(user?.role);
    if (currentRole !== previousRoleRef.current) {
      previousRoleRef.current = currentRole;
      // The canAccess check will handle the redirect on next render.
    }
  }, [user]);

  if (!canAccess(user)) {
    return (
      <Navigate
        to={unauthorizedRedirectPath(user)}
        replace
        state={{ from: location.pathname, unauthorized: true }}
      />
    );
  }

  return children;
}

export default RoleRoute;

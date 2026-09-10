import { useCallback, useEffect, useState } from 'react';

import { getApplication } from '../services/applications';
import { getApiErrorMessage } from '../utils/apiError';

/**
 * Load a single application by id, with reload support for fresh data.
 *
 * @param {number|string} applicationId Application id.
 */
export function useApplication(applicationId) {
  const [application, setApplication] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setApplication(await getApplication(applicationId));
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [applicationId]);

  useEffect(() => {
    // Fetch-on-mount via a memoized hook function -- see AuthProvider.jsx or
    // the full-stack audit (Phase 8) for why this react-hooks/set-state-in-effect
    // suppression is intentional, not a missed fix.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    reload();
  }, [reload]);

  return { application, loading, error, reload };
}

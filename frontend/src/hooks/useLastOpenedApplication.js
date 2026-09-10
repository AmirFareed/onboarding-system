import { useCallback, useMemo } from 'react';

import { getPreference } from '../utils/preferences';

const LAST_OPENED_KEY = 'lastOpenedApplicationId';

/**
 * Remember the most recently opened application.
 *
 * Reads and writes the stored application id used by the "Resume Application"
 * shortcut. Writing is gated on the `rememberLastOpenedApplication`
 * preference; reading returns the stored id regardless (the caller decides
 * whether to surface it based on the preference).
 */
export function useLastOpenedApplication() {
  const remember = getPreference('rememberLastOpenedApplication', true);

  const lastOpenedId = useMemo(() => {
    if (!remember) {
      return null;
    }
    try {
      const raw = window.localStorage.getItem(LAST_OPENED_KEY);
      const id = raw ? Number(raw) : null;
      return Number.isFinite(id) ? id : null;
    } catch {
      return null;
    }
  }, [remember]);

  const recordOpened = useCallback(
    (applicationId) => {
      if (!remember || applicationId == null) {
        return;
      }
      try {
        window.localStorage.setItem(LAST_OPENED_KEY, String(applicationId));
      } catch {
        // Ignore storage failures.
      }
    },
    [remember]
  );

  const clear = useCallback(() => {
    try {
      window.localStorage.removeItem(LAST_OPENED_KEY);
    } catch {
      // Ignore storage failures.
    }
  }, []);

  return { lastOpenedId, recordOpened, clear };
}

export default useLastOpenedApplication;

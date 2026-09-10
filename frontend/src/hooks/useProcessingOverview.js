import { useCallback, useEffect, useState } from 'react';

import { listApplications } from '../services/applications';
import { getProcessingProgress, retryProcessing } from '../services/processing';
import { getApiErrorMessage } from '../utils/apiError';
import { getPreference } from '../utils/preferences';

/**
 * Aggregate processing status across every application.
 *
 * Merges the applications list with each application's processing progress so a
 * single view answers "what is being processed and how much is left". While any
 * application still has queued or in-flight documents the hook polls, gated by
 * the autoRefreshProcessingStatus workspace preference.
 *
 * @returns {{
 *   rows: Array<{application: object, progress: object|null}>,
 *   loading: boolean,
 *   refreshing: boolean,
 *   error: string|null,
 *   reload: () => Promise<void>,
 *   retry: (applicationId: number) => Promise<void>,
 *   retryingIds: Set<number>,
 * }}
 */
export function useProcessingOverview() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [retryingIds, setRetryingIds] = useState(() => new Set());

  const reload = useCallback(async () => {
    setRefreshing(true);
    try {
      const { items } = await listApplications({ limit: 100 });
      const progressList = await Promise.all(
        items.map((application) => getProcessingProgress(application.id).catch(() => null))
      );
      setRows(
        items.map((application, index) => ({
          application,
          progress: progressList[index],
        }))
      );
      setError(null);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const retry = useCallback(
    async (applicationId) => {
      setRetryingIds((prev) => new Set(prev).add(applicationId));
      try {
        await retryProcessing(applicationId);
        await reload();
      } catch (err) {
        setError(getApiErrorMessage(err));
      } finally {
        setRetryingIds((prev) => {
          const next = new Set(prev);
          next.delete(applicationId);
          return next;
        });
      }
    },
    [reload]
  );

  useEffect(() => {
    // Fetch-on-mount via a memoized hook function -- see AuthProvider.jsx or
    // the full-stack audit (Phase 8) for why this react-hooks/set-state-in-effect
    // suppression is intentional, not a missed fix.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    reload();
  }, [reload]);

  const hasWork = rows.some(
    ({ progress }) =>
      progress != null &&
      (Number(progress.queued) > 0 || Number(progress.processing) > 0)
  );

  useEffect(() => {
    if (!getPreference('autoRefreshProcessingStatus', true)) {
      return undefined;
    }
    if (!hasWork) {
      return undefined;
    }
    const interval = window.setInterval(reload, 2500);
    return () => window.clearInterval(interval);
  }, [hasWork, reload]);

  return { rows, loading, refreshing, error, reload, retry, retryingIds };
}

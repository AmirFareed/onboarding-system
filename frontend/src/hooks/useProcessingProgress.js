import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useAuth } from './useAuth';
import {
  getProcessingDocuments,
  getProcessingProgress,
  retryProcessing,
  startProcessing,
} from '../services/processing';
import { getApiErrorMessage } from '../utils/apiError';
import { getPreference } from '../utils/preferences';
import { canAccessValidationReport } from '../utils/permissions';

export function useProcessingProgress(applicationId) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [progress, setProgress] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState(null);

  const navigateReportFiredRef = useRef(false);

  const reload = useCallback(async () => {
    try {
      const [nextProgress, nextDocuments] = await Promise.all([
        getProcessingProgress(applicationId),
        getProcessingDocuments(applicationId),
      ]);
      setProgress(nextProgress);
      setDocuments(nextDocuments.documents ?? []);
      setError(null);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [applicationId]);

  const runAction = useCallback(async (action) => {
    setActionLoading(true);
    try {
      const result = await action(applicationId);
      await reload();
      return result;
    } finally {
      setActionLoading(false);
    }
  }, [applicationId, reload]);

  // One-shot navigation to the validation report when processing completes.
  // Only navigate if the user can access the validation report (REVIEWER/EMPLOYEE).
  // Operators stay on the processing view since they cannot access /reports.
  useEffect(() => {
    const autoOpen = getPreference('openReportOnProcessingComplete', false);
    const completed =
      progress != null &&
      Number(progress.total_documents) > 0 &&
      Number(progress.completed) >= Number(progress.total_documents);
    if (!autoOpen || !completed || !canAccessValidationReport(user)) {
      navigateReportFiredRef.current = false;
      return;
    }
    if (navigateReportFiredRef.current) {
      return;
    }
    navigateReportFiredRef.current = true;
    navigate(`/reports?application=${applicationId}`);
  }, [progress, applicationId, navigate, user]);

  useEffect(() => {
    // Fetch-on-mount via a memoized hook function -- see AuthProvider.jsx or
    // the full-stack audit (Phase 8) for why this react-hooks/set-state-in-effect
    // suppression is intentional, not a missed fix.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    reload();
  }, [reload]);

  // Same hasWork gate as useProcessingOverview.js: only poll while there is
  // actually queued or in-flight work, instead of unconditionally every
  // 2.5s for as long as the page/preference allows.
  const hasWork =
    progress != null && (Number(progress.queued) > 0 || Number(progress.processing) > 0);

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

  return {
    progress,
    documents,
    loading,
    actionLoading,
    error,
    reload,
    start: () => runAction(startProcessing),
    retry: () => runAction(retryProcessing),
  };
}

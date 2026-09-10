import { useCallback, useEffect, useRef, useState } from 'react';

import { getValidationHistory, listValidationQueue, rejectApplication, requestDocuments, submitApplication } from '../services/operatorWorkflow';
import { getApiErrorMessage } from '../utils/apiError';

/**
 * Load everything the operator Validation page needs.
 *
 * The queue lists every application with business-level completeness details
 * (never OCR/processing internals). Selecting an application opens its
 * immutable validation history. The three operator actions (request documents,
 * reject, submit for processing) always refetch the backend state afterward so
 * the UI reflects the stored result, not local state.
 *
 * @returns {object} Queue state, selection state, history and action callbacks.
 */
export function useValidationQueue() {
  const [applications, setApplications] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);

  // Guards against out-of-order responses: overlapping list fetches (StrictMode
  // double-effects, rapid refresh) must not let a stale response overwrite the
  // latest one, otherwise the queue could briefly (or permanently) empty.
  const queueRequestIdRef = useRef(0);

  // Same guard for the selected application's history: switching the selection
  // quickly enough (before an in-flight fetch for the previous one resolves)
  // must not let that stale response overwrite the newly-selected app's data.
  const historyRequestIdRef = useRef(0);

  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState(null);

  const loadQueue = useCallback(async () => {
    const requestId = ++queueRequestIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const data = await listValidationQueue({ limit: 100 });
      if (requestId === queueRequestIdRef.current) {
        setApplications(data?.items ?? []);
        setTotal(data?.total ?? 0);
      }
    } catch (err) {
      if (requestId === queueRequestIdRef.current) {
        setError(getApiErrorMessage(err));
        setApplications([]);
        setTotal(0);
      }
    } finally {
      if (requestId === queueRequestIdRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    // Fetch-on-mount via a memoized hook function -- see AuthProvider.jsx or
    // the full-stack audit (Phase 8) for why this react-hooks/set-state-in-effect
    // suppression is intentional, not a missed fix.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadQueue();
  }, [loadQueue]);

  const loadHistory = useCallback(async () => {
    const requestId = ++historyRequestIdRef.current;
    if (selectedId == null) {
      setHistory([]);
      setHistoryError(null);
      return;
    }
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const data = await getValidationHistory(selectedId, { limit: 100 });
      if (requestId === historyRequestIdRef.current) {
        setHistory(data?.entries ?? []);
      }
    } catch (err) {
      if (requestId === historyRequestIdRef.current) {
        setHistoryError(getApiErrorMessage(err));
        setHistory([]);
      }
    } finally {
      if (requestId === historyRequestIdRef.current) {
        setHistoryLoading(false);
      }
    }
  }, [selectedId]);

  useEffect(() => {
    // Fetch-on-mount/selection-change via a memoized hook function -- see
    // AuthProvider.jsx or the full-stack audit (Phase 8) for why this
    // react-hooks/set-state-in-effect suppression is intentional.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadHistory();
  }, [loadHistory]);

  const handleSelect = useCallback((value) => {
    setSelectedId(value === '' ? null : Number(value));
  }, []);

  const selectedApplication =
    applications.find((application) => application.application_id === selectedId) ?? null;

  /**
   * Run an operator action, then reload the queue + history so the UI reflects
   * the stored result.
   *
   * @param {Function} action An operatorWorkflow service call that takes the
   *   application id as its first argument.
   * @param {object} [payload] Extra arguments passed to the action.
   * @returns {Promise<object|null>} The action result, or null on failure.
   */
  const runAction = useCallback(
    async (action, payload) => {
      if (selectedId == null) {
        return null;
      }
      setActionLoading(true);
      setActionError(null);
      try {
        const result = await action(selectedId, payload);
        await Promise.all([loadQueue(), loadHistory()]);
        return result;
      } catch (err) {
        setActionError(getApiErrorMessage(err));
        return null;
      } finally {
        setActionLoading(false);
      }
    },
    [selectedId, loadQueue, loadHistory]
  );

  const handleRequestDocuments = useCallback(
    (payload) => runAction(requestDocuments, payload),
    [runAction]
  );
  const handleReject = useCallback((payload) => runAction(rejectApplication, payload), [runAction]);
  const handleSubmit = useCallback(() => runAction(submitApplication), [runAction]);

  const handleRefresh = useCallback(() => {
    loadQueue();
    loadHistory();
  }, [loadQueue, loadHistory]);

  return {
    applications,
    total,
    loading,
    error,
    selectedId,
    onSelect: handleSelect,
    selectedApplication,
    history,
    historyLoading,
    historyError,
    actionLoading,
    actionError,
    onRequestDocuments: handleRequestDocuments,
    onReject: handleReject,
    onSubmit: handleSubmit,
    onRefresh: handleRefresh,
  };
}
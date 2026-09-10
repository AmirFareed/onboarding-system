import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { getApplication, listApplications } from '../services/applications';
import { getReviewHistory, getReviewScreen, submitHumanReview } from '../services/humanReview';
import { getApiErrorMessage } from '../utils/apiError';

// Applications only reach PENDING_REVIEW once PipelineRunnerService.run()
// completes successfully (see bulk_queue/pipeline_runner.py). Before that
// backend transition existed, this default silently matched zero
// applications regardless of how many were actually awaiting review.
const DEFAULT_STATUS = 'PENDING_REVIEW';

const FINALIZED_STATUSES = ['APPROVED', 'REJECTED', 'CORRECTED'];

/**
 * Load everything the final Human Review page needs.
 *
 * Applications are listed through the shared list endpoint (optionally
 * filtered by status, defaulting to applications awaiting review). Selecting
 * an application opens its review screen, application record and review
 * history in parallel. Submitting a decision always refetches the backend
 * state so the UI reflects the stored result, not local state.
 *
 * When the page is opened with an `?application=<id>` search param (e.g. from
 * the Validation Report's "Open Human Review" link), that application is
 * pre-selected as soon as it appears in the loaded list.
 */
export function useHumanReview() {
  const [searchParams] = useSearchParams();
  const paramAppId = searchParams.get('application');
  const [applications, setApplications] = useState([]);
  const [appsLoading, setAppsLoading] = useState(true);
  const [appsError, setAppsError] = useState(null);
  const [statusFilter, setStatusFilter] = useState(DEFAULT_STATUS);
  const [selectedId, setSelectedId] = useState(null);

  // Guards against out-of-order responses: overlapping list fetches (StrictMode
  // double-effects, rapid filter changes) must not let a stale response overwrite
  // the latest one, otherwise the app dropdown briefly (or permanently) empties.
  const appsRequestIdRef = useRef(0);

  // Same guard for the selected application's review data: switching the
  // selection quickly enough (before an in-flight fetch for the previous one
  // resolves) must not let that stale response overwrite the newly-selected
  // application's data.
  const reviewRequestIdRef = useRef(0);

  const [reviewScreen, setReviewScreen] = useState(null);
  const [application, setApplication] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  const loadApplications = useCallback(async () => {
    const requestId = ++appsRequestIdRef.current;
    setAppsLoading(true);
    setAppsError(null);
    try {
      const { items } = await listApplications({
        status: statusFilter || undefined,
        limit: 100,
      });
      if (requestId === appsRequestIdRef.current) {
        setApplications(items ?? []);
      }
    } catch (err) {
      if (requestId === appsRequestIdRef.current) {
        setAppsError(getApiErrorMessage(err));
        setApplications([]);
      }
    } finally {
      if (requestId === appsRequestIdRef.current) {
        setAppsLoading(false);
      }
    }
  }, [statusFilter]);

  useEffect(() => {
    // Fetch-on-mount via a memoized hook function -- see AuthProvider.jsx or
    // the full-stack audit (Phase 8) for why this react-hooks/set-state-in-effect
    // suppression is intentional, not a missed fix.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadApplications();
  }, [loadApplications]);

  // Pre-select the application named by the `?application=` search param (e.g.
  // from the Validation Report's "Open Human Review" link) once it has loaded.
  // Only fires when the param is present and the id hasn't been chosen yet, so
  // a manual selection afterwards is never overridden.
  useEffect(() => {
    if (paramAppId == null) {
      return;
    }
    const requested = Number(paramAppId);
    if (Number.isNaN(requested) || selectedId === requested) {
      return;
    }
    if (appsLoading || appsError) {
      return;
    }
    if (applications.some((app) => app.id === requested)) {
      // Pre-selection only syncs state once the requested application has
      // loaded; see the fetch-on-mount note in useProcessingOverview.js for
      // the suppression rationale.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedId(requested);
    }
  }, [paramAppId, selectedId, applications, appsLoading, appsError]);

  const reload = useCallback(async () => {
    const requestId = ++reviewRequestIdRef.current;
    if (selectedId == null) {
      setReviewScreen(null);
      setApplication(null);
      setHistory([]);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [screen, app, reviews] = await Promise.all([
        getReviewScreen(selectedId),
        getApplication(selectedId),
        getReviewHistory(selectedId),
      ]);
      if (requestId === reviewRequestIdRef.current) {
        setReviewScreen(screen);
        setApplication(app);
        setHistory(reviews?.reviews ?? []);
      }
    } catch (err) {
      if (requestId === reviewRequestIdRef.current) {
        setError(getApiErrorMessage(err));
        setReviewScreen(null);
        setApplication(null);
        setHistory([]);
      }
    } finally {
      if (requestId === reviewRequestIdRef.current) {
        setLoading(false);
      }
    }
  }, [selectedId]);

  useEffect(() => {
    // Fetch-on-mount/selection-change via a memoized hook function -- see
    // AuthProvider.jsx or the full-stack audit (Phase 8) for why this
    // react-hooks/set-state-in-effect suppression is intentional.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    reload();
  }, [reload]);

  const handleStatusChange = useCallback((value) => {
    setStatusFilter(value);
    setSelectedId(null);
  }, []);

  const handleSelect = useCallback((value) => {
    setSelectedId(value === '' ? null : Number(value));
  }, []);

  const alreadyReviewed =
    reviewScreen?.previous_review != null ||
    (application != null && FINALIZED_STATUSES.includes(application.status));

  const submit = useCallback(
    async (payload) => {
      if (selectedId == null) {
        return null;
      }
      setSubmitting(true);
      setSubmitError(null);
      try {
        const result = await submitHumanReview(selectedId, payload);
        await reload();
        return result;
      } catch (err) {
        const message = getApiErrorMessage(err);
        setSubmitError(message);
        return null;
      } finally {
        setSubmitting(false);
      }
    },
    [selectedId, reload]
  );

  const handleRefresh = useCallback(() => {
    loadApplications();
    reload();
  }, [loadApplications, reload]);

  return {
    applications,
    appsLoading,
    appsError,
    statusFilter,
    onStatusChange: handleStatusChange,
    selectedId,
    onSelect: handleSelect,
    reviewScreen,
    application,
    history,
    loading,
    error,
    submitting,
    submitError,
    submit,
    alreadyReviewed,
    onRefresh: handleRefresh,
  };
}
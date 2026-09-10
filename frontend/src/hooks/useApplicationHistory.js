import { useCallback, useEffect, useRef, useState } from 'react';

import { getApplicationTimeline, listApplicationHistory } from '../services/applicationHistory';
import { getApiErrorMessage } from '../utils/apiError';

const PAGE_SIZE = 50;

/**
 * Load the IT application-history list and one application's timeline.
 *
 * List filters are applied server-side (newest submissions first); every
 * filter change triggers a fresh fetch. Selecting an application fetches its
 * full lifecycle timeline. A request-id guard discards out-of-order responses
 * so a stale fetch can never overwrite a newer one.
 *
 * @returns {object} List rows, pagination, filter state and timeline state.
 */
export function useApplicationHistory() {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const [offset, setOffset] = useState(0);

  const [selectedId, setSelectedId] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineError, setTimelineError] = useState(null);

  // Guards against out-of-order responses: overlapping fetches (StrictMode
  // double-effects, rapid filter changes) must not let a stale response
  // overwrite the latest one.
  const requestIdRef = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const data = await listApplicationHistory(
        { query: query || undefined, status: status || undefined },
        { offset, limit: PAGE_SIZE }
      );
      if (requestId === requestIdRef.current) {
        setRows(data?.items ?? []);
        setTotal(data?.total ?? 0);
      }
    } catch (err) {
      if (requestId === requestIdRef.current) {
        setError(getApiErrorMessage(err));
        setRows([]);
        setTotal(0);
      }
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [query, status, offset]);

  useEffect(() => {
    // Fetch-on-mount/filter-change via a memoized hook function -- see
    // AuthProvider.jsx or the full-stack audit (Phase 8) for why this
    // react-hooks/set-state-in-effect suppression is intentional.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  const loadTimeline = useCallback(async (applicationId) => {
    setSelectedId(applicationId);
    setTimeline(null);
    setTimelineError(null);
    setTimelineLoading(true);
    try {
      const data = await getApplicationTimeline(applicationId);
      setTimeline(data);
    } catch (err) {
      setTimelineError(getApiErrorMessage(err));
    } finally {
      setTimelineLoading(false);
    }
  }, []);

  const handleQueryChange = useCallback((value) => {
    setQuery(value);
    setOffset(0);
  }, []);

  const handleStatusChange = useCallback((value) => {
    setStatus(value);
    setOffset(0);
  }, []);

  const goToPage = useCallback((page) => {
    setOffset(page * PAGE_SIZE);
  }, []);

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = Math.floor(offset / PAGE_SIZE);

  return {
    rows,
    total,
    loading,
    error,
    query,
    status,
    pageCount,
    currentPage,
    selectedId,
    timeline,
    timelineLoading,
    timelineError,
    onQueryChange: handleQueryChange,
    onStatusChange: handleStatusChange,
    onGoToPage: goToPage,
    onSelect: loadTimeline,
    onCloseTimeline: () => setSelectedId(null),
    onRefresh: load,
  };
}
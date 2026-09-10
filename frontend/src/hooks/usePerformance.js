import { useCallback, useEffect, useRef, useState } from 'react';

import { getPerformanceOverview, listPerformanceApplications } from '../services/performance';
import { getApiErrorMessage } from '../utils/apiError';

const PAGE_SIZE = 50;

/**
 * Load the IT performance overview and per-application timing table.
 *
 * The overview is fetched once per load; the table is filterable (search,
 * status) and paginated server-side. A request-id guard discards out-of-order
 * responses so a stale fetch can never overwrite a newer one.
 *
 * @returns {object} Overview, table rows, pagination, filter state.
 */
export function usePerformance() {
  const [overview, setOverview] = useState(null);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [overviewError, setOverviewError] = useState(null);

  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const [offset, setOffset] = useState(0);

  // Guards against out-of-order responses: overlapping fetches (StrictMode
  // double-effects, rapid filter changes) must not let a stale response
  // overwrite the latest one.  Overview and rows use independent counters
  // so a simultaneous reload() of both never makes one counter stale.
  const overviewRequestIdRef = useRef(0);
  const rowsRequestIdRef = useRef(0);

  const loadOverview = useCallback(async () => {
    const requestId = ++overviewRequestIdRef.current;
    setOverviewLoading(true);
    setOverviewError(null);
    try {
      const data = await getPerformanceOverview();
      if (requestId === overviewRequestIdRef.current) {
        setOverview(data);
      }
    } catch (err) {
      if (requestId === overviewRequestIdRef.current) {
        setOverviewError(getApiErrorMessage(err));
      }
    } finally {
      if (requestId === overviewRequestIdRef.current) {
        setOverviewLoading(false);
      }
    }
  }, []);

  const loadRows = useCallback(async () => {
    const requestId = ++rowsRequestIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const data = await listPerformanceApplications(
        { query: query || undefined, status: status || undefined },
        { offset, limit: PAGE_SIZE }
      );
      if (requestId === rowsRequestIdRef.current) {
        setRows(data?.items ?? []);
        setTotal(data?.total ?? 0);
      }
    } catch (err) {
      if (requestId === rowsRequestIdRef.current) {
        setError(getApiErrorMessage(err));
        setRows([]);
        setTotal(0);
      }
    } finally {
      if (requestId === rowsRequestIdRef.current) {
        setLoading(false);
      }
    }
  }, [query, status, offset]);

  const reload = useCallback(() => {
    loadOverview();
    loadRows();
  }, [loadOverview, loadRows]);

  useEffect(() => {
    // Fetch-on-mount/filter-change via a memoized hook function -- see
    // AuthProvider.jsx or the full-stack audit (Phase 8) for why this
    // react-hooks/set-state-in-effect suppression is intentional.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    reload();
  }, [reload]);

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
    overview,
    overviewLoading,
    overviewError,
    rows,
    total,
    loading,
    error,
    query,
    status,
    pageCount,
    currentPage,
    onQueryChange: handleQueryChange,
    onStatusChange: handleStatusChange,
    onGoToPage: goToPage,
    onRefresh: reload,
  };
}
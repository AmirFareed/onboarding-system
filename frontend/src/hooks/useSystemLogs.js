import { useCallback, useEffect, useRef, useState } from 'react';

import { getSystemLog, listSystemLogs } from '../services/systemLogs';
import { getApiErrorMessage } from '../utils/apiError';

const PAGE_SIZE = 50;

/**
 * Load the IT system-log list and one entry's full detail.
 *
 * List filters are applied server-side (newest first); every filter change
 * resets to the first page and triggers a fresh fetch. Selecting a row fetches
 * its full stored record. A request-id guard discards out-of-order responses
 * so a stale fetch can never overwrite a newer one, mirroring
 * useApplicationHistory.js.
 *
 * @returns {object} List rows, pagination, filter state and detail state.
 */
export function useSystemLogs() {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [actor, setActor] = useState('');
  const [eventType, setEventType] = useState('');
  const [severity, setSeverity] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [query, setQuery] = useState('');
  const [includeOrphaned, setIncludeOrphaned] = useState(false);
  const [offset, setOffset] = useState(0);

  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);

  // Guards against out-of-order responses: overlapping fetches (StrictMode
  // double-effects, rapid filter changes) must not let a stale response
  // overwrite the latest one.
  const requestIdRef = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const data = await listSystemLogs(
        {
          actor: actor || undefined,
          eventType: eventType || undefined,
          severity: severity || undefined,
          dateFrom: dateFrom || undefined,
          dateTo: dateTo || undefined,
          query: query || undefined,
          includeOrphaned,
        },
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
  }, [actor, eventType, severity, dateFrom, dateTo, query, includeOrphaned, offset]);

  useEffect(() => {
    // Fetch-on-mount/filter-change via a memoized hook function -- see
    // useApplicationHistory.js for why this react-hooks/set-state-in-effect
    // suppression is intentional.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  const loadDetail = useCallback(async (logId) => {
    setSelectedId(logId);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    try {
      const data = await getSystemLog(logId);
      setDetail(data);
    } catch (err) {
      setDetailError(getApiErrorMessage(err));
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const handleActorChange = useCallback((value) => {
    setActor(value);
    setOffset(0);
  }, []);

  const handleEventTypeChange = useCallback((value) => {
    setEventType(value);
    setOffset(0);
  }, []);

  const handleSeverityChange = useCallback((value) => {
    setSeverity(value);
    setOffset(0);
  }, []);

  const handleDateFromChange = useCallback((value) => {
    setDateFrom(value);
    setOffset(0);
  }, []);

  const handleDateToChange = useCallback((value) => {
    setDateTo(value);
    setOffset(0);
  }, []);

  const handleQueryChange = useCallback((value) => {
    setQuery(value);
    setOffset(0);
  }, []);

  const handleIncludeOrphanedChange = useCallback((value) => {
    setIncludeOrphaned(value);
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
    actor,
    eventType,
    severity,
    dateFrom,
    dateTo,
    query,
    includeOrphaned,
    pageCount,
    currentPage,
    selectedId,
    detail,
    detailLoading,
    detailError,
    onActorChange: handleActorChange,
    onEventTypeChange: handleEventTypeChange,
    onSeverityChange: handleSeverityChange,
    onDateFromChange: handleDateFromChange,
    onDateToChange: handleDateToChange,
    onQueryChange: handleQueryChange,
    onIncludeOrphanedChange: handleIncludeOrphanedChange,
    onGoToPage: goToPage,
    onSelect: loadDetail,
    onCloseDetail: () => setSelectedId(null),
    onRefresh: load,
  };
}

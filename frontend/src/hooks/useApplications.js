import { useCallback, useEffect, useMemo, useState } from 'react';

import { useApplicationsStore } from '../store/ApplicationsContext';
import { getPreference, setPreference } from '../utils/preferences';
import { sortBy } from '../utils/sort';

/**
 * Applications page view over the shared application store.
 *
 * The canonical list lives in the ApplicationsProvider; this hook derives the
 * page-specific view (status filter, search and column sorting are applied
 * client-side over the fetched page). Creating an application goes through the
 * store, so the new record appears in both the Applications page and the
 * Dashboard "Recent Applications" section from the same update.
 */
export function useApplications() {
  const { applications, loading, error, reload, create } = useApplicationsStore();
  const [statusFilter, setStatusFilter] = useState(() =>
    getPreference('rememberApplicationFilter', true)
      ? (getPreference('applicationFilter', '') ?? '')
      : ''
  );
  const [searchTerm, setSearchTerm] = useState('');
  const [sortKey, setSortKey] = useState('submitted_at');
  const [sortDir, setSortDir] = useState('desc');

  useEffect(() => {
    if (getPreference('rememberApplicationFilter', true)) {
      setPreference('applicationFilter', statusFilter);
    }
  }, [statusFilter]);

  const filteredApplications = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    return applications.filter((application) => {
      if (statusFilter && application.status !== statusFilter) {
        return false;
      }
      if (!term) {
        return true;
      }
      return (
        String(application.id).includes(term) ||
        (application.name ?? '').toLowerCase().includes(term) ||
        application.created_by.toLowerCase().includes(term) ||
        (application.notes ?? '').toLowerCase().includes(term)
      );
    });
  }, [applications, statusFilter, searchTerm]);

  const visibleApplications = useMemo(
    () => sortBy(filteredApplications, sortKey, sortDir),
    [filteredApplications, sortKey, sortDir]
  );

  const handleStatusChange = useCallback((value) => {
    setStatusFilter(value);
  }, []);

  const handleSearchChange = useCallback((value) => {
    setSearchTerm(value);
  }, []);

  const handleSortChange = useCallback((key, direction) => {
    setSortKey(key);
    setSortDir(direction);
  }, []);

  return {
    applications: visibleApplications,
    total: filteredApplications.length,
    loading,
    error,
    reload,
    searchTerm,
    statusFilter,
    sortKey,
    sortDir,
    onSearchChange: handleSearchChange,
    onStatusChange: handleStatusChange,
    onSortChange: handleSortChange,
    create,
  };
}

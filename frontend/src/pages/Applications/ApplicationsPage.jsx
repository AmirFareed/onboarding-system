import { Link } from 'react-router-dom';

import { Files, History, Plus } from 'lucide-react';

import ApplicationEmptyState from '../../components/applications/ApplicationEmptyState/ApplicationEmptyState';
import ApplicationFilters from '../../components/applications/ApplicationFilters/ApplicationFilters';
import ApplicationSearch from '../../components/applications/ApplicationSearch/ApplicationSearch';
import { ApplicationTableSkeleton } from '../../components/applications/ApplicationSkeleton/ApplicationSkeleton';
import ApplicationTable from '../../components/applications/ApplicationTable/ApplicationTable';
import ErrorState from '../../components/common/ErrorState/ErrorState';
import { useApplications } from '../../hooks/useApplications';
import { useAuth } from '../../hooks/useAuth';
import { useLastOpenedApplication } from '../../hooks/useLastOpenedApplication';
import { useApplicationsStore } from '../../store/ApplicationsContext';
import { canUploadDocuments } from '../../utils/permissions';
import { getPreference } from '../../utils/preferences';
import styles from './ApplicationsPage.module.css';

/**
 * Applications landing page.
 *
 * Renders a toolbar (search + status filter) above the application table. The
 * status filter is applied server-side; search and column sorting run
 * client-side. Includes loading skeletons, a friendly error state, and two
 * flavours of empty state (no data yet vs. no matches).
 */
function ApplicationsPage() {
  const { user } = useAuth();
  const {
    applications,
    total,
    loading,
    error,
    reload,
    searchTerm,
    statusFilter,
    sortKey,
    sortDir,
    onSearchChange,
    onStatusChange,
    onSortChange,
  } = useApplications();

  const { applications: storeApplications } = useApplicationsStore();
  const { lastOpenedId, clear } = useLastOpenedApplication();
  const showResume = Boolean(
    getPreference('rememberLastOpenedApplication', true) &&
      lastOpenedId != null &&
      storeApplications.some((application) => application.id === lastOpenedId)
  );

  const handleResume = () => {
    clear();
  };

  const hasFilters = Boolean(searchTerm.trim() || statusFilter);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h2 className={styles.title}>Applications</h2>
          <p className={styles.subtitle}>
            Manage financial document verification applications.
          </p>
        </div>
        {canUploadDocuments(user) && (
          <div className={styles.headerActions}>
            <Link to="/applications/batch-upload" className={styles.batchBtn}>
              <Files aria-hidden="true" />
              Batch Upload PDFs
            </Link>
            <Link to="/applications/new" className={styles.createBtn}>
              <Plus aria-hidden="true" />
              Create New Application
            </Link>
          </div>
        )}
      </header>

      <div className={styles.toolbar}>
        <ApplicationSearch
          id="applications-search"
          value={searchTerm}
          onChange={onSearchChange}
        />
        <ApplicationFilters
          id="applications-status-filter"
          value={statusFilter}
          onChange={onStatusChange}
        />
        {showResume && (
          <Link
            to={`/applications/${lastOpenedId}`}
            state={{ fromResume: true }}
            className={styles.resumeChip}
            onClick={handleResume}
          >
            <History aria-hidden="true" />
            Resume Application #{lastOpenedId}
          </Link>
        )}
        <p className={styles.count} aria-live="polite">
          {total} {total === 1 ? 'application' : 'applications'}
        </p>
      </div>

      {loading ? (
        <ApplicationTableSkeleton />
      ) : error ? (
        <ErrorState message="Unable to load applications. Please try again." onRetry={reload} />
      ) : applications.length === 0 ? (
        <ApplicationEmptyState filtered={hasFilters} />
      ) : (
        <ApplicationTable
          applications={applications}
          sortKey={sortKey}
          sortDir={sortDir}
          onSortChange={onSortChange}
        />
      )}
    </div>
  );
}

export default ApplicationsPage;

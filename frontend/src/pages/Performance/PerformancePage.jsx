import { useState } from 'react';

import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Clock,
  RefreshCw,
  Search,
  ShieldAlert,
  Timer,
  UserCheck,
} from 'lucide-react';

import ApplicationStatusBadge from '../../components/applications/ApplicationStatusBadge/ApplicationStatusBadge';
import EmptyState from '../../components/common/EmptyState/EmptyState';
import ErrorState from '../../components/common/ErrorState/ErrorState';
import Spinner from '../../components/common/Spinner/Spinner';
import { APPLICATION_STATUSES } from '../../data/statuses';
import { useAuth } from '../../hooks/useAuth';
import { usePerformance } from '../../hooks/usePerformance';
import { formatDateTime, formatDuration } from '../../utils/format';
import { isIt, isEmployee } from '../../utils/roles';
import styles from './PerformancePage.module.css';

/**
 * IT performance view.
 *
 * Summarises aggregate turnaround, internal processing, waiting-for-documents
 * and review times (averaged only over applications that actually have the
 * metric) alongside status counts and resubmission totals. The table drills
 * into each application with its own timing breakdown; expanding a row shows
 * the individual time spans behind every number -- the exact document
 * request/receipt pairs, queue-job runs and review windows that produced it.
 * The page is reachable only by the IT role; the backend 403 remains the
 * authoritative gate.
 */
function PerformancePage() {
  const { user } = useAuth();
  const {
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
    onQueryChange,
    onStatusChange,
    onGoToPage,
    onRefresh,
  } = usePerformance();
  const [searchValue, setSearchValue] = useState('');
  const [expandedId, setExpandedId] = useState(null);

  const allowed = isIt(user) || isEmployee(user);

  if (!allowed) {
    return (
      <div className={styles.page}>
        <header className={styles.header}>
          <h2 className={styles.title}>Performance</h2>
          <p className={styles.subtitle}>Application turnaround and processing times.</p>
        </header>
        <div className={styles.accessDenied} role="alert">
          <div className={styles.accessDeniedIcon} aria-hidden="true">
            <ShieldAlert />
          </div>
          <h3 className={styles.accessDeniedTitle}>Access denied</h3>
          <p className={styles.accessDeniedText}>
            Performance figures are restricted to the IT role. Your account is not authorized to
            view them. Contact your administrator if you believe this is in error.
          </p>
        </div>
      </div>
    );
  }

  const submitSearch = () => {
    onQueryChange(searchValue.trim());
  };

  const toggleRow = (applicationId) => {
    setExpandedId((prev) => (prev === applicationId ? null : applicationId));
  };

  const averageCards = overview
    ? [
        {
          label: 'Avg waiting for documents',
          seconds: overview.avg_waiting_seconds,
          icon: Clock,
        },
        {
          label: 'Avg internal processing',
          seconds: overview.avg_processing_seconds,
          icon: Timer,
        },
        {
          label: 'Avg review time',
          seconds: overview.avg_review_seconds,
          icon: UserCheck,
        },
        {
          label: 'Avg total turnaround',
          seconds: overview.avg_turnaround_seconds,
          icon: Timer,
        },
      ]
    : [];

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h2 className={styles.title}>Performance</h2>
          <p className={styles.subtitle}>
            How long applications spend waiting, being processed and under review.
          </p>
        </div>
        <button
          className={styles.refreshBtn}
          type="button"
          onClick={onRefresh}
          disabled={loading || overviewLoading}
          aria-label="Refresh performance figures"
        >
          <RefreshCw aria-hidden="true" />
          Refresh
        </button>
      </header>

      {overviewLoading && !overview ? (
        <div className={styles.center} aria-busy="true">
          <Spinner size="medium" />
        </div>
      ) : overviewError && !overview ? (
        <ErrorState message={overviewError} onRetry={onRefresh} />
      ) : (
        <div className={styles.summary} aria-live="polite">
          <div className={`${styles.card} ${styles.cardHighlight}`}>
            <span className={styles.cardValue}>{overview?.total_applications ?? 0}</span>
            <span className={styles.cardLabel}>Applications</span>
            <span className={styles.cardHint}>
              {overview?.decided_applications ?? 0} decided
            </span>
          </div>
          {averageCards.map(({ label, seconds, icon: Icon }) => (
            <div key={label} className={styles.card}>
              <span className={styles.cardValue}>
                {seconds == null ? '\u2014' : formatDuration(seconds)}
              </span>
              <span className={styles.cardLabel}>
                <Icon className={styles.cardIcon} aria-hidden="true" />
                {label}
              </span>
              {seconds == null && (
                <span className={styles.cardHint}>No completed spans yet</span>
              )}
            </div>
          ))}
          <div className={styles.card}>
            <span className={styles.cardValue}>
              {(overview?.total_resubmissions ?? 0) + (overview?.total_missing_document_cycles ?? 0)}
            </span>
            <span className={styles.cardLabel}>Document follow-ups</span>
            <span className={styles.cardHint}>
              {overview?.total_resubmissions ?? 0} resubmissions ·{' '}
              {overview?.total_missing_document_cycles ?? 0} missing-document cycles
            </span>
          </div>
        </div>
      )}

      <div className={styles.toolbar}>
        <div className={styles.filters}>
          <div className={styles.searchWrap}>
            <Search className={styles.searchIcon} aria-hidden="true" />
            <input
              className={styles.searchInput}
              type="search"
              value={searchValue}
              onChange={(event) => setSearchValue(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  submitSearch();
                }
              }}
              placeholder="Search by id, name or submitter"
              aria-label="Search performance rows"
            />
          </div>
          <select
            className={styles.statusSelect}
            value={status}
            onChange={(event) => onStatusChange(event.target.value)}
            aria-label="Filter by application status"
          >
            <option value="">All statuses</option>
            {APPLICATION_STATUSES.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <button
            className={styles.secondaryBtn}
            type="button"
            onClick={submitSearch}
            disabled={loading}
          >
            Search
          </button>
        </div>
        <p className={styles.count} aria-live="polite">
          {total} {total === 1 ? 'application' : 'applications'}
        </p>
      </div>

      {loading && rows.length === 0 ? (
        <div className={styles.center} aria-busy="true">
          <Spinner size="medium" />
        </div>
      ) : error && rows.length === 0 ? (
        <ErrorState message={error} onRetry={onRefresh} />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No applications found"
          message={
            query || status
              ? 'No applications match the current search and filters.'
              : 'Create an application to see its performance breakdown here.'
          }
        />
      ) : (
        <>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Application</th>
                  <th scope="col">Status</th>
                  <th scope="col">Waiting</th>
                  <th scope="col">Processing</th>
                  <th scope="col">Review</th>
                  <th scope="col">Turnaround</th>
                  <th scope="col" className={styles.actionsHeader}>
                    Details
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const expanded = row.application_id === expandedId;
                  const followUps = (row.resubmissions ?? 0) + (row.missing_document_cycles ?? 0);
                  return (
                    <FragmentRow
                      key={row.application_id}
                      row={row}
                      expanded={expanded}
                      followUps={followUps}
                      onToggle={toggleRow}
                    />
                  );
                })}
              </tbody>
            </table>
          </div>

          {pageCount > 1 && (
            <nav className={styles.pagination} aria-label="Performance pages">
              <button
                type="button"
                className={styles.pageBtn}
                disabled={currentPage === 0}
                onClick={() => onGoToPage(currentPage - 1)}
                aria-label="Previous page"
              >
                <ChevronLeft aria-hidden="true" />
              </button>
              <span className={styles.pageInfo}>
                Page {currentPage + 1} of {pageCount}
              </span>
              <button
                type="button"
                className={styles.pageBtn}
                disabled={currentPage >= pageCount - 1}
                onClick={() => onGoToPage(currentPage + 1)}
                aria-label="Next page"
              >
                <ChevronRight aria-hidden="true" />
              </button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}

function FragmentRow({ row, expanded, followUps, onToggle }) {
  const metric = (seconds) => (seconds == null ? '\u2014' : formatDuration(seconds));

  // For in-flight applications, show turnaround-so-far instead of a blank dash.
  const turnaroundDisplay =
    row.total_turnaround_seconds != null
      ? formatDuration(row.total_turnaround_seconds)
      : row.turnaround_so_far_seconds != null
        ? `${formatDuration(row.turnaround_so_far_seconds)} so far`
        : '\u2014';

  return (
    <>
      <tr className={expanded ? styles.selectedRow : undefined}>
        <td data-label="Application">
          <div className={styles.appCell}>
            <span className={styles.appId}>#{row.application_id}</span>
            {row.application_name && <span className={styles.appName}>{row.application_name}</span>}
            <span className={styles.appCreator}>
              by {row.created_by} · submitted {formatDateTime(row.submitted_at)}
            </span>
            {followUps > 0 && (
              <span className={styles.followUp}>Document follow-ups: {followUps}</span>
            )}
            {row.current_evidence && (
              <span className={styles.currentEvidence}>{row.current_evidence}</span>
            )}
          </div>
        </td>
        <td data-label="Status">
          <ApplicationStatusBadge status={row.status} />
        </td>
        <td data-label="Waiting">{metric(row.waiting_seconds)}</td>
        <td data-label="Processing">{metric(row.processing_seconds)}</td>
        <td data-label="Review">{metric(row.review_seconds)}</td>
        <td data-label="Turnaround">{turnaroundDisplay}</td>
        <td data-label="Details" className={styles.actionsCell}>
          <button
            className={styles.detailBtn}
            type="button"
            onClick={() => onToggle(row.application_id)}
            aria-expanded={expanded}
          >
            {expanded ? <ChevronUp aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}
            {expanded ? 'Hide evidence' : 'Show evidence'}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className={styles.evidenceRow}>
          <td colSpan={7}>
            <SpansSection title="Waiting for documents" spans={row.waiting_spans ?? []} />
            <SpansSection title="Internal processing" spans={row.processing_spans ?? []} />
            <SpansSection title="Review" spans={row.review_spans ?? []} />
          </td>
        </tr>
      )}
    </>
  );
}

function SpansSection({ title, spans }) {
  return (
    <div className={styles.evidenceSection}>
      <h4 className={styles.evidenceTitle}>{title}</h4>
      {spans.length === 0 ? (
        <p className={styles.evidenceEmpty}>No recorded spans.</p>
      ) : (
        <ul className={styles.spanList}>
          {spans.map((span, index) => (
            <li key={`${span.label}-${index}`} className={styles.spanItem}>
              <div className={styles.spanHeader}>
                <span className={styles.spanLabel}>
                  {span.open && <span className={styles.openTag}>Open</span>}
                  {span.label}
                </span>
                <span className={styles.spanDuration}>
                  {span.duration_seconds == null ? '\u2014' : formatDuration(span.duration_seconds)}
                </span>
              </div>
              <p className={styles.spanRange}>
                {formatDateTime(span.start)} → {span.end ? formatDateTime(span.end) : 'now'}
              </p>
              {span.detail && <p className={styles.spanDetail}>{span.detail}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default PerformancePage;

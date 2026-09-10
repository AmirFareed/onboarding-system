import { useState } from 'react';

import { ChevronLeft, ChevronRight, RefreshCw, Search, ShieldAlert, X } from 'lucide-react';

import EmptyState from '../../components/common/EmptyState/EmptyState';
import ErrorState from '../../components/common/ErrorState/ErrorState';
import Spinner from '../../components/common/Spinner/Spinner';
import StatusChip from '../../components/common/StatusChip/StatusChip';
import { useAuth } from '../../hooks/useAuth';
import { useSystemLogs } from '../../hooks/useSystemLogs';
import { formatDateTime } from '../../utils/format';
import { isIt, isEmployee } from '../../utils/roles';
import styles from './SystemLogsPage.module.css';

const SEVERITY_VARIANTS = {
  INFO: 'info',
  WARNING: 'warning',
  ERROR: 'danger',
};

function severityVariant(severity) {
  return SEVERITY_VARIANTS[severity] ?? 'neutral';
}

/**
 * IT system-log viewer.
 *
 * Read-only view over the shared audit log (`GET /system-logs`): a
 * searchable/filterable, paginated, newest-first table with a detail panel for
 * one entry's full stored record. The page is reachable only by the IT role;
 * the backend 403 remains the authoritative gate -- this gate only decides
 * what the UI shows. Mirrors ApplicationHistoryPage's list + detail-panel
 * shape.
 */
function SystemLogsPage() {
  const { user } = useAuth();
  const {
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
    onActorChange,
    onEventTypeChange,
    onSeverityChange,
    onDateFromChange,
    onDateToChange,
    onQueryChange,
    onIncludeOrphanedChange,
    onGoToPage,
    onSelect,
    onCloseDetail,
    onRefresh,
  } = useSystemLogs();
  const [searchValue, setSearchValue] = useState('');

  const allowed = isIt(user) || isEmployee(user);

  if (!allowed) {
    return (
      <div className={styles.page}>
        <header className={styles.header}>
          <h2 className={styles.title}>System Logs</h2>
          <p className={styles.subtitle}>Audit trail of system and workflow events.</p>
        </header>
        <div className={styles.accessDenied} role="alert">
          <div className={styles.accessDeniedIcon} aria-hidden="true">
            <ShieldAlert />
          </div>
          <h3 className={styles.accessDeniedTitle}>Access denied</h3>
          <p className={styles.accessDeniedText}>
            System logs are restricted to the IT role. Your account is not authorized to view them.
            Contact your administrator if you believe this is in error.
          </p>
        </div>
      </div>
    );
  }

  const submitSearch = () => {
    onQueryChange(searchValue.trim());
  };

  const selected = rows.find((row) => row.id === selectedId);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h2 className={styles.title}>System Logs</h2>
          <p className={styles.subtitle}>Audit trail of system and workflow events, newest first.</p>
        </div>
        <button
          className={styles.refreshBtn}
          type="button"
          onClick={onRefresh}
          disabled={loading}
          aria-label="Refresh system logs"
        >
          <RefreshCw aria-hidden="true" />
          Refresh
        </button>
      </header>

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
              placeholder="Search by actor or action"
              aria-label="Search system logs"
            />
          </div>
          <input
            className={styles.filterInput}
            type="text"
            value={actor}
            onChange={(event) => onActorChange(event.target.value)}
            placeholder="Actor"
            aria-label="Filter by actor"
          />
          <input
            className={styles.filterInput}
            type="text"
            value={eventType}
            onChange={(event) => onEventTypeChange(event.target.value)}
            placeholder="Action"
            aria-label="Filter by action"
          />
          <select
            className={styles.filterSelect}
            value={severity}
            onChange={(event) => onSeverityChange(event.target.value)}
            aria-label="Filter by severity"
          >
            <option value="">All severities</option>
            <option value="INFO">Info</option>
            <option value="WARNING">Warning</option>
            <option value="ERROR">Error</option>
          </select>
          <label className={styles.dateField}>
            <span className={styles.dateLabel}>From</span>
            <input
              className={styles.dateInput}
              type="date"
              value={dateFrom}
              onChange={(event) => onDateFromChange(event.target.value)}
              aria-label="Filter from date"
            />
          </label>
          <label className={styles.dateField}>
            <span className={styles.dateLabel}>To</span>
            <input
              className={styles.dateInput}
              type="date"
              value={dateTo}
              onChange={(event) => onDateToChange(event.target.value)}
              aria-label="Filter to date"
            />
          </label>
          <button
            className={styles.secondaryBtn}
            type="button"
            onClick={submitSearch}
            disabled={loading}
          >
            Search
          </button>
          <label className={styles.orphanToggle}>
            <input
              type="checkbox"
              checked={includeOrphaned}
              onChange={(event) => onIncludeOrphanedChange(event.target.checked)}
            />
            Show entries with no linked application
          </label>
        </div>
        <p className={styles.count} aria-live="polite">
          {total} {total === 1 ? 'entry' : 'entries'}
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
          title="No log entries found"
          message={
            query || actor || eventType || severity || dateFrom || dateTo
              ? 'No log entries match the current search and filters.'
              : 'System and workflow events will appear here as they happen.'
          }
        />
      ) : (
        <>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Timestamp</th>
                  <th scope="col">Actor</th>
                  <th scope="col">Action</th>
                  <th scope="col">Severity</th>
                  <th scope="col">Application</th>
                  <th scope="col" className={styles.actionsHeader}>
                    Details
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const selectedRow = row.id === selectedId;
                  return (
                    <tr key={row.id} className={selectedRow ? styles.selectedRow : undefined}>
                      <td data-label="Timestamp">{formatDateTime(row.performed_at)}</td>
                      <td data-label="Actor">
                        <div className={styles.actorCell}>
                          <span className={styles.actorName}>{row.username}</span>
                          {row.actor_role && (
                            <span className={styles.actorRole}>{row.actor_role}</span>
                          )}
                        </div>
                      </td>
                      <td data-label="Action">
                        <code className={styles.actionCode}>{row.action}</code>
                      </td>
                      <td data-label="Severity">
                        {row.severity ? (
                          <StatusChip label={row.severity} variant={severityVariant(row.severity)} />
                        ) : (
                          <span className={styles.muted}>—</span>
                        )}
                      </td>
                      <td data-label="Application">
                        {row.application_id ? `#${row.application_id}` : (
                          <span className={styles.muted}>—</span>
                        )}
                      </td>
                      <td data-label="Details" className={styles.actionsCell}>
                        <button
                          className={styles.detailBtn}
                          type="button"
                          onClick={() => (selectedRow ? onCloseDetail() : onSelect(row.id))}
                        >
                          {selectedRow ? 'Close' : 'View'}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {pageCount > 1 && (
            <nav className={styles.pagination} aria-label="System log pages">
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

      {selectedId && (
        <section className={styles.panel} aria-label={`Details for log entry ${selectedId}`}>
          <div className={styles.panelHeader}>
            <div>
              <h3 className={styles.panelTitle}>
                {selected?.action ?? `Log entry #${selectedId}`}
              </h3>
              <p className={styles.panelMeta}>Entry #{selectedId}</p>
            </div>
            <button
              type="button"
              className={styles.closeBtn}
              onClick={onCloseDetail}
              aria-label="Close details"
            >
              <X aria-hidden="true" />
            </button>
          </div>

          {detailLoading ? (
            <p className={styles.muted}>Loading details…</p>
          ) : detailError ? (
            <ErrorState message={detailError} onRetry={() => onSelect(selectedId)} />
          ) : detail ? (
            <div className={styles.detailBody}>
              <dl className={styles.detailGrid}>
                <div className={styles.detailRow}>
                  <dt>Timestamp</dt>
                  <dd>{formatDateTime(detail.performed_at)}</dd>
                </div>
                <div className={styles.detailRow}>
                  <dt>Actor</dt>
                  <dd>
                    {detail.username}
                    {detail.actor_role ? ` · ${detail.actor_role}` : ''}
                  </dd>
                </div>
                <div className={styles.detailRow}>
                  <dt>Action</dt>
                  <dd>
                    <code className={styles.actionCode}>{detail.action}</code>
                  </dd>
                </div>
                {detail.severity && (
                  <div className={styles.detailRow}>
                    <dt>Severity</dt>
                    <dd>
                      <StatusChip
                        label={detail.severity}
                        variant={severityVariant(detail.severity)}
                      />
                    </dd>
                  </div>
                )}
                {detail.application_id && (
                  <div className={styles.detailRow}>
                    <dt>Application</dt>
                    <dd>#{detail.application_id}</dd>
                  </div>
                )}
                {detail.document_id && (
                  <div className={styles.detailRow}>
                    <dt>Document</dt>
                    <dd>#{detail.document_id}</dd>
                  </div>
                )}
                {(detail.previous_status || detail.new_status) && (
                  <div className={styles.detailRow}>
                    <dt>Status change</dt>
                    <dd>
                      {detail.previous_status ?? '—'} → {detail.new_status ?? '—'}
                    </dd>
                  </div>
                )}
              </dl>
              {detail.details && (
                <div className={styles.detailJsonWrap}>
                  <p className={styles.detailJsonLabel}>Details</p>
                  <pre className={styles.detailJson}>
                    {JSON.stringify(detail.details, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          ) : null}
        </section>
      )}
    </div>
  );
}

export default SystemLogsPage;

import { useState } from 'react';

import {
  Activity,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  FilePlus2,
  FileText,
  Flag,
  RefreshCw,
  Search,
  ShieldAlert,
  Upload,
  X,
} from 'lucide-react';

import ApplicationStatusBadge from '../../components/applications/ApplicationStatusBadge/ApplicationStatusBadge';
import EmptyState from '../../components/common/EmptyState/EmptyState';
import ErrorState from '../../components/common/ErrorState/ErrorState';
import Spinner from '../../components/common/Spinner/Spinner';
import StatusChip from '../../components/common/StatusChip/StatusChip';
import { APPLICATION_STATUSES } from '../../data/statuses';
import { useApplicationHistory } from '../../hooks/useApplicationHistory';
import { useAuth } from '../../hooks/useAuth';
import { getValidationHistoryEvent } from '../../data/statuses';
import { formatDateTime } from '../../utils/format';
import { isIt, isEmployee } from '../../utils/roles';
import { getDocumentTypeConfig } from '../../data/documents';
import styles from './ApplicationHistoryPage.module.css';

const TIMELINE_ICONS = {
  APPLICATION_CREATED: FilePlus2,
  DOCUMENT_UPLOADED: Upload,
  DOCUMENTS_REQUESTED: FileText,
  DOCUMENTS_RECEIVED: CheckCircle2,
  SUBMITTED_FOR_PROCESSING: Activity,
  OPERATOR_SUBMITTED: Activity,
  OPERATOR_REJECTED: X,
  PROCESSING_COMPLETED: CheckCircle2,
  PROCESSING_FAILED: X,
  REVIEW_DECISION: Flag,
};

/**
 * IT application-history view.
 *
 * Lists every application with its current status and the most recent workflow
 * event (document request, upload, review decision, ...), searchable by
 * id/name/submitter and filterable by status. Selecting an application shows
 * its full chronological lifecycle timeline. The page is reachable only by the
 * IT role; the backend 403 remains the authoritative gate -- this gate only
 * decides what the UI shows.
 */
function ApplicationHistoryPage() {
  const { user } = useAuth();
  const {
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
    onQueryChange,
    onStatusChange,
    onGoToPage,
    onSelect,
    onCloseTimeline,
    onRefresh,
  } = useApplicationHistory();
  const [searchValue, setSearchValue] = useState('');

  const allowed = isIt(user) || isEmployee(user);

  if (!allowed) {
    return (
      <div className={styles.page}>
        <header className={styles.header}>
          <h2 className={styles.title}>Application History</h2>
          <p className={styles.subtitle}>Lifecycle history for every application.</p>
        </header>
        <div className={styles.accessDenied} role="alert">
          <div className={styles.accessDeniedIcon} aria-hidden="true">
            <ShieldAlert />
          </div>
          <h3 className={styles.accessDeniedTitle}>Access denied</h3>
          <p className={styles.accessDeniedText}>
            Application history is restricted to the IT role. Your account is not authorized to view
            it. Contact your administrator if you believe this is in error.
          </p>
        </div>
      </div>
    );
  }

  const submitSearch = () => {
    onQueryChange(searchValue.trim());
  };

  const selected = rows.find((row) => row.application_id === selectedId);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h2 className={styles.title}>Application History</h2>
          <p className={styles.subtitle}>
            Lifecycle history for every application, from submission to decision.
          </p>
        </div>
        <button
          className={styles.refreshBtn}
          type="button"
          onClick={onRefresh}
          disabled={loading}
          aria-label="Refresh application history"
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
              placeholder="Search by id, name or submitter"
              aria-label="Search application history"
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
              : 'Create an application to see its lifecycle history here.'
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
                  <th scope="col">Submitted</th>
                  <th scope="col">Last event</th>
                  <th scope="col" className={styles.actionsHeader}>
                    Timeline
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const event = row.last_event_type
                    ? getValidationHistoryEvent(row.last_event_type)
                    : null;
                  const selectedRow = row.application_id === selectedId;
                  return (
                    <tr
                      key={row.application_id}
                      className={selectedRow ? styles.selectedRow : undefined}
                    >
                      <td data-label="Application">
                        <div className={styles.appCell}>
                          <span className={styles.appId}>#{row.application_id}</span>
                          {row.application_name && (
                            <span className={styles.appName}>{row.application_name}</span>
                          )}
                          <span className={styles.appCreator}>by {row.created_by}</span>
                        </div>
                      </td>
                      <td data-label="Status">
                        <ApplicationStatusBadge status={row.status} />
                      </td>
                      <td data-label="Submitted">{formatDateTime(row.submitted_at)}</td>
                      <td data-label="Last event">
                        {event ? (
                          <div className={styles.lastEvent}>
                            <StatusChip label={event.label} variant={event.variant} />
                            {row.last_event_at && (
                              <span className={styles.lastEventTime}>
                                {formatDateTime(row.last_event_at)}
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className={styles.muted}>No activity yet</span>
                        )}
                      </td>
                      <td data-label="Timeline" className={styles.actionsCell}>
                        <button
                          className={styles.timelineBtn}
                          type="button"
                          onClick={() =>
                            selectedRow ? onCloseTimeline() : onSelect(row.application_id)
                          }
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
            <nav className={styles.pagination} aria-label="Application history pages">
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

      {selected && (
        <section className={styles.panel} aria-label={`Timeline for application ${selected.application_id}`}>
          <div className={styles.panelHeader}>
            <div>
              <h3 className={styles.panelTitle}>
                {selected.application_name || `Application #${selected.application_id}`}
              </h3>
              <p className={styles.panelMeta}>
                #{selected.application_id} · submitted {formatDateTime(selected.submitted_at)}
              </p>
            </div>
            <div className={styles.panelStatus}>
              <ApplicationStatusBadge status={selected.status} />
              <button
                type="button"
                className={styles.closeBtn}
                onClick={onCloseTimeline}
                aria-label="Close timeline"
              >
                <X aria-hidden="true" />
              </button>
            </div>
          </div>

          {timelineLoading ? (
            <p className={styles.muted}>Loading timeline…</p>
          ) : timelineError ? (
            <ErrorState message={timelineError} onRetry={() => onSelect(selected.application_id)} />
          ) : timeline?.events?.length === 0 ? (
            <p className={styles.muted}>No activity recorded yet.</p>
          ) : (
            // Build resubmission cycles from DOCUMENTS_REQUESTED → DOCUMENTS_RECEIVED pairs.
            // Preserve consecutive DOCUMENT_UPLOADED grouping.
            // Keep all events in chronological order.
            <>
              {(() => {
                const events = timeline.events || [];
                
                // Count total cycles for cycle numbering
                const totalCycles = events.filter(e => e.kind === 'DOCUMENTS_REQUESTED').length;
                
                // Find all request→receipt pairs and mark which events belong to each cycle
                const requestedIndices = events
                  .map((e, i) => ({ index: i, kind: e.kind }))
                  .filter(e => e.kind === 'DOCUMENTS_REQUESTED')
                  .map(e => e.index);
                
                const cycles = requestedIndices.map((reqIdx) => {
                  // Find the next DOCUMENTS_RECEIVED after this request
                  const recvIdx = events
                    .slice(reqIdx + 1)
                    .findIndex(e => e.kind === 'DOCUMENTS_RECEIVED');
                  const receiptIndex = recvIdx >= 0 ? reqIdx + 1 + recvIdx : -1;
                  
                  return {
                    requestIndex: reqIdx,
                    receiptIndex,
                    isClosed: receiptIndex >= 0,
                    cycleNumber: requestedIndices.indexOf(reqIdx) + 1,
                  };
                });
                
                // Build the grouped timeline
                const grouped = [];
                const processedIndices = new Set();
                
                for (let i = 0; i < events.length; i++) {
                  if (processedIndices.has(i)) continue;
                  
                  const e = events[i];
                  
                  // Check if this is a DOCUMENTS_REQUESTED that starts a cycle
                  const cycleForThisRequest = cycles.find(c => c.requestIndex === i);
                  if (cycleForThisRequest) {
                    const startIdx = i;
                    const endIdx = cycleForThisRequest.receiptIndex >= 0 
                      ? cycleForThisRequest.receiptIndex 
                      : events.length - 1;
                    
                    const cycleEvents = events.slice(startIdx, endIdx + 1);
                    
                    grouped.push({
                      kind: 'RESUBMISSION_CYCLE',
                      cycleNumber: cycleForThisRequest.cycleNumber,
                      totalCycles,
                      isClosed: cycleForThisRequest.isClosed,
                      timestamp: e.timestamp,
                      events: cycleEvents,
                      requestEvent: e,
                      receiptEvent: cycleForThisRequest.isClosed ? events[cycleForThisRequest.receiptIndex] : null,
                    });
                    
                    // Mark all indices as processed
                    for (let j = startIdx; j <= endIdx; j++) {
                      processedIndices.add(j);
                    }
                    
                    i = endIdx; // Skip past the cycle
                  } else if (e.kind === 'DOCUMENT_UPLOADED') {
                    // Group consecutive uploads (existing behavior)
                    const docs = [e];
                    let j = i + 1;
                    while (j < events.length && events[j].kind === 'DOCUMENT_UPLOADED' && !processedIndices.has(j)) {
                      docs.push(events[j]);
                      j += 1;
                    }

                    grouped.push({
                      kind: 'DOCUMENTS_GROUP',
                      label: 'Documents submitted',
                      timestamp: docs[0].timestamp,
                      items: docs,
                    });
                    
                    for (let k = i; k < j; k++) {
                      processedIndices.add(k);
                    }
                    
                    i = j - 1;
                  } else {
                    // Other events pass through unchanged
                    grouped.push(e);
                    processedIndices.add(i);
                  }
                }

                // Helper to format duration between two timestamps
                const formatDuration = (start, end) => {
                  const diffMs = new Date(end) - new Date(start);
                  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
                  const diffMinutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
                  
                  if (diffHours === 0) return `${diffMinutes}m`;
                  if (diffMinutes === 0) return `${diffHours}h`;
                  return `${diffHours}h ${diffMinutes}m`;
                };

                return (
                  <ol className={styles.timeline}>
                    {grouped.map((event, index) => {
                      // Render resubmission cycles
                      if (event.kind === 'RESUBMISSION_CYCLE') {
                        const Icon = TIMELINE_ICONS.DOCUMENTS_REQUESTED ?? FileText;
                        const waitingDuration = event.isClosed
                          ? formatDuration(event.requestEvent.timestamp, event.receiptEvent.timestamp)
                          : null;
                        
                        // Extract missing documents from detail field
                        const missingDocs = event.requestEvent.detail
                          ? event.requestEvent.detail
                              .replace(/^Requested: /, '')
                              .split(', ')
                          : [];
                        
                        return (
                          <li key={`cycle-${event.cycleNumber}`} className={styles.timelineItem}>
                            <div className={styles.timelineCycleContainer}>
                              {/* Cycle header */}
                              <div className={styles.timelineCycleHeader}>
                                <div className={styles.timelineDot} aria-hidden="true">
                                  <Icon />
                                </div>
                                <div className={styles.timelineBody}>
                                  <div className={styles.timelineHeader}>
                                    <span className={styles.timelineLabel}>
                                      {event.isClosed 
                                        ? `Resubmission Cycle ${event.cycleNumber}` 
                                        : `Waiting for documents`}
                                    </span>
                                    {event.isClosed && event.cycleNumber < event.totalCycles && (
                                      <span className={styles.cycleBadge}>
                                        Cycle {event.cycleNumber} of {event.totalCycles}
                                      </span>
                                    )}
                                  </div>
                                </div>
                              </div>

                              {/* Cycle details */}
                              <div className={styles.timelineCycleDetail}>
                                {/* Request section */}
                                <div className={styles.cyclePhase}>
                                  <div className={styles.cyclePhaseLabel}>
                                    Documents requested
                                  </div>
                                  <div className={styles.cyclePhaseTime}>
                                    {formatDateTime(event.requestEvent.timestamp)}
                                  </div>
                                  {event.requestEvent.actor_name && (
                                    <p className={styles.cyclePhaseActor}>
                                      {event.requestEvent.actor_name}
                                    </p>
                                  )}
                                </div>

                                {/* Missing documents */}
                                {missingDocs.length > 0 && (
                                  <div className={styles.cycleMissingDocs}>
                                    <div className={styles.cycleMissingLabel}>Missing:</div>
                                    <ul className={styles.cycleMissingList}>
                                      {missingDocs.map((docTypeStr, idx) => {
                                        const docType = docTypeStr.trim();
                                        const config = getDocumentTypeConfig(docType);
                                        const humanName = config?.label ?? docType;
                                        return (
                                          <li key={`missing-${idx}`}>
                                            {humanName}
                                          </li>
                                        );
                                      })}
                                    </ul>
                                  </div>
                                )}

                                {/* Waiting period indicator */}
                                {event.isClosed && (
                                  <>
                                    <div className={styles.cycleArrow}>↓ Applicant submitted documents</div>
                                    <div className={styles.cyclePhase}>
                                      <div className={styles.cyclePhaseLabel}>
                                        Documents resubmitted
                                      </div>
                                      <div className={styles.cyclePhaseTime}>
                                        {formatDateTime(event.receiptEvent.timestamp)}
                                      </div>
                                      {waitingDuration && (
                                        <div className={styles.cycleWaitingTime}>
                                          Applicant waiting: {waitingDuration}
                                        </div>
                                      )}
                                    </div>
                                  </>
                                )}

                                {!event.isClosed && (
                                  <div className={styles.cycleArrow}>
                                    ↓ Waiting since {formatDateTime(event.requestEvent.timestamp)}
                                  </div>
                                )}
                              </div>
                            </div>
                          </li>
                        );
                      }

                      // Render document groups (existing behavior)
                      if (event.kind === 'DOCUMENTS_GROUP') {
                        const Icon = TIMELINE_ICONS['DOCUMENT_UPLOADED'] ?? Upload;
                        return (
                          <li key={`group-${index}`} className={styles.timelineItem}>
                            <div className={styles.timelineDot} aria-hidden="true">
                              <Icon />
                            </div>
                            <div className={styles.timelineBody}>
                              <div className={styles.timelineHeader}>
                                <span className={styles.timelineLabel}>Documents submitted</span>
                                <span className={styles.timelineTime}>{formatDateTime(event.timestamp)}</span>
                              </div>
                              <div className={styles.timelineDetail}>
                                        <details>
                                  <summary>
                                    {event.items.length} {event.items.length === 1 ? 'document' : 'documents'}
                                  </summary>
                                  <ul className={styles.uploadList}>
                                    {event.items.map((doc, di) => {
                                      // Use structured document_type field from backend instead of
                                      // parsing from label. Fallback to label parsing for backwards
                                      // compatibility with old API responses.
                                      const docType = doc.document_type || 
                                        doc.label?.replace(/ uploaded$/i, '').split(' (')[0];
                                      const config = getDocumentTypeConfig(docType);
                                      const human = config?.label ?? docType;
                                      const copySuffix = (doc.copy_number && doc.copy_number > 1) 
                                        ? ` — Copy ${doc.copy_number}` 
                                        : '';
                                      const display = human + copySuffix;

                                      return (
                                        <li key={`doc-${di}`}>
                                          <strong>{display}</strong>
                                          {doc.timestamp && (
                                            <span className={styles.uploadMeta}> — {formatDateTime(doc.timestamp)}</span>
                                          )}
                                          {doc.filename && <div className={styles.uploadDetail}>{doc.filename}</div>}
                                        </li>
                                      );
                                    })}
                                  </ul>
                                </details>
                              </div>
                            </div>
                          </li>
                        );
                      }

                      // Render other events (existing behavior)
                      const Icon = TIMELINE_ICONS[event.kind] ?? Clock;
                      return (
                        <li key={`${event.kind}-${index}`} className={styles.timelineItem}>
                          <div className={styles.timelineDot} aria-hidden="true">
                            <Icon />
                          </div>
                          <div className={styles.timelineBody}>
                            <div className={styles.timelineHeader}>
                              <span className={styles.timelineLabel}>{event.label}</span>
                              <span className={styles.timelineTime}>
                                {formatDateTime(event.timestamp)}
                              </span>
                            </div>
                            {event.actor_name && (
                              <p className={styles.timelineActor}>
                                {[event.actor_name, event.actor_role].filter(Boolean).join(' · ')}
                              </p>
                            )}
                            {event.detail && <p className={styles.timelineDetail}>{event.detail}</p>}
                          </div>
                        </li>
                      );
                    })}
                  </ol>
                );
              })()}
            </>
          )}
        </section>
      )}
    </div>
  );
}

export default ApplicationHistoryPage;

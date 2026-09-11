import { Link } from 'react-router-dom';

import { AlertCircle, CheckCircle2, Clock, Loader2, RefreshCw } from 'lucide-react';

import ApplicationStatusBadge from '../../components/applications/ApplicationStatusBadge/ApplicationStatusBadge';
import EmptyState from '../../components/common/EmptyState/EmptyState';
import ErrorState from '../../components/common/ErrorState/ErrorState';
import Spinner from '../../components/common/Spinner/Spinner';
import StatusChip from '../../components/common/StatusChip/StatusChip';
import { useAuth } from '../../hooks/useAuth';
import { useProcessingOverview } from '../../hooks/useProcessingOverview';
import { useBatchUploadStore } from '../../store/BatchUploadContext';
import { canUploadDocuments } from '../../utils/permissions';
import styles from './ProcessingPage.module.css';

/**
 * Processing status for every application.
 *
 * Summarises how each application is progressing through document processing:
 * how many documents are done, how many are left, and which ones need
 * attention. Rows link to the application and offer a retry for failed
 * documents. The view auto-refreshes while work is in flight unless the
 * autoRefreshProcessingStatus preference is disabled.
 */
function ProcessingPage() {
  const { user } = useAuth();
  const { rows, loading, refreshing, error, reload, retry, retryingIds } = useProcessingOverview();
  // Files still queued in the batch-upload feature (see BatchUploadPage) have
  // no Application yet -- BatchUploadContext only creates one when a file's
  // turn to process actually arrives -- so useProcessingOverview's
  // listApplications-backed `rows` has no way to know about them. Reading
  // the same app-level context batch-upload itself uses (mounted in
  // ProtectedLayout, so it survives navigating here) is the only way to show
  // the full batch picture in one place instead of just the files already
  // underway.
  const { items: batchItems } = useBatchUploadStore();
  const pendingBatchItems = batchItems.filter((item) => item.status === 'pending');

  const totals = rows.reduce(
    (acc, { progress }) => {
      if (progress == null) {
        return acc;
      }
      acc.totalDocs += Number(progress.total_documents) || 0;
      acc.completed += Number(progress.completed) || 0;
      acc.failed += Number(progress.failed) || 0;
      acc.inFlight +=
        (Number(progress.queued) || 0) + (Number(progress.processing) || 0);
      if (Number(progress.processing) > 0) {
        acc.busyApplications += 1;
      }
      return acc;
    },
    { totalDocs: 0, completed: 0, failed: 0, inFlight: 0, busyApplications: 0 }
  );

  const remaining = Math.max(totals.totalDocs - totals.completed, 0);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h2 className={styles.title}>Processing</h2>
          <p className={styles.subtitle}>
            See how each application is moving through document processing.
          </p>
        </div>
        <button
          className={styles.refreshBtn}
          type="button"
          onClick={reload}
          disabled={refreshing}
          aria-label="Refresh processing status"
        >
          <RefreshCw aria-hidden="true" />
          Refresh
        </button>
      </header>

      <div className={styles.summary} aria-live="polite">
        <div className={styles.card}>
          <span className={styles.cardValue}>{rows.length}</span>
          <span className={styles.cardLabel}>Applications</span>
        </div>
        <div className={styles.card}>
          <span className={styles.cardValue}>{totals.busyApplications}</span>
          <span className={styles.cardLabel}>Processing now</span>
        </div>
        <div className={styles.card}>
          <span className={styles.cardValue}>{remaining}</span>
          <span className={styles.cardLabel}>Documents left</span>
        </div>
        <div className={styles.card}>
          <span className={`${styles.cardValue} ${totals.failed ? styles.cardValueAttention : ''}`}>
            {totals.failed}
          </span>
          <span className={styles.cardLabel}>Need attention</span>
        </div>
        <div className={styles.card}>
          <span className={styles.cardValue}>{pendingBatchItems.length}</span>
          <span className={styles.cardLabel}>Queued</span>
        </div>
      </div>

      {loading && rows.length === 0 ? (
        <div className={styles.center} aria-busy="true">
          <Spinner size="medium" />
        </div>
      ) : error && rows.length === 0 ? (
        <ErrorState message="Unable to load processing status." onRetry={reload} />
      ) : rows.length === 0 && pendingBatchItems.length === 0 ? (
        <EmptyState
          title="No applications yet"
          message="Create an application and upload documents to see processing status here."
          action={
            canUploadDocuments(user) ? (
              <Link to="/applications/new" className={styles.createBtn}>
                Create New Application
              </Link>
            ) : undefined
          }
        />
      ) : (
        <ul className={styles.list}>
          {rows.map(({ application, progress }) => {
            const total = Number(progress?.total_documents) || 0;
            const completed = Number(progress?.completed) || 0;
            const failed = Number(progress?.failed) || 0;
            const queued = Number(progress?.queued) || 0;
            const processing = Number(progress?.processing) || 0;
            const percent = total ? Math.round((completed / total) * 100) : 0;
            return (
              <li key={application.id} className={styles.item}>
                <div className={styles.itemHeader}>
                  <Link to={`/applications/${application.id}`} className={styles.appLink}>
                    #{application.id}
                    {application.name && <span className={styles.appName}>{application.name}</span>}
                  </Link>
                  <ApplicationStatusBadge status={application.status} />
                </div>

                {progress == null ? (
                  <p className={styles.unavailable}>Processing status unavailable.</p>
                ) : total === 0 ? (
                  <p className={styles.idle}>
                    No documents uploaded yet.{' '}
                    <Link to={`/applications/${application.id}/upload`} className={styles.uploadLink}>
                      Upload documents
                    </Link>
                  </p>
                ) : (
                  <div className={styles.progressArea}>
                    <div className={styles.progressRow}>
                      <div
                        className={styles.track}
                        role="progressbar"
                        aria-valuenow={percent}
                        aria-valuemin="0"
                        aria-valuemax="100"
                        aria-label={`${completed} of ${total} documents processed`}
                      >
                        <span className={styles.trackFill} style={{ width: `${percent}%` }} />
                      </div>
                      <span className={styles.counts}>
                        {completed} of {total} done · {total - completed} left
                      </span>
                    </div>
                    <div className={styles.statusRow}>
                      {queued > 0 && (
                        <span className={`${styles.chip} ${styles.chipQueued}`}>
                          <Clock aria-hidden="true" /> {queued} queued
                        </span>
                      )}
                      {processing > 0 && (
                        <span className={`${styles.chip} ${styles.chipProcessing}`}>
                          <Loader2 aria-hidden="true" /> {processing} processing
                        </span>
                      )}
                      {failed > 0 && (
                        <span className={`${styles.chip} ${styles.chipFailed}`}>
                          <AlertCircle aria-hidden="true" /> {failed} need attention
                        </span>
                      )}
                      {completed > 0 && (
                        <span className={`${styles.chip} ${styles.chipDone}`}>
                          <CheckCircle2 aria-hidden="true" /> {completed} completed
                        </span>
                      )}
                      {failed > 0 && (
                        <button
                          className={styles.retryBtn}
                          type="button"
                          onClick={() => retry(application.id)}
                          disabled={retryingIds.has(application.id)}
                        >
                          {retryingIds.has(application.id) ? (
                            <Spinner size="small" />
                          ) : (
                            <RefreshCw aria-hidden="true" />
                          )}
                          {retryingIds.has(application.id) ? 'Retrying…' : 'Retry failed'}
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </li>
            );
          })}
          {pendingBatchItems.map((item) => (
            <li key={item.clientId} className={styles.item}>
              <div className={styles.itemHeader}>
                <span className={styles.appLink}>
                  <span className={styles.appName}>{item.previewName}</span>
                </span>
                <StatusChip label="Pending" variant="neutral" />
              </div>
              <p className={styles.idle}>Queued for batch upload — not started yet.</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default ProcessingPage;

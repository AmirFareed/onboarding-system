import { AlertCircle, CheckCircle2, Play, RefreshCw } from 'lucide-react';

import ErrorState from '../../common/ErrorState/ErrorState';
import Spinner from '../../common/Spinner/Spinner';
import { useProcessingProgress } from '../../../hooks/useProcessingProgress';
import styles from './ProcessingProgress.module.css';

function ProcessingProgress({ applicationId }) {
  const {
    progress,
    documents,
    loading,
    actionLoading,
    error,
    reload,
    start,
    retry,
  } = useProcessingProgress(applicationId);

  if (loading && !progress) {
    return <section className={styles.section} aria-busy="true"><Spinner size="medium" /></section>;
  }
  if (error && !progress) {
    return <section className={styles.section}><ErrorState message="Unable to load processing progress." onRetry={reload} /></section>;
  }
  if (!progress || progress.total_documents === 0) {
    return (
      <section className={styles.section} aria-label="Document processing">
        <div className={styles.heading}><h3>Processing Documents</h3><span>No documents ready</span></div>
        <p className={styles.empty}>Upload documents to begin processing.</p>
      </section>
    );
  }

  const completed = progress.completed;
  const attention = progress.documents_needing_attention;
  return (
    <section className={styles.section} aria-label="Document processing">
      <div className={styles.header}>
        <div><h3>Processing Documents</h3><p>{completed} of {progress.total_documents} documents processed</p></div>
        <div className={styles.actions}>
          <button className={styles.primaryButton} type="button" onClick={() => start()} disabled={actionLoading}>
            <Play aria-hidden="true" /> Start Processing
          </button>
          {attention > 0 && (
            <button className={styles.secondaryButton} type="button" onClick={() => retry()} disabled={actionLoading}>
              <RefreshCw aria-hidden="true" /> Retry Documents
            </button>
          )}
          <button
            className={styles.secondaryButton}
            type="button"
            onClick={reload}
            disabled={actionLoading}
            aria-label="Refresh processing status"
          >
            <RefreshCw aria-hidden="true" /> Refresh
          </button>
        </div>
      </div>
      <div className={styles.progressTrack} role="progressbar" aria-valuenow={progress.progress_percentage} aria-valuemin="0" aria-valuemax="100">
        <span style={{ width: `${progress.progress_percentage}%` }} />
      </div>
      <div className={styles.summary}>
        <span><RefreshCw aria-hidden="true" /> {progress.queued} waiting</span>
        <span><Spinner size="small" /> {progress.processing} currently processing</span>
        <span className={attention ? styles.attention : styles.complete}>
          {attention ? <AlertCircle aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />} {attention} documents need attention
        </span>
      </div>
      <ul className={styles.documents}>
        {documents.map((document) => (
          <li key={document.document_id}>
            <span>{document.file_name}</span>
            <span className={`${styles.status} ${styles[document.status?.toLowerCase()]}`}>{document.message}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default ProcessingProgress;

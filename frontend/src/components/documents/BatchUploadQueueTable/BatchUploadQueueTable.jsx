import { Link } from 'react-router-dom';
import { Eye, X } from 'lucide-react';

import StatusChip from '../../common/StatusChip/StatusChip';
import EmptyState from '../../common/EmptyState/EmptyState';
import { BATCH_PHASE_LABELS, getBatchItemStatusDisplay } from '../../../data/batchStatuses';
import styles from './BatchUploadQueueTable.module.css';

/**
 * One row's status/progress detail line, shown under the StatusChip.
 *
 * @param {object} props
 * @param {object} props.item A batch queue item from BatchUploadContext.
 */
function StatusDetail({ item }) {
  if (item.status === 'processing') {
    const phaseLabel = BATCH_PHASE_LABELS[item.phase] ?? 'Processing…';
    const progressSuffix = item.phase === 'uploading' ? ` ${item.progress}%` : '';
    return (
      <span className={styles.detail}>
        {phaseLabel}
        {progressSuffix}
      </span>
    );
  }
  if (item.status === 'completed' && item.applicationStatus === 'NEEDS_DOCUMENTS') {
    return <span className={styles.detail}>Additional documents needed</span>;
  }
  if (item.status === 'failed' && item.error) {
    return <span className={styles.detailError}>{item.error}</span>;
  }
  return null;
}

/**
 * Queue table for the batch PDF upload feature: one row per selected file,
 * its derived/actual application name, current status and a link to the
 * application once it exists.
 *
 * @param {object} props
 * @param {Array<object>} props.items Queue items from useBatchUploadStore().
 * @param {Function} props.onRemove Called with a clientId to remove a
 *   still-pending file from the queue.
 */
function BatchUploadQueueTable({ items, onRemove }) {
  if (items.length === 0) {
    return (
      <EmptyState
        title="No files selected"
        message="Add PDF files above to build the batch. Each one becomes its own application."
      />
    );
  }

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">File</th>
            <th scope="col">Application</th>
            <th scope="col">Status</th>
            <th scope="col" className={styles.actionsHeader}>
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const display = getBatchItemStatusDisplay(item.status);
            return (
              <tr key={item.clientId} className={styles.row}>
                <td className={styles.fileCell} data-label="File">
                  {item.filename}
                </td>
                <td data-label="Application">{item.applicationName ?? item.previewName}</td>
                <td data-label="Status">
                  <div className={styles.statusCell}>
                    <StatusChip label={display.label} variant={display.variant} />
                    <StatusDetail item={item} />
                  </div>
                </td>
                <td className={styles.actionsCell} data-label="Actions">
                  <div className={styles.actions}>
                    {item.applicationId != null && (
                      <Link
                        to={`/applications/${item.applicationId}`}
                        className={styles.actionLink}
                        aria-label={`View application for ${item.filename}`}
                      >
                        <Eye aria-hidden="true" />
                        View
                      </Link>
                    )}
                    {item.status === 'pending' && (
                      <button
                        type="button"
                        className={styles.actionLink}
                        aria-label={`Remove ${item.filename} from the queue`}
                        onClick={() => onRemove(item.clientId)}
                      >
                        <X aria-hidden="true" />
                        Remove
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default BatchUploadQueueTable;

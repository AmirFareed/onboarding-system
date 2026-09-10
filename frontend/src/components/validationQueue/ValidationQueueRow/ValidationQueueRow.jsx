import { ClipboardList } from 'lucide-react';

import { getValidationHistoryEvent } from '../../../data/statuses';
import { formatDateTime } from '../../../utils/format';
import ApplicationStatusBadge from '../../applications/ApplicationStatusBadge/ApplicationStatusBadge';
import StatusChip from '../../common/StatusChip/StatusChip';
import styles from './ValidationQueueRow.module.css';

/**
 * A single application row in the operator validation queue.
 *
 * Shown values are deliberately business-level: status, document counts and
 * the last workflow event -- never OCR/processing internals. On mobile the row
 * collapses into a card, matching the ApplicationRow pattern.
 *
 * @param {object} props
 * @param {object} props.application Validation queue item to display.
 * @param {boolean} props.selected Whether this row is the active selection.
 * @param {Function} props.onSelect Callback invoked with the application id.
 */
function ValidationQueueRow({ application, selected, onSelect }) {
  const lastEvent = application.last_event_type
    ? getValidationHistoryEvent(application.last_event_type)
    : null;

  return (
    <tr
      className={`${styles.row} ${selected ? styles.selected : ''}`}
      onClick={() => onSelect(application.application_id)}
    >
      <td data-label="Application">
        <span className={styles.applicationName}>
          {application.application_name || `Application #${application.application_id}`}
        </span>
        {application.needs_attention && (
          <StatusChip label="Needs attention" variant="warning" />
        )}
      </td>
      <td data-label="Status">
        <ApplicationStatusBadge status={application.status} />
      </td>
      <td data-label="Documents">
        <span className={styles.documentsCount}>
          {application.received_document_count} of {application.required_document_count} received
        </span>
        <span className={styles.completion}>
          {Math.round(application.completion_percentage)}% complete
        </span>
      </td>
      <td data-label="Missing">
        {application.missing_document_count > 0 ? (
          <span className={styles.missingCount}>{application.missing_document_count} missing</span>
        ) : (
          <span className={styles.completeLabel}>None</span>
        )}
      </td>
      <td data-label="Last Activity">
        {lastEvent ? (
          <>
            <span className={styles.eventLabel}>{lastEvent.label}</span>
            <span className={styles.eventTime}>{formatDateTime(application.last_event_at)}</span>
          </>
        ) : (
          <span className={styles.completeLabel}>—</span>
        )}
      </td>
      <td className={styles.actionsCell} data-label="Review">
        <button
          type="button"
          className={styles.actionButton}
          onClick={(event) => {
            event.stopPropagation();
            onSelect(application.application_id);
          }}
          aria-label={`Review application ${application.application_id}`}
        >
          <ClipboardList aria-hidden="true" />
          Review
        </button>
      </td>
    </tr>
  );
}

export default ValidationQueueRow;
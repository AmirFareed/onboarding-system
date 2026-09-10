import ValidationQueueRow from '../ValidationQueueRow/ValidationQueueRow';
import styles from './ValidationQueueTable.module.css';

/**
 * Operator validation queue table.
 *
 * Lists every application with its business-level completeness state. Rows are
 * shown in the backend's returned order (no client-side sorting); selecting a
 * row opens the action + history panel.
 *
 * @param {object} props
 * @param {Array<object>} props.applications Queue items to display.
 * @param {number|null} props.selectedId Currently selected application id.
 * @param {Function} props.onSelect Callback invoked with an application id.
 */
function ValidationQueueTable({ applications, selectedId, onSelect }) {
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">Application</th>
            <th scope="col">Status</th>
            <th scope="col">Documents</th>
            <th scope="col">Missing</th>
            <th scope="col">Last Activity</th>
            <th scope="col" className={styles.actionsHeader}>
              Review
            </th>
          </tr>
        </thead>
        <tbody>
          {applications.map((application) => (
            <ValidationQueueRow
              key={application.application_id}
              application={application}
              selected={application.application_id === selectedId}
              onSelect={onSelect}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default ValidationQueueTable;
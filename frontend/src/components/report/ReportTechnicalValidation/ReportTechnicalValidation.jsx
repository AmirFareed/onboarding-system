import StatusChip from '../../common/StatusChip/StatusChip';
import { getRuleResultStatus } from '../../../data/statuses';
import styles from './ReportTechnicalValidation.module.css';

/**
 * Document-quality validation results.
 *
 * Each row reports the file-level quality outcome for a document: overall
 * status, readability, rotation state and any failed checks or warnings. File
 * contents and extracted fields never appear here.
 *
 * @param {object} props
 * @param {object[]} props.items The stored document-quality reports.
 */
function ReportTechnicalValidation({ items }) {
  if (!items || items.length === 0) {
    return (
      <p className={styles.empty}>
        No document-quality results are available for these documents.
      </p>
    );
  }

  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th scope="col">Document</th>
          <th scope="col">Type</th>
          <th scope="col">Status</th>
          <th scope="col">Readability</th>
          <th scope="col">Rotation</th>
          <th scope="col">Issues</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => {
          const status = getRuleResultStatus(item.validation_status);
          const readability = getRuleResultStatus(item.readability_status);
          const rotation = getRuleResultStatus(item.rotation_status);
          const issues = [...(item.failed_checks ?? []), ...(item.warnings ?? [])];
          return (
            <tr key={item.document_id}>
              <td data-label="Document" className={styles.fileCell}>
                {item.file_name}
              </td>
              <td data-label="Type" className={styles.mutedCell}>
                {item.file_type}
              </td>
              <td data-label="Status">
                <StatusChip label={status.label} variant={status.variant} />
              </td>
              <td data-label="Readability">
                <StatusChip label={readability.label} variant={readability.variant} />
              </td>
              <td data-label="Rotation">
                <StatusChip label={rotation.label} variant={rotation.variant} />
              </td>
              <td data-label="Issues" className={styles.mutedCell}>
                {issues.length > 0 ? issues.join('; ') : 'None'}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export default ReportTechnicalValidation;
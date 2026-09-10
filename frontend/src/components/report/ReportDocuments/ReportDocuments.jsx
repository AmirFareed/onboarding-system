import StatusChip from '../../common/StatusChip/StatusChip';
import { getDocumentStatus, getRuleResultStatus } from '../../../data/statuses';
import { getDocumentTypeConfig } from '../../../data/documents';
import styles from './ReportDocuments.module.css';

/**
 * Per-document status table from the validation report.
 *
 * Each row shows the document type, processing outcome, document-quality
 * outcome and the field-extraction result, in business-facing language. The
 * raw OCR/technical/analysis status values are mapped to employee-friendly
 * outcomes via the shared status catalogue.
 *
 * @param {object} props
 * @param {object[]} props.documents The report's `document_summary` rows.
 */
function ReportDocuments({ documents }) {
  if (!documents || documents.length === 0) {
    return (
      <p className={styles.empty}>No documents were included in this report.</p>
    );
  }

  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th scope="col">Document</th>
          <th scope="col">Processing</th>
          <th scope="col">Document quality</th>
          <th scope="col">Field extraction</th>
          <th scope="col">Needs attention</th>
        </tr>
      </thead>
      <tbody>
        {documents.map((document) => {
          const config = getDocumentTypeConfig(document.document_type);
          const processing = getDocumentStatus(document.processing_status);
          const ocr = getRuleResultStatus(document.ocr_status);
          const technical = getRuleResultStatus(document.technical_validation_status);
          const analysis = getRuleResultStatus(document.analysis_status);
          const needsAttention =
            ocr.variant === 'danger' ||
            technical.variant === 'danger' ||
            analysis.variant === 'danger';
          return (
            <tr key={document.document_id}>
              <td data-label="Document" className={styles.typeCell}>
                {config.label}
              </td>
              <td data-label="Processing">
                <StatusChip label={processing.label} variant={processing.variant} />
              </td>
              <td data-label="Document quality">
                <StatusChip label={technical.label} variant={technical.variant} />
              </td>
              <td data-label="Field extraction">
                <StatusChip label={analysis.label} variant={analysis.variant} />
              </td>
              <td data-label="Needs attention">
                <StatusChip
                  label={needsAttention ? 'Yes' : 'No'}
                  variant={needsAttention ? 'warning' : 'success'}
                />
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export default ReportDocuments;
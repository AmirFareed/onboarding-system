import StatusChip from '../../common/StatusChip/StatusChip';
import { getDocumentTypeConfig } from '../../../data/documents';
import styles from './ReportCompleteness.module.css';

/**
 * Completeness result section with progress bar and grouped document list.
 *
 * Shows the completion percentage, a visual progress bar, and a clear
 * separation between present, missing, and duplicate documents.
 *
 * @param {object} props
 * @param {object|null} props.completeness The completeness report.
 */
function ReportCompleteness({ completeness }) {
  if (!completeness) {
    return null;
  }

  const presentCount =
    completeness.required_documents?.filter((d) => d.is_present).length ?? 0;
  const requiredCount = completeness.required_documents?.length ?? 0;
  const percentage = Math.round(completeness.completion_percentage ?? 0);

  const present =
    completeness.required_documents?.filter((d) => d.is_present) ?? [];
  const missing = completeness.missing_documents ?? [];
  const duplicates = completeness.duplicate_documents ?? [];

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <span className={styles.count}>
          {presentCount} / {requiredCount} Required Documents Present
        </span>
        <span className={styles.percentage}>{percentage}%</span>
      </div>

      <div className={styles.progressTrack}>
        <div
          className={styles.progressFill}
          style={{ width: `${percentage}%` }}
        />
      </div>

      {present.length > 0 && (
        <div className={styles.group}>
          <h4 className={styles.groupTitle}>Present</h4>
          <ul className={styles.docList}>
            {present.map((doc) => {
              const config = getDocumentTypeConfig(doc.document_type);
              return (
                <li key={doc.document_type} className={styles.docItem}>
                  <StatusChip label={'\u2713'} variant="success" />
                  <span className={styles.docLabel}>{config.label}</span>
                  <span className={styles.copyCount}>
                    {doc.copy_count} {doc.copy_count === 1 ? 'copy' : 'copies'}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {missing.length > 0 && (
        <div className={styles.group}>
          <h4 className={styles.groupTitle}>Missing</h4>
          <ul className={styles.docList}>
            {missing.map((docType) => {
              const type = typeof docType === 'string' ? docType : docType.document_type;
              const config = getDocumentTypeConfig(type);
              return (
                <li key={type} className={styles.docItem}>
                  <StatusChip label={'\u2715'} variant="danger" />
                  <span className={styles.docLabel}>{config.label}</span>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {duplicates.length > 0 && (
        <div className={styles.group}>
          <h4 className={styles.groupTitle}>Duplicates</h4>
          <ul className={styles.docList}>
            {duplicates.map((dup) => {
              const docType = typeof dup === 'string' ? dup : dup.document_type;
              const copyCount = typeof dup === 'object' ? dup.copy_count : null;
              const config = getDocumentTypeConfig(docType);
              return (
                <li key={docType} className={styles.docItem}>
                  <StatusChip label={'\u26A0'} variant="warning" />
                  <span className={styles.docLabel}>{config.label}</span>
                  {copyCount && (
                    <span className={styles.copyCount}>{copyCount} copies</span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

export default ReportCompleteness;

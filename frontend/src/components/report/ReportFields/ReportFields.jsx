import StatusChip from '../../common/StatusChip/StatusChip';
import { getReportStatus } from '../../../data/statuses';
import { getFieldLabel } from '../../../data/fieldLabels';
import styles from './ReportFields.module.css';

/**
 * Group normalized fields by their source document.
 */
function groupByDocument(fields) {
  const byDoc = new Map();
  for (const field of fields) {
    const key = field.file_name ?? field.document_id ?? 'Unknown';
    if (!byDoc.has(key)) {
      byDoc.set(key, { docName: key, docId: field.document_id, fields: [] });
    }
    byDoc.get(key).fields.push(field);
  }
  return [...byDoc.values()];
}

/**
 * Single field row with human-readable label.
 * Shows extraction mismatch warning for account_number when it matches IBAN format.
 */
function FieldRow({ field, allFields }) {
  const status = getReportStatus(field.verification_status);
  const hasNormalized =
    field.normalized_value && field.normalized_value !== field.extracted_value;

  const isIbanMismatch =
    field.field_name === 'account_number' &&
    allFields.some((f) => {
      if (f.field_name !== 'iban') return false;
      const acctVal = field.extracted_value ?? '';
      const ibanVal = f.extracted_value ?? '';
      return acctVal === ibanVal && acctVal.startsWith('PK') && acctVal.length > 20;
    });

  const displayStatus = isIbanMismatch
    ? { label: 'Needs Review', variant: 'warning', icon: '\u26A0' }
    : status;

  return (
    <div className={styles.fieldRow}>
      <div className={styles.fieldHeader}>
        <span className={styles.fieldLabel}>{getFieldLabel(field.field_name)}</span>
        <StatusChip label={displayStatus.label} variant={displayStatus.variant} icon={displayStatus.icon} />
      </div>
      <div className={styles.fieldValues}>
        <span className={styles.fieldValue}>{field.extracted_value || '\u2014'}</span>
        {hasNormalized && (
          <span className={styles.fieldNormalized}>
            Standardized: {field.normalized_value}
          </span>
        )}
        {isIbanMismatch && (
          <span className={styles.fieldWarning}>
            This value matches the structure of an IBAN. Verify the Account Number against the source document.
          </span>
        )}
      </div>
    </div>
  );
}

/**
 * Fallback display for analysis items when normalized fields are unavailable.
 */
function AnalysisFallback({ items }) {
  const withFields = (items ?? []).filter(
    (item) => item.extracted_fields && Object.keys(item.extracted_fields).length > 0
  );

  if (withFields.length === 0) {
    return (
      <p className={styles.empty}>
        No extracted fields available for this application.
      </p>
    );
  }

  return (
    <div className={styles.docList}>
      {withFields.map((item) => (
        <div key={item.document_id} className={styles.docCard}>
          <h4 className={styles.docTitle}>{item.file_name}</h4>
          <dl className={styles.fieldList}>
            {Object.entries(item.extracted_fields).map(([name, value]) => (
              <div key={name} className={styles.fieldRow}>
                <dt className={styles.fieldLabel}>{getFieldLabel(name)}</dt>
                <dd className={styles.fieldValue}>{value ?? '\u2014'}</dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </div>
  );
}

/**
 * Extracted and normalized field results with human-readable labels.
 *
 * Fields are grouped by source document. Each field shows its human-readable
 * label, extracted value, optional standardized value, and verification status.
 * An IBAN mismatch warning is surfaced when the account number appears to
 * contain an IBAN-format value.
 *
 * @param {object} props
 * @param {object[]} props.normalized Stored normalized field records.
 * @param {object[]} props.analysisItems Document-analysis result rows.
 * @param {object} props.fields Fields summary from the view model.
 */
function ReportFields({ normalized, analysisItems, fields }) {
  if (normalized && normalized.length > 0) {
    const groups = groupByDocument(normalized);

    return (
      <div className={styles.wrap}>
        <div className={styles.progress}>
          <span className={styles.progressLabel}>
            {fields.verified} / {fields.total} extracted fields verified automatically
          </span>
          <div className={styles.progressTrack}>
            <div
              className={styles.progressFill}
              style={{ width: `${fields.progress}%` }}
            />
          </div>
          <span className={styles.progressValue}>{fields.progress}%</span>
        </div>

        <div className={styles.fieldGroups}>
          {groups.map((group) => (
            <div key={group.docId ?? group.docName} className={styles.fieldGroup}>
              <h4 className={styles.docTitle}>{group.docName}</h4>
              {group.fields.map((field, index) => (
                <FieldRow
                  key={`${field.field_name}-${field.document_id}-${index}`}
                  field={field}
                  allFields={normalized}
                />
              ))}
            </div>
          ))}
        </div>
      </div>
    );
  }

  return <AnalysisFallback items={analysisItems} />;
}

export default ReportFields;

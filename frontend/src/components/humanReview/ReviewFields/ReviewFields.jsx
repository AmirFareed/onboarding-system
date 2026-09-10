import { Fragment } from 'react';

import { AlertTriangle, Pencil, X } from 'lucide-react';

import StatusChip from '../../common/StatusChip/StatusChip';
import { getRuleResultStatus } from '../../../data/statuses';
import { getFieldLabel } from '../../../data/fieldLabels';
import styles from './ReviewFields.module.css';

/**
 * Composite key for a field's correction draft.
 */
function correctionKey(documentId, fieldName) {
  return `${documentId}::${fieldName}`;
}

function confidenceClass(score) {
  if (score == null) return 'muted';
  if (score >= 0.9) return 'high';
  if (score >= 0.7) return 'medium';
  return 'low';
}

/**
 * Check if an account number value looks like an IBAN (PK + long alphanumeric).
 */
function isIbanFormat(value) {
  if (!value) return false;
  return /^PK\d{2}[A-Z0-9]{16,}$/i.test(value.replace(/\s/g, ''));
}

/**
 * Extracted fields with their confidence and correction workflow.
 *
 * Each row shows the human-readable field name, its source document, the
 * extracted value, the normalized value, the confidence score and the
 * verification status. Fields can be corrected with an inline editor.
 *
 * @param {object} props
 * @param {object[]} props.fields The review screen's fields.
 * @param {object[]} props.corrections Current correction entries.
 * @param {Function} props.onCorrectionsChange Correction update handler.
 * @param {boolean} props.readOnly Disable correction actions.
 */
function ReviewFields({ fields, corrections, onCorrectionsChange, readOnly = false }) {
  if (!fields || fields.length === 0) {
    return (
      <p className={styles.empty}>No extracted fields are available for this application.</p>
    );
  }

  const correctionByField = new Map(
    corrections.map((correction) => [
      correctionKey(correction.document_id, correction.field_name),
      correction,
    ])
  );

  const updateCorrection = (documentId, fieldName, patch) => {
    const key = correctionKey(documentId, fieldName);
    const current = correctionByField.get(key);
    const next = { ...(current ?? {}), document_id: documentId, field_name: fieldName, ...patch };
    onCorrectionsChange([
      ...corrections.filter(
        (correction) => correctionKey(correction.document_id, correction.field_name) !== key
      ),
      next,
    ]);
  };

  const addCorrection = (field) => {
    if (readOnly) return;
    const defaultValue = field.normalized_value || field.extracted_value || '';
    const key = correctionKey(field.document_id, field.field_name);
    if (!correctionByField.has(key)) {
      onCorrectionsChange([
        ...corrections,
        {
          document_id: field.document_id,
          field_name: field.field_name,
          corrected_value: defaultValue,
          reason: '',
        },
      ]);
    }
  };

  const removeCorrection = (documentId, fieldName) => {
    const key = correctionKey(documentId, fieldName);
    onCorrectionsChange(
      corrections.filter(
        (correction) => correctionKey(correction.document_id, correction.field_name) !== key
      )
    );
  };

  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th scope="col">Field</th>
          <th scope="col">Extracted value</th>
          <th scope="col">Normalized value</th>
          <th scope="col">Confidence</th>
          <th scope="col">Status</th>
          <th scope="col">
            <span className={styles.srOnly}>Actions</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {fields.map((field) => {
          const status = getRuleResultStatus(field.verification_status);
          const hasCorrectedValue = field.human_corrected_value != null;
          const isCorrected = field.human_verified || hasCorrectedValue;
          const key = correctionKey(field.document_id, field.field_name);
          const isCorrecting = correctionByField.has(key);
          const correction = correctionByField.get(key);
          const fieldLabel = getFieldLabel(field.field_name);
          const showIbanWarning =
            field.field_name === 'account_number' && isIbanFormat(field.extracted_value);

          return (
            <Fragment key={`${field.document_id}-${field.field_name}`}>
              <tr>
                <td data-label="Field" className={styles.fieldCell}>
                  <span className={styles.fieldName}>{fieldLabel}</span>
                  <span className={styles.sourceDoc}>{field.file_name}</span>
                </td>
                <td data-label="Extracted value">
                  {field.extracted_value || '—'}
                </td>
                <td data-label="Normalized value">
                  {field.normalized_value || '—'}
                  {hasCorrectedValue && (
                    <span className={styles.corrected}>
                      Corrected: {field.human_corrected_value}
                    </span>
                  )}
                </td>
                <td
                  data-label="Confidence"
                  className={`${styles.confidence} ${styles[confidenceClass(field.confidence_score)]}`}
                >
                  {field.confidence_score != null
                    ? `${Math.round(field.confidence_score * 100)}%`
                    : '—'}
                </td>
                <td data-label="Status">
                  {isCorrected ? (
                    <StatusChip
                      label={hasCorrectedValue ? 'Human Corrected' : 'Reviewed'}
                      variant={hasCorrectedValue ? 'info' : 'success'}
                    />
                  ) : (
                    <StatusChip label={status.label} variant={status.variant} />
                  )}
                </td>
                <td data-label="Actions" className={styles.actionCell}>
                  {!readOnly && !isCorrected && !isCorrecting && (
                    <button
                      type="button"
                      className={styles.correctBtn}
                      onClick={() => addCorrection(field)}
                    >
                      <Pencil aria-hidden="true" />
                      Correct
                    </button>
                  )}
                  {isCorrecting && (
                    <button
                      type="button"
                      className={styles.removeBtn}
                      onClick={() => removeCorrection(field.document_id, field.field_name)}
                      aria-label={`Cancel correction for ${fieldLabel}`}
                    >
                      <X aria-hidden="true" />
                      Cancel
                    </button>
                  )}
                </td>
              </tr>

              {/* IBAN mismatch warning */}
              {showIbanWarning && !isCorrecting && (
                <tr className={styles.warningRow}>
                  <td colSpan="6">
                    <div className={styles.fieldWarning}>
                      <AlertTriangle className={styles.warningIcon} aria-hidden="true" />
                      <span>
                        Possible extraction mismatch — The extracted Account Number appears to
                        contain an IBAN-format value. Please verify against the source document.
                      </span>
                    </div>
                  </td>
                </tr>
              )}

              {/* Correction editor */}
              {isCorrecting && (
                <tr className={styles.correctionRow}>
                  <td colSpan="6" data-label="Correction">
                    <div className={styles.correctionEditor}>
                      <div className={styles.correctionHeader}>
                        <span className={styles.correctionTitle}>
                          Correct: {fieldLabel}
                        </span>
                      </div>
                      <div className={styles.correctionValues}>
                        <div className={styles.valueBlock}>
                          <span className={styles.valueLabel}>Original extracted value</span>
                          <code className={styles.valueOriginal}>
                            {field.extracted_value || '—'}
                          </code>
                        </div>
                        {field.normalized_value && field.normalized_value !== field.extracted_value && (
                          <div className={styles.valueBlock}>
                            <span className={styles.valueLabel}>Normalized value</span>
                            <code className={styles.valueNormalized}>
                              {field.normalized_value}
                            </code>
                          </div>
                        )}
                      </div>
                      <div className={styles.correctionInputs}>
                        <label className={styles.inputWrap}>
                          <span className={styles.inputLabel}>Corrected value</span>
                          <input
                            type="text"
                            className={styles.input}
                            value={correction.corrected_value ?? ''}
                            onChange={(event) =>
                              updateCorrection(field.document_id, field.field_name, {
                                corrected_value: event.target.value,
                              })
                            }
                          />
                        </label>
                        <label className={styles.inputWrap}>
                          <span className={styles.inputLabel}>Reason (optional)</span>
                          <input
                            type="text"
                            className={styles.input}
                            value={correction.reason ?? ''}
                            onChange={(event) =>
                              updateCorrection(field.document_id, field.field_name, {
                                reason: event.target.value,
                              })
                            }
                          />
                        </label>
                      </div>
                    </div>
                  </td>
                </tr>
              )}
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}

export default ReviewFields;

import { useState } from 'react';

import { ChevronDown, ChevronRight, FileText } from 'lucide-react';

import StatusChip from '../../common/StatusChip/StatusChip';
import { getDocumentStatus, getRuleResultStatus } from '../../../data/statuses';
import { formatDateTime } from '../../../utils/format';
import styles from './ReviewDocuments.module.css';

/**
 * Documents section for the Human Review page.
 *
 * Shows document completeness summary, required documents table, and
 * uploaded documents grouped by type with expand/collapse for copies.
 *
 * @param {object} props
 * @param {object} props.viewModel Derived semantic state.
 * @param {object[]} props.uploadedDocuments Raw document list from reviewScreen.
 */
function ReviewDocuments({ viewModel, uploadedDocuments }) {
  const { documents, completeness } = viewModel;

  const requiredDocs = completeness?.required_documents ?? [];
  const presentCount = requiredDocs.filter((r) => r.is_present).length;
  const totalCount = requiredDocs.length;
  const missingDocs = documents.filter((d) => d.status === 'missing');
  const duplicateDocs = documents.filter((d) => d.status === 'duplicate');

  // Separate bulk upload from individual documents
  const bulkUploads = (uploadedDocuments ?? []).filter(
    (d) => d.document_type === 'BULK_UPLOAD'
  );
  const individualDocs = (uploadedDocuments ?? []).filter(
    (d) => d.document_type !== 'BULK_UPLOAD'
  );

  return (
    <div className={styles.container}>
      {/* Completeness summary */}
      <div className={styles.completenessSummary}>
        <span className={styles.completenessText}>
          <strong>{presentCount}</strong> / {totalCount} Required Documents Present
        </span>
        {(missingDocs.length > 0 || duplicateDocs.length > 0) && (
          <span className={styles.completenessDetail}>
            {missingDocs.length > 0 && `${missingDocs.length} Missing`}
            {missingDocs.length > 0 && duplicateDocs.length > 0 && ' · '}
            {duplicateDocs.length > 0 && `${duplicateDocs.length} Duplicate`}
          </span>
        )}
      </div>

      {/* Required documents table */}
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">Document</th>
            <th scope="col">Status</th>
            <th scope="col">Copies</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => (
            <tr key={doc.type} className={styles[doc.status]}>
              <td data-label="Document" className={styles.docLabel}>
                {doc.label}
              </td>
              <td data-label="Status">
                {doc.status === 'present' && (
                  <StatusChip label="Present" variant="success" />
                )}
                {doc.status === 'missing' && (
                  <StatusChip label="Missing" variant="neutral" />
                )}
                {doc.status === 'duplicate' && (
                  <StatusChip label="Duplicate" variant="warning" />
                )}
              </td>
              <td data-label="Copies" className={styles.mutedCell}>
                {doc.status === 'missing' ? (
                  '—'
                ) : (
                  <span>
                    {doc.copyCount}
                    {doc.requiredCopies !== doc.copyCount && (
                      <span className={styles.requiredNote}>
                        {' '}/ {doc.requiredCopies} required
                      </span>
                    )}
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Uploaded documents grouped by type */}
      {documents.filter((d) => d.status !== 'missing').length > 0 && (
        <div className={styles.uploadedSection}>
          <h4 className={styles.uploadedTitle}>Uploaded Documents</h4>
          <div className={styles.documentGroups}>
            {documents
              .filter((d) => d.status !== 'missing')
              .map((docGroup) => (
                <DocumentGroup
                  key={docGroup.type}
                  docGroup={docGroup}
                  uploadedDocs={individualDocs.filter(
                    (d) => d.document_type === docGroup.type
                  )}
                />
              ))}
          </div>
        </div>
      )}

      {/* Bulk upload (separate, not counted as required) */}
      {bulkUploads.length > 0 && (
        <div className={styles.bulkSection}>
          <h4 className={styles.uploadedTitle}>Original Upload</h4>
          {bulkUploads.map((doc) => (
            <div key={doc.document_id} className={styles.bulkItem}>
              <FileText className={styles.bulkIcon} aria-hidden="true" />
              <div className={styles.bulkInfo}>
                <span className={styles.bulkFilename}>{doc.original_filename}</span>
                <span className={styles.bulkMeta}>
                  Processing: {getDocumentStatus(doc.processing_status).label}
                  {' · '}
                  {doc.ocr_confidence != null
                    ? `${Math.round(doc.ocr_confidence * 100)}% confidence`
                    : 'No confidence data'}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Expandable document group showing copies.
 */
function DocumentGroup({ docGroup, uploadedDocs }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={styles.docGroup}>
      <button
        type="button"
        className={styles.docGroupHeader}
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        {expanded ? (
          <ChevronDown className={styles.chevron} aria-hidden="true" />
        ) : (
          <ChevronRight className={styles.chevron} aria-hidden="true" />
        )}
        <span className={styles.docGroupLabel}>{docGroup.label}</span>
        <StatusChip
          label={docGroup.status === 'duplicate' ? 'Duplicate' : 'Present'}
          variant={docGroup.status === 'duplicate' ? 'warning' : 'success'}
        />
        <span className={styles.docGroupCount}>
          {docGroup.copyCount} copy{docGroup.copyCount !== 1 ? 'ies' : ''}
        </span>
      </button>

      {expanded && (
        <div className={styles.docGroupBody}>
          {uploadedDocs.map((doc, index) => {
            const processing = getDocumentStatus(doc.processing_status);
            const ocr = getRuleResultStatus(doc.ocr_status);
            return (
              <div key={doc.document_id} className={styles.copyRow}>
                <span className={styles.copyLabel}>
                  Copy {index + 1} — {doc.original_filename}
                </span>
                <div className={styles.copyDetails}>
                  <StatusChip label={processing.label} variant={processing.variant} />
                  <span className={styles.mutedCell}>
                    OCR: {ocr.label}
                  </span>
                  <span className={styles.mutedCell}>
                    {doc.ocr_confidence != null
                      ? `${Math.round(doc.ocr_confidence * 100)}%`
                      : '—'}
                  </span>
                  <span className={styles.mutedCell}>
                    {formatDateTime(doc.uploaded_at)}
                  </span>
                </div>
                {doc.ocr_text_preview && (
                  <details className={styles.preview}>
                    <summary>View OCR text preview</summary>
                    <p className={styles.previewText}>{doc.ocr_text_preview}</p>
                  </details>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default ReviewDocuments;

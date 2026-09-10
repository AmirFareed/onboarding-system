import { useState } from 'react';

import StatusChip from '../../common/StatusChip/StatusChip';
import { getDocumentStatus, getRuleResultStatus } from '../../../data/statuses';
import styles from './ReportGroupedDocuments.module.css';

/**
 * Derive a StatusChip variant from a raw processing/extraction status.
 */
function getStatusInfo(rawStatus) {
  if (!rawStatus || rawStatus === 'NOT_ANALYZED' || rawStatus === 'NOT_VALIDATED') {
    return { label: 'Not processed', variant: 'neutral' };
  }
  const mapped = getDocumentStatus(rawStatus);
  if (mapped) return mapped;
  return getRuleResultStatus(rawStatus);
}

/**
 * Single document card within the grouped list.
 */
function DocumentCard({ doc }) {
  const [expanded, setExpanded] = useState(false);

  const statusConfig =
    doc.status === 'present'
      ? { icon: '\u2713', variant: 'success', text: `Present \u00B7 ${doc.copyCount} copy${doc.copyCount !== 1 ? 's' : ''}` }
      : doc.status === 'duplicate'
        ? { icon: '\u26A0', variant: 'warning', text: `${doc.copyCount} copies \u00B7 Expected ${doc.requiredCopies}` }
        : { icon: '\u2715', variant: 'danger', text: 'Missing' };

  return (
    <div className={`${styles.card} ${styles[doc.status] ?? ''}`}>
      <div className={styles.cardHeader}>
        <span className={styles.docLabel}>{doc.label}</span>
        <StatusChip
          label={statusConfig.text}
          variant={statusConfig.variant}
          icon={statusConfig.icon}
        />
      </div>

      {doc.status === 'missing' && (
        <p className={styles.dependentNote}>
          Dependent checks cannot be performed until this document is provided.
        </p>
      )}

      {doc.copies.length === 1 && doc.status !== 'missing' && (
        <div className={styles.singleCopy}>
          <CopyDetail label="Processing" status={doc.copies[0].processing} />
          <CopyDetail label="Quality" status={doc.copies[0].quality} />
          <CopyDetail label="Extraction" status={doc.copies[0].extraction} />
        </div>
      )}

      {doc.copies.length > 1 && (
        <>
          <button
            type="button"
            className={styles.expandBtn}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? 'Hide copies' : `View ${doc.copies.length} copies`}
          </button>

          {expanded && (
            <ul className={styles.copyList}>
              {doc.copies.map((copy, index) => (
                <li key={copy.documentId ?? index} className={styles.copyItem}>
                  <span className={styles.copyLabel}>Copy {index + 1}</span>
                  <div className={styles.copyStatuses}>
                    <CopyDetail label="Processing" status={copy.processing} />
                    <CopyDetail label="Extraction" status={copy.extraction} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

/**
 * Inline status detail for a single copy.
 */
function CopyDetail({ label, status }) {
  const info = getStatusInfo(status);
  return (
    <span className={styles.copyDetail}>
      {label}: <StatusChip label={info.label} variant={info.variant} />
    </span>
  );
}

/**
 * Grouped document cards for the validation report.
 *
 * Documents are grouped by their required type. Copies are nested under the
 * parent type. Missing documents show a note about dependent checks.
 *
 * @param {object} props
 * @param {object[]} props.documents Grouped document items from the view model.
 */
function ReportGroupedDocuments({ documents }) {
  if (!documents || documents.length === 0) {
    return (
      <p className={styles.empty}>No documents were included in this report.</p>
    );
  }

  return (
    <div className={styles.list}>
      {documents.map((doc) => (
        <DocumentCard key={doc.type} doc={doc} />
      ))}
    </div>
  );
}

export default ReportGroupedDocuments;

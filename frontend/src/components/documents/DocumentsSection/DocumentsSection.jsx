import { Link } from 'react-router-dom';

import { Download, FileText, UploadCloud } from 'lucide-react';

import EmptyState from '../../common/EmptyState/EmptyState';
import ErrorState from '../../common/ErrorState/ErrorState';
import Spinner from '../../common/Spinner/Spinner';
import StatusChip from '../../common/StatusChip/StatusChip';
import { useAuth } from '../../../hooks/useAuth';
import { REQUIRED_DOCUMENT_TYPES, getDocumentTypeConfig } from '../../../data/documents';
import { getDocumentStatus } from '../../../data/statuses';
import { canUploadDocuments } from '../../../utils/permissions';
import { getDocumentDownloadUrl } from '../../../services/documents';
import { useDocuments } from '../../../hooks/useDocuments';
import styles from './DocumentsSection.module.css';

/**
 * Resolve the display label for one uploaded copy.
 *
 * Composite topics (e.g. CNIC front/back) show their slot label ("Front",
 * "Back"); multi-copy types show a numbered slot ("Copy 1", "Copy 2", ...).
 *
 * @param {object} entry Catalogue entry for the document type.
 * @param {object} document Uploaded document metadata.
 * @returns {string} Human-readable copy label.
 */
function copyLabel(entry, document) {
  const slotIndex = entry.slotTypes?.indexOf(document.document_type) ?? -1;
  if (entry.slotLabels && slotIndex >= 0) {
    return entry.slotLabels[slotIndex];
  }
  return `Copy ${document.copy_number ?? 1}`;
}

/**
 * Group uploaded documents by catalogue type, preserving catalogue order and
 * copy order within each group.
 *
 * @param {Array<object>} documents Uploaded document metadata.
 * @returns {Array<{entry: object, items: Array<object>}>}
 */
function groupDocuments(documents) {
  return REQUIRED_DOCUMENT_TYPES.map((entry) => ({
    entry,
    items: documents
      .filter((document) => {
        const config = getDocumentTypeConfig(document.document_type);
        return (
          config.type === document.document_type ||
          config.slotTypes?.includes(document.document_type)
        ) && config.type === entry.type;
      })
      .sort((a, b) => (a.copy_number ?? 1) - (b.copy_number ?? 1)),
  })).filter((group) => group.items.length > 0);
}

/**
 * Read-only documents section for the application details page.
 *
 * Loads the uploaded documents for the application and lists them grouped by
 * document type — one heading per type with each copy as a numbered row (e.g.
 * "Schedule of Charges Agreement (Sub-Biller)" once, then Copy 1 … Copy 6).
 * Never invents rows: it shows a loading state, a fixed error message with
 * retry, or a genuine empty state.
 *
 * @param {object} props
 * @param {number|string} props.applicationId Application id.
 */
function DocumentsSection({ applicationId }) {
  const { user } = useAuth();
  const { documents, loading, error, reload } = useDocuments(applicationId);
  const groups = groupDocuments(documents);

  return (
    <section className={styles.section} aria-label="Documents">
      <div className={styles.header}>
        <div className={styles.iconWrap} aria-hidden="true">
          <FileText />
        </div>
        <div>
          <h3 className={styles.title}>Documents</h3>
          <p className={styles.subtitle}>Uploaded files for this application.</p>
        </div>
      </div>

      {loading ? (
        <div className={styles.center} aria-busy="true">
          <Spinner size="medium" />
        </div>
      ) : error ? (
        <ErrorState message="Unable to load documents." onRetry={reload} />
      ) : groups.length === 0 ? (
        <EmptyState
          title={documents.length === 0 ? 'No documents uploaded yet' : 'No required documents found'}
          message={
            documents.length === 0
              ? 'Upload the required financial documents to begin verification.'
              : 'Uploaded files are still being processed or are not yet assigned to a required document type.'
          }
          action={
            documents.length === 0 && canUploadDocuments(user) ? (
              <Link to={`/applications/${applicationId}/upload`} className={styles.uploadLink}>
                <UploadCloud aria-hidden="true" />
                Upload Documents
              </Link>
            ) : undefined
          }
        />
      ) : (
        <div className={styles.groups}>
          {groups.map(({ entry, items }) => (
            <section key={entry.type} className={styles.group}>
              <h4 className={styles.groupTitle}>{entry.label}</h4>
              <ul className={styles.list}>
                {items.map((document) => {
                  const status = getDocumentStatus(document.processing_status);
                  return (
                    <li className={styles.row} key={document.id}>
                      <div className={styles.rowIcon} aria-hidden="true">
                        <FileText />
                      </div>
                      <div className={styles.meta}>
                        <span className={styles.name}>{copyLabel(entry, document)}</span>
                        <span className={styles.filename}>{document.original_filename}</span>
                      </div>
                      <StatusChip label={status.label} variant={status.variant} />
                      <a
                        className={styles.download}
                        href={getDocumentDownloadUrl(document.application_id, document.id)}
                        aria-label={`Download ${document.original_filename}`}
                      >
                        <Download aria-hidden="true" />
                        Download
                      </a>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      )}
    </section>
  );
}

export default DocumentsSection;

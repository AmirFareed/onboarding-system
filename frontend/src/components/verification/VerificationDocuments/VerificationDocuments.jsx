import { Search } from 'lucide-react';

import { getDocumentTypeConfig } from '../../../data/documents';
import { formatDateTime } from '../../../utils/format';
import VerificationStatusBadge from '../VerificationStatusBadge/VerificationStatusBadge';
import styles from './VerificationDocuments.module.css';

const STATUS_FILTERS = [
  { value: '', label: 'All statuses' },
  { value: 'VERIFIED', label: 'Verified' },
  { value: 'REVIEW_REQUIRED', label: 'Review Required' },
  { value: 'FAILED', label: 'Failed' },
  { value: 'PENDING', label: 'Pending' },
];

/**
 * Searchable, filterable document list for the verification workspace.
 *
 * Each row shows the document type, its verification status, how many issues
 * affect it and when it was uploaded. On desktop the list renders as a table;
 * on mobile each row collapses into a card with `data-label` attributes.
 * Selecting a row opens the document detail panel.
 *
 * @param {object} props
 * @param {object[]} props.documents Documents enriched with verification status.
 * @param {string} props.searchTerm Current search text.
 * @param {Function} props.onSearchChange Search handler.
 * @param {string} props.statusFilter Current status filter.
 * @param {Function} props.onStatusChange Status filter handler.
 * @param {number|null} props.selectedId Currently open document id.
 * @param {Function} props.onSelect Select handler.
 */
function VerificationDocuments({
  documents,
  searchTerm,
  onSearchChange,
  statusFilter,
  onStatusChange,
  selectedId,
  onSelect,
}) {
  const hasRows = documents.length > 0;

  return (
    <section className={styles.section} aria-label="Documents">
      <div className={styles.toolbar}>
        <h3 className={styles.title}>Documents</h3>
        <div className={styles.controls}>
          <label className={styles.searchWrap}>
            <Search className={styles.searchIcon} aria-hidden="true" />
            <span className={styles.srOnly}>Search documents</span>
            <input
              type="search"
              value={searchTerm}
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder="Search by type or file name"
              className={styles.search}
            />
          </label>
          <label className={styles.filterWrap}>
            <span className={styles.srOnly}>Filter by status</span>
            <select
              value={statusFilter}
              onChange={(event) => onStatusChange(event.target.value)}
              className={styles.filter}
            >
              {STATUS_FILTERS.map(({ value, label }) => (
                <option key={value || 'all'} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {!hasRows ? (
        <p className={styles.empty}>No documents match the current filters.</p>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">Document</th>
              <th scope="col">Status</th>
              <th scope="col">Issues</th>
              <th scope="col">Uploaded</th>
              <th scope="col">
                <span className={styles.srOnly}>Open</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {documents.map((document) => {
              const config = getDocumentTypeConfig(document.document_type);
              const isSelected = document.id === selectedId;
              return (
                <tr
                  key={document.id}
                  className={`${styles.row} ${isSelected ? styles.rowSelected : ''}`}
                  onClick={() => onSelect(document.id)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      onSelect(document.id);
                    }
                  }}
                  tabIndex={0}
                  role="button"
                  aria-pressed={isSelected}
                  aria-label={`Open ${config.label} details`}
                >
                  <td data-label="Document" className={styles.typeCell}>
                    <span className={styles.typeLabel}>{config.label}</span>
                  </td>
                  <td data-label="Status">
                    <VerificationStatusBadge status={document.verification_status} />
                  </td>
                  <td data-label="Issues" className={styles.issueCell}>
                    {document.issue_count > 0 ? (
                      <span className={styles.issueCount}>{document.issue_count}</span>
                    ) : (
                      <span className={styles.noIssues}>None</span>
                    )}
                  </td>
                  <td data-label="Uploaded" className={styles.dateCell}>
                    {formatDateTime(document.uploaded_at ?? document.created_at)}
                  </td>
                  <td className={styles.chevronCell}>
                    <span className={styles.chevron} aria-hidden="true">
                      ›
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}

export default VerificationDocuments;

import { Download, FileText, X } from 'lucide-react';

import { getDocumentTypeConfig } from '../../../data/documents';
import { getDocumentDownloadUrl } from '../../../services/documents';
import VerificationStatusBadge from '../VerificationStatusBadge/VerificationStatusBadge';
import styles from './DocumentDetailPanel.module.css';

function RequirementRow({ rule }) {
  return (
    <li className={styles.requirement}>
      <div className={styles.requirementHeader}>
        <span className={styles.requirementName}>{rule.rule_name}</span>
        <VerificationStatusBadge status={rule.status} />
      </div>
      {rule.message && <p className={styles.requirementMessage}>{rule.message}</p>}
    </li>
  );
}

/**
 * Per-document verification detail panel.
 *
 * Shows every business requirement (rule outcome) that touches the selected
 * document, each with an employee-facing status, plus a download action. No
 * rule ids, confidence scores or other internal metadata are rendered. When
 * the workspace is refreshed, the backend stream endpoint is the only document
 * access used; preview stays a placeholder for a future inline-viewer API.
 *
 * @param {object} props
 * @param {object} props.document The selected document (with derived rules).
 * @param {Function} props.onClose Close handler.
 */
function DocumentDetailPanel({ document, onClose }) {
  const config = getDocumentTypeConfig(document.document_type);
  const requirements = document.rules ?? [];

  return (
    <section className={styles.panel} aria-label={`${config.label} verification details`}>
      <div className={styles.header}>
        <div className={styles.heading}>
          <div className={styles.iconWrap} aria-hidden="true">
            <FileText />
          </div>
          <div>
            <h3 className={styles.title}>{config.label}</h3>
            <p className={styles.subtitle}>{document.original_filename}</p>
          </div>
        </div>
        <div className={styles.headerActions}>
          <span className={styles.statusWrap}>
            <VerificationStatusBadge status={document.verification_status} />
          </span>
          <a
            href={getDocumentDownloadUrl(document.application_id, document.id)}
            className={styles.download}
            aria-label={`Download ${config.label}`}
          >
            <Download aria-hidden="true" />
            View Document
          </a>
          <button
            type="button"
            className={styles.close}
            onClick={onClose}
            aria-label="Close document details"
          >
            <X aria-hidden="true" />
          </button>
        </div>
      </div>

      {requirements.length === 0 ? (
        <p className={styles.empty}>
          No verification requirements have been checked for this document yet.
        </p>
      ) : (
        <ul className={styles.requirements}>
          {requirements.map((rule, index) => (
            <RequirementRow key={`${rule.rule_name}-${index}`} rule={rule} />
          ))}
        </ul>
      )}
    </section>
  );
}

export default DocumentDetailPanel;

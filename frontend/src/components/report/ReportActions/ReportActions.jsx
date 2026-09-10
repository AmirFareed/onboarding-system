import { Link } from 'react-router-dom';

import styles from './ReportActions.module.css';

/**
 * Review actions for the validation report.
 *
 * Shows blocking issues and available actions based on the application state.
 *
 * @param {object} props
 * @param {number} props.applicationId The application ID.
 * @param {boolean} props.canApprove Whether approval is currently allowed.
 * @param {boolean} props.canRequestDocuments Whether document request action is available.
 * @param {object} props.viewModel The view model for deriving blocking issues.
 */
function ReportActions({ applicationId, canApprove, canRequestDocuments, viewModel }) {
  const missingCount = viewModel?.completeness?.missing_documents?.length ?? 0;
  const failureCount = viewModel?.summary?.actualFailures ?? 0;
  const pendingCount = viewModel?.summary?.pending ?? 0;
  const hasBlockingIssues = !canApprove;

  // Check if AMC is present (not missing)
  const amcPresent = viewModel?.completeness?.required_documents?.some(
    (doc) => doc.document_type === 'ACCOUNT_MAINTENANCE_CERTIFICATE' && doc.is_present
  );

  return (
    <div className={styles.wrap}>
      {hasBlockingIssues && (
        <div className={styles.blockingSection}>
          <span className={styles.blockingTitle}>Blocking Issues</span>
          <ul className={styles.blockingList}>
            {missingCount > 0 && (
              <li className={styles.blockingItem}>
                {missingCount} required document{missingCount !== 1 ? 's' : ''} missing
              </li>
            )}
            {failureCount > 0 && (
              <li className={styles.blockingItem}>
                {failureCount} validation failure{failureCount !== 1 ? 's' : ''} requires review
              </li>
            )}
            {pendingCount > 0 && (
              <li className={styles.blockingItem}>
                {pendingCount} check{pendingCount !== 1 ? 's' : ''} pending
              </li>
            )}
          </ul>
        </div>
      )}

      {amcPresent && (
        <div className={styles.manualVerificationSection}>
          <span className={styles.manualVerificationTitle}>Manual Verification Required</span>
          <div className={styles.manualVerificationItem}>
            <span className={styles.manualVerificationIcon}>⚠</span>
            <span className={styles.manualVerificationLabel}>
              Account Maintenance Certificate Originality
            </span>
          </div>
          <p className={styles.manualVerificationNote}>
            The system cannot automatically verify document originality. Please review the Account
            Maintenance Certificate during Human Review.
          </p>
        </div>
      )}

      <div className={styles.actions}>
        {canRequestDocuments && (
          <Link
            to={`/validation?application=${applicationId}`}
            className={styles.secondaryBtn}
          >
            Request Missing Documents
          </Link>
        )}
        <Link
          to={`/human-review?application=${applicationId}`}
          className={styles.primaryBtn}
        >
          Correct
        </Link>
      </div>

      {!canApprove && (
        <p className={styles.blockedNote}>
          Approval unavailable until all blocking issues are resolved.
        </p>
      )}
    </div>
  );
}

export default ReportActions;

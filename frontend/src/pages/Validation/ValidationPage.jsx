import { RefreshCw } from 'lucide-react';

import EmptyState from '../../components/common/EmptyState/EmptyState';
import ErrorState from '../../components/common/ErrorState/ErrorState';
import Spinner from '../../components/common/Spinner/Spinner';
import { useToast } from '../../components/common/Toast/ToastContext';
import ValidationQueueDetailPanel from '../../components/validationQueue/ValidationQueueDetailPanel/ValidationQueueDetailPanel';
import ValidationQueueSummary from '../../components/validationQueue/ValidationQueueSummary/ValidationQueueSummary';
import ValidationQueueTable from '../../components/validationQueue/ValidationQueueTable/ValidationQueueTable';
import { useAuth } from '../../hooks/useAuth';
import { useValidationQueue } from '../../hooks/useValidationQueue';
import { isEmployee, isOperator } from '../../utils/roles';
import styles from './ValidationPage.module.css';

/**
 * Operator validation workflow.
 *
 * The queue lists every application with its business-level completeness state
 * (status, document counts, missing documents, last workflow event) and lets an
 * operator request missing documents, reject an incomplete application or
 * submit a complete one for processing. Non-operators can view the queue and
 * history but not run actions; the backend 403 remains the authoritative gate.
 * Every action refetches the backend state so the UI reflects the stored
 * result, not local state.
 */
function ValidationPage() {
  const { user } = useAuth();
  const toast = useToast();
  const {
    applications,
    total,
    loading,
    error,
    selectedId,
    onSelect,
    selectedApplication,
    history,
    historyLoading,
    historyError,
    actionLoading,
    actionError,
    onRequestDocuments,
    onReject,
    onSubmit,
    onRefresh,
  } = useValidationQueue();

  const canOperate = isOperator(user) || isEmployee(user);

  const handleRequestDocuments = async (payload) => {
    const result = await onRequestDocuments(payload);
    if (result) {
      toast.success('Document request sent to the applicant.');
    }
  };

  const handleReject = async (payload) => {
    const result = await onReject(payload);
    if (result) {
      toast.success('Application rejected.');
    }
  };

  const handleSubmit = async () => {
    const result = await onSubmit();
    if (result) {
      toast.success('Application submitted for processing.');
    }
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h2 className={styles.title}>Validation</h2>
        <p className={styles.subtitle}>
          Review incoming applications, request missing documents and confirm which applications
          are ready for processing.
        </p>
      </header>

      <div className={styles.toolbar}>
        <p className={styles.count} aria-live="polite">
          {total} {total === 1 ? 'application' : 'applications'}
        </p>
        <button type="button" className={styles.secondaryBtn} onClick={onRefresh}>
          <RefreshCw aria-hidden="true" />
          Refresh
        </button>
      </div>

      {loading ? (
        <div className={styles.loadingWrap} aria-busy="true">
          <Spinner size="medium" />
          <p className={styles.loadingText}>Loading validation queue…</p>
        </div>
      ) : error ? (
        <ErrorState message={error} onRetry={onRefresh} />
      ) : applications.length === 0 ? (
        <EmptyState
          title="No applications to validate"
          message="Newly uploaded applications appear here for completeness review."
        />
      ) : (
        <>
          <ValidationQueueSummary applications={applications} />
          <ValidationQueueTable
            applications={applications}
            selectedId={selectedId}
            onSelect={onSelect}
          />
        </>
      )}

      {selectedApplication != null && (
        <ValidationQueueDetailPanel
          application={selectedApplication}
          history={history}
          historyLoading={historyLoading}
          historyError={historyError}
          canOperate={canOperate}
          actionLoading={actionLoading}
          actionError={actionError}
          onRequestDocuments={handleRequestDocuments}
          onReject={handleReject}
          onSubmit={handleSubmit}
        />
      )}
    </div>
  );
}

export default ValidationPage;
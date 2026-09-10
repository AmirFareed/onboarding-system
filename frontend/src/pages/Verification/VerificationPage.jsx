import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { ArrowLeft, RefreshCw } from 'lucide-react';

import ApplicationStatusBadge from '../../components/applications/ApplicationStatusBadge/ApplicationStatusBadge';
import ErrorState from '../../components/common/ErrorState/ErrorState';
import EmptyState from '../../components/common/EmptyState/EmptyState';
import CrossDocumentPanel from '../../components/verification/CrossDocumentPanel/CrossDocumentPanel';
import DocumentDetailPanel from '../../components/verification/DocumentDetailPanel/DocumentDetailPanel';
import IssueList from '../../components/verification/IssueList/IssueList';
import VerificationDocuments from '../../components/verification/VerificationDocuments/VerificationDocuments';
import VerificationStatusBadge from '../../components/verification/VerificationStatusBadge/VerificationStatusBadge';
import VerificationSummary from '../../components/verification/VerificationSummary/VerificationSummary';
import { useApplication } from '../../hooks/useApplication';
import { useAuth } from '../../hooks/useAuth';
import { useVerification } from '../../hooks/useVerification';
import { canUploadDocuments } from '../../utils/permissions';
import { formatDateTime } from '../../utils/format';
import styles from './VerificationPage.module.css';

/**
 * Skeleton shown while the verification workspace loads.
 */
function VerificationSkeleton() {
  return (
    <div aria-hidden="true">
      <div className={styles.skeletonHeader} />
      <div className={styles.skeletonGrid}>
        {Array.from({ length: 5 }, (_, index) => (
          <div className={styles.skeletonCard} key={index} />
        ))}
      </div>
      <div className={styles.skeletonTable} />
    </div>
  );
}

/**
 * Document verification workspace for an application.
 *
 * A business-level review screen built from the stored validation results, the
 * completeness report and the document list. It shows an overall summary,
 * a searchable document list with per-document requirements, a cross-document
 * consistency panel and a severity-grouped issue list. Internal rule ids,
 * confidence scores and other technical pipeline metadata are never rendered.
 */
function VerificationPage() {
  const { applicationId } = useParams();
  const { user } = useAuth();
  const { application, loading: appLoading, error: appError, reload: reloadApp } =
    useApplication(applicationId);
  const {
    loading,
    error,
    reload,
    documents,
    documentsWithStatus,
    overallStatus,
    summary,
    issues,
    crossDocumentRules,
    searchTerm,
    statusFilter,
    onSearchChange,
    onStatusChange,
  } = useVerification(applicationId);

  const [selectedId, setSelectedId] = useState(null);

  const selectedDocument = documentsWithStatus.find((document) => document.id === selectedId) ?? null;

  const handleRefresh = () => {
    reload();
    reloadApp();
  };

  const isLoading = appLoading || loading;

  if (isLoading) {
    return (
      <div className={styles.page} aria-busy="true">
        <VerificationSkeleton />
      </div>
    );
  }

  if (appError || !application) {
    return (
      <div className={styles.page}>
        <ErrorState message={appError ?? 'Application not found.'} onRetry={reloadApp} />
      </div>
    );
  }

  const noVerificationData =
    documentsWithStatus.length === 0 && issues.total === 0;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headingRow}>
          <h2 className={styles.title}>Verification — Application #{application.id}</h2>
          <VerificationStatusBadge status={overallStatus} />
        </div>
        <p className={styles.subtitle}>
          {application.notes
            ? application.notes
            : 'Document verification workspace for this application.'}
        </p>
        <div className={styles.meta}>
          <span>
            Last updated {formatDateTime(application.updated_at)}
          </span>
          <span>Submitted by {application.created_by}</span>
          <ApplicationStatusBadge status={application.status} />
        </div>
      </header>

      <div className={styles.actions}>
        <button type="button" className={styles.refreshBtn} onClick={handleRefresh}>
          <RefreshCw aria-hidden="true" />
          Refresh
        </button>
        <Link to={`/applications/${application.id}`} className={styles.secondaryBtn}>
          <ArrowLeft aria-hidden="true" />
          Back to Application
        </Link>
      </div>

      {error ? (
        <ErrorState message="Unable to load verification data. Please try again." onRetry={reload} />
      ) : noVerificationData ? (
        <EmptyState
          title="No verification results yet"
          message="No documents have been verified for this application yet. Run the verification pipeline or upload documents to begin."
          action={
            canUploadDocuments(user) ? (
              <Link to={`/applications/${application.id}/upload`} className={styles.primaryBtn}>
                Upload Documents
              </Link>
            ) : undefined
          }
        />
      ) : (
        <>
          <VerificationSummary summary={summary} />

          <VerificationDocuments
            documents={documents}
            searchTerm={searchTerm}
            onSearchChange={onSearchChange}
            statusFilter={statusFilter}
            onStatusChange={onStatusChange}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />

          {selectedDocument && (
            <DocumentDetailPanel document={selectedDocument} onClose={() => setSelectedId(null)} />
          )}

          <CrossDocumentPanel rules={crossDocumentRules} />

          <IssueList issues={issues} />
        </>
      )}
    </div>
  );
}

export default VerificationPage;

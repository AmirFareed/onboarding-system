import { useEffect } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';

import { ArrowLeft, History, ShieldCheck, UploadCloud } from 'lucide-react';
import ApplicationStatusBadge from '../../components/applications/ApplicationStatusBadge/ApplicationStatusBadge';
import { ApplicationCardSkeleton } from '../../components/applications/ApplicationSkeleton/ApplicationSkeleton';
import DocumentsSection from '../../components/documents/DocumentsSection/DocumentsSection';
import ProcessingProgress from '../../components/processing/ProcessingProgress/ProcessingProgress';
import ErrorState from '../../components/common/ErrorState/ErrorState';
import { useApplication } from '../../hooks/useApplication';
import { useAuth } from '../../hooks/useAuth';
import { useLastOpenedApplication } from '../../hooks/useLastOpenedApplication';
import { canUploadDocuments } from '../../utils/permissions';
import { formatDate, formatDateTime } from '../../utils/format';
import styles from './ApplicationDetailsPage.module.css';

/**
 * Neutral placeholder section for a future module (verification, activity).
 * Renders an empty state only; no fake data is ever shown.
 */
function PlaceholderCard({ icon: Icon, title, message }) {
  return (
    <section className={styles.placeholder} aria-label={title}>
      <div className={styles.placeholderIcon} aria-hidden="true">
        <Icon />
      </div>
      <h3 className={styles.placeholderTitle}>{title}</h3>
      <p className={styles.placeholderMessage}>{message}</p>
    </section>
  );
}

/**
 * Application details page.
 *
 * Shows the application's information in a card: status badge, submission and
 * update dates, creator and notes, with a primary action to upload documents
 * and a secondary action back to the list. Placeholder cards signal where the
 * documents, verification status and activity feeds will live.
 */
function ApplicationDetailsPage() {
  const { applicationId } = useParams();
  const location = useLocation();
  const { user } = useAuth();
  const { application, loading, error, reload } = useApplication(applicationId);
  const { recordOpened } = useLastOpenedApplication();

  useEffect(() => {
    // Arriving via the "Resume Application" chip clears the stored id first, so
    // don't immediately re-record it here or the chip would never disappear.
    if (application && !location.state?.fromResume) {
      recordOpened(application.id);
    }
  }, [application, location.state?.fromResume, recordOpened]);

  if (loading) {
    return (
      <div className={styles.page} aria-busy="true">
        <ApplicationCardSkeleton />
      </div>
    );
  }

  if (error || !application) {
    return (
      <div className={styles.page}>
        <ErrorState message={error ?? 'Application not found.'} onRetry={reload} />
        <Link to="/applications" className={styles.secondaryBtn}>
          <ArrowLeft aria-hidden="true" />
          Back to Applications
        </Link>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headingRow}>
          <h2 className={styles.title}>Application #{application.id}</h2>
          <ApplicationStatusBadge status={application.status} />
        </div>
        <p className={styles.subtitle}>Financial document verification case.</p>
      </header>

      <section className={styles.card} aria-label="Application information">
        <div className={styles.grid}>
          <div className={styles.field}>
            <span className={styles.label}>Application ID</span>
            <span className={styles.value}>#{application.id}</span>
          </div>
          {application.name && (
            <div className={styles.field}>
              <span className={styles.label}>Name</span>
              <span className={styles.value}>{application.name}</span>
            </div>
          )}
          <div className={styles.field}>
            <span className={styles.label}>Submission Date</span>
            <span className={styles.value}>{formatDateTime(application.submitted_at)}</span>
          </div>
          <div className={styles.field}>
            <span className={styles.label}>Last Updated</span>
            <span className={styles.value}>{formatDate(application.updated_at)}</span>
          </div>
          <div className={styles.field}>
            <span className={styles.label}>Created By</span>
            <span className={styles.value}>{application.created_by}</span>
          </div>
          <div className={`${styles.field} ${styles.fieldFull}`}>
            <span className={styles.label}>Notes</span>
            <span className={styles.value}>{application.notes || '\u2014'}</span>
          </div>
        </div>

        <div className={styles.actions}>
          {canUploadDocuments(user) && (
            <Link
              to={`/applications/${application.id}/upload`}
              className={styles.primaryBtn}
            >
              <UploadCloud aria-hidden="true" />
              Upload Documents
            </Link>
          )}
          <Link
            to={`/applications/${application.id}/verification`}
            className={styles.primaryBtn}
          >
            <ShieldCheck aria-hidden="true" />
            Verification
          </Link>
          <Link to="/applications" className={styles.secondaryBtn}>
            <ArrowLeft aria-hidden="true" />
            Back to Applications
          </Link>
        </div>
      </section>

      <DocumentsSection applicationId={application.id} />
      <ProcessingProgress applicationId={application.id} />

      <div className={styles.placeholders}>
        <PlaceholderCard
          icon={History}
          title="Recent Activity"
          message="No activity has been recorded for this application yet."
        />
      </div>
    </div>
  );
}

export default ApplicationDetailsPage;

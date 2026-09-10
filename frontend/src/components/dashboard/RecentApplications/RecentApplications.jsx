import { useEffect, useState } from 'react';
import { ChevronRight, ChevronUp, Plus } from 'lucide-react';
import { Link } from 'react-router-dom';
import ApplicationStatusBadge from '../../applications/ApplicationStatusBadge/ApplicationStatusBadge';
import EmptyState from '../../common/EmptyState/EmptyState';
import ErrorState from '../../common/ErrorState/ErrorState';
import StatusChip from '../../common/StatusChip/StatusChip';
import { useApplicationsStore } from '../../../store/ApplicationsContext';
import { useAuth } from '../../../hooks/useAuth';
import { isEmployee, isOperator } from '../../../utils/roles';
import { computeDocumentProgress } from '../../../data/documents';
import { formatDate } from '../../../utils/format';
import styles from './RecentApplications.module.css';

const CHECKLIST_STATUS_VARIANT = {
  complete: 'success',
  incomplete: 'warning',
  missing: 'neutral',
};

const CHECKLIST_STATUS_LABEL = {
  complete: 'Complete',
  incomplete: 'Incomplete',
  missing: 'Missing',
};

function DocumentChecklist({ documents }) {
  const { totalCopies, uploadedCopies, percent, categories } = computeDocumentProgress(documents);

  return (
    <div className={styles.checklist} aria-label="Document upload progress">
      <div className={styles.progressRow}>
        <span className={styles.progressText}>
          {uploadedCopies} / {totalCopies} documents
        </span>
        <span className={styles.progressPercent}>{percent}%</span>
      </div>
      <div
        className={styles.progressTrack}
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className={styles.progressBar} style={{ width: `${percent}%` }} />
      </div>
      <ul className={styles.checklistList}>
        {categories.map((category) => (
          <li key={category.type} className={styles.checklistRow}>
            <span className={styles.checklistLabel}>{category.label}</span>
            <span className={styles.checklistCount}>
              {category.present} / {category.required}
            </span>
            <StatusChip
              label={CHECKLIST_STATUS_LABEL[category.status]}
              variant={CHECKLIST_STATUS_VARIANT[category.status]}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Recent Applications dashboard section.
 *
 * Reads the shared applications store, so it always shows the same records as
 * the Applications page. Displays the five most recently updated applications;
 * a newly created application appears here and on the Applications page from
 * the same store update, without any dashboard-specific dataset. Each row shows
 * the document upload progress for that application and expands to reveal the
 * per-category checklist.
 */
function RecentApplications() {
  const { recentApplications, documentsByApplication, loadDocuments, loading, error, reload } =
    useApplicationsStore();
  const { user } = useAuth();
  const [expandedId, setExpandedId] = useState(null);

  const canCreateApplication = isEmployee(user) || isOperator(user);

  useEffect(() => {
    for (const application of recentApplications) {
      if (!documentsByApplication[application.id]) {
        loadDocuments(application.id);
      }
    }
  }, [recentApplications, documentsByApplication, loadDocuments]);

  return (
    <section className={styles.card} aria-label="Recent applications">
      <div className={styles.header}>
        <h3 className={styles.title}>Recent Applications</h3>
        <Link to="/applications" className={styles.viewAll}>
          View all
        </Link>
      </div>

      {loading ? (
        <ul className={styles.list}>
          {Array.from({ length: 3 }, (_, index) => (
            <li key={index} className={styles.skeletonRow} aria-hidden="true" />
          ))}
        </ul>
      ) : error ? (
        <ErrorState message="Unable to load recent applications." onRetry={reload} />
      ) : recentApplications.length === 0 ? (
        <EmptyState
          title="No applications yet"
          message="Create an application to begin the document verification process."
          action={
            canCreateApplication ? (
              <Link to="/applications/new" className={styles.createBtn}>
                <Plus aria-hidden="true" />
                Create New Application
              </Link>
            ) : undefined
          }
        />
      ) : (
        <ul className={styles.list}>
          {recentApplications.map((application) => {
            const state = documentsByApplication[application.id];
            const isExpanded = expandedId === application.id;
            return (
              <li key={application.id} className={styles.item}>
                <button
                  type="button"
                  className={styles.row}
                  aria-expanded={isExpanded}
                  onClick={() => setExpandedId(isExpanded ? null : application.id)}
                >
                  <span className={styles.id}>#{application.id}</span>
                  <span className={styles.status}>
                    <ApplicationStatusBadge status={application.status} />
                  </span>
                  <span className={styles.meta}>
                    {application.name && (
                      <span className={styles.name}>{application.name}</span>
                    )}
                    <span className={styles.createdBy}>{application.created_by}</span>
                    <span className={styles.updated}>
                      Updated {formatDate(application.updated_at)}
                    </span>
                  </span>
                  {isExpanded ? (
                    <ChevronUp className={styles.chevron} aria-hidden="true" />
                  ) : (
                    <ChevronRight className={styles.chevron} aria-hidden="true" />
                  )}
                </button>
                {isExpanded && <DocumentChecklist documents={state?.items ?? []} />}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export default RecentApplications;

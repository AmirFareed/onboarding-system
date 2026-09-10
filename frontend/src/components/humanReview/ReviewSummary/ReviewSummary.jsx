import { Info } from 'lucide-react';

import ApplicationStatusBadge from '../../applications/ApplicationStatusBadge/ApplicationStatusBadge';
import StatusChip from '../../common/StatusChip/StatusChip';
import { getApplicationStatus, getVerificationStatus } from '../../../data/statuses';
import { formatDateTime } from '../../../utils/format';
import styles from './ReviewSummary.module.css';

/**
 * Application header for the final review.
 *
 * Shows the static application information, the lifecycle status, the
 * validation verdict and data-driven recommendations that guide the
 * reviewer's decision.
 *
 * @param {object} props
 * @param {object} props.viewModel Derived semantic state from useHumanReviewViewModel.
 */
function ReviewSummary({ viewModel }) {
  const { application } = viewModel;

  // Application lifecycle status (PENDING_REVIEW, APPROVED, etc.)
  const lifecycleStatus = getApplicationStatus(application.status);

  // Validation verdict (PASS, FAIL, WARNING, etc.)
  const report = viewModel;
  const validationVerdict = getVerificationStatus(
    report?.report?.overall_status ?? report?.overallStatus
  );

  // Data-driven recommendations (from viewModel, NOT from report.recommendations)
  const recommendations = viewModel.recommendations ?? [];

  return (
    <div className={styles.summary}>
      <div className={styles.top}>
        <div className={styles.identity}>
          <h3 className={styles.name}>Application #{application.application_id}</h3>
          <div className={styles.meta}>
            <ApplicationStatusBadge status={application.status} />
            <span>Submitted {formatDateTime(application.submitted_at)}</span>
            <span>Submitted by {application.created_by}</span>
            <span>Updated {formatDateTime(application.updated_at)}</span>
          </div>
        </div>
        <div className={styles.statuses}>
          <div className={styles.statusRow}>
            <span className={styles.statusLabel}>Application Status</span>
            <StatusChip label={lifecycleStatus.label} variant={lifecycleStatus.variant} />
          </div>
          <div className={styles.statusRow}>
            <span className={styles.statusLabel}>Validation Result</span>
            <StatusChip label={validationVerdict.label} variant={validationVerdict.variant} />
          </div>
        </div>
      </div>

      {recommendations.length > 0 && (
        <div className={styles.recommendations}>
          <div className={styles.recHeader}>
            <Info className={styles.recIcon} aria-hidden="true" />
            <h4 className={styles.recTitle}>Recommendations</h4>
          </div>
          <ul className={styles.recList}>
            {recommendations.map((rec) => (
              <li key={rec.code}>{rec.message}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default ReviewSummary;

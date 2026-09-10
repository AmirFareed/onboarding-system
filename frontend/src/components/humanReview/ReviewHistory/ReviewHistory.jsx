import { History } from 'lucide-react';

import StatusChip from '../../common/StatusChip/StatusChip';
import { formatDateTime } from '../../../utils/format';
import styles from './ReviewHistory.module.css';

function decisionEntry(decision) {
  switch (decision) {
    case 'APPROVE':
      return { label: 'Approved', variant: 'success' };
    case 'CORRECT':
      return { label: 'Corrected', variant: 'neutral' };
    case 'REJECT':
      return { label: 'Rejected', variant: 'danger' };
    default:
      return { label: decision ?? 'Unknown', variant: 'neutral' };
  }
}

/**
 * Stored final reviews for an application.
 *
 * Renders the recorded decision, reviewer, timestamps, comments, rejection
 * reason, checklist completion and any stored field corrections. When an
 * application has already been finally reviewed this is the read-only record
 * shown instead of the decision form.
 *
 * @param {object} props
 * @param {object[]} props.reviews Stored reviews, most recent first.
 */
function ReviewHistory({ reviews }) {
  if (!reviews || reviews.length === 0) {
    return (
      <p className={styles.empty}>
        No final reviews have been recorded for this application.
      </p>
    );
  }

  return (
    <div className={styles.list}>
      {reviews.map((review) => {
        const decision = decisionEntry(review.decision);
        return (
          <article key={review.review_id} className={styles.review}>
            <header className={styles.header}>
              <div className={styles.heading}>
                <History className={styles.icon} aria-hidden="true" />
                <h4 className={styles.title}>Review by {review.reviewer_name}</h4>
                <StatusChip label={decision.label} variant={decision.variant} />
              </div>
              <span className={styles.date}>{formatDateTime(review.reviewed_at)}</span>
            </header>

            <dl className={styles.details}>
              <div className={styles.detailRow}>
                <dt>Checklist</dt>
                <dd>
                  {review.checklist_checked} of {review.checklist_total} items checked
                </dd>
              </div>
              {review.comments && (
                <div className={styles.detailRow}>
                  <dt>Comments</dt>
                  <dd>{review.comments}</dd>
                </div>
              )}
              {review.rejection_reason && (
                <div className={styles.detailRow}>
                  <dt>Rejection reason</dt>
                  <dd>{review.rejection_reason}</dd>
                </div>
              )}
            </dl>

            {review.corrections?.length > 0 && (
              <ul className={styles.corrections}>
                {review.corrections.map((correction) => (
                  <li key={correction.field_name} className={styles.correction}>
                    <span className={styles.correctionField}>{correction.field_name}</span>
                    <span className={styles.correctionValue}>
                      {correction.original_value != null ? (
                        <>
                          {correction.original_value} → <strong>{correction.corrected_value}</strong>
                        </>
                      ) : (
                        <strong>{correction.corrected_value}</strong>
                      )}
                    </span>
                    {correction.reason && (
                      <span className={styles.correctionReason}>{correction.reason}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </article>
        );
      })}
    </div>
  );
}

export default ReviewHistory;
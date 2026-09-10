import { AlertTriangle, Info } from 'lucide-react';

import StatusChip from '../../common/StatusChip/StatusChip';
import styles from './ReportIssues.module.css';

/**
 * Group issues into employee-facing severities.
 *
 * Backend severities and rule statuses map onto Critical / Warning / Review
 * Required vocabulary so the report never surfaces internal enum names.
 */
function groupIssues(issues) {
  const groups = { critical: [], warning: [], review: [] };
  for (const issue of issues) {
    const severity = String(issue.severity ?? '').toUpperCase();
    if (severity === 'ERROR' || issue.status === 'FAIL') {
      groups.critical.push(issue);
    } else if (severity === 'WARNING' || issue.status === 'WARNING') {
      groups.warning.push(issue);
    } else {
      groups.review.push(issue);
    }
  }
  return groups;
}

function IssueGroup({ title, items, variant }) {
  if (items.length === 0) {
    return null;
  }
  return (
    <div className={styles.group}>
      <div className={styles.groupHeader}>
        <h4 className={styles.groupTitle}>{title}</h4>
        <StatusChip label={`${items.length}`} variant={variant} />
      </div>
      <ul className={styles.issueList}>
        {items.map((issue, index) => (
          <li key={`${issue.title}-${index}`} className={styles.issue}>
            <span className={styles.issueTitle}>{issue.title}</span>
            <span className={styles.issueMessage}>{issue.message || '—'}</span>
            {issue.category && (
              <span className={styles.issueCategory}>{issue.category}</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Issues requiring attention plus the report recommendations.
 *
 * @param {object} props
 * @param {object[]} props.issues Failed/pending rules and analysis issues.
 * @param {object[]} props.recommendations Deterministic report recommendations.
 */
function ReportIssues({ issues, recommendations }) {
  const safeIssues = issues ?? [];
  const groups = groupIssues(safeIssues);

  return (
    <div className={styles.wrap}>
      {safeIssues.length === 0 && recommendations.length === 0 ? (
        <p className={styles.empty}>
          No issues requiring attention were found for this application.
        </p>
      ) : (
        <>
          <IssueGroup title="Critical issues" items={groups.critical} variant="danger" />
          <IssueGroup title="Warnings" items={groups.warning} variant="warning" />
          <IssueGroup title="Review required" items={groups.review} variant="neutral" />
        </>
      )}

      {recommendations.length > 0 && (
        <div className={styles.recommendations}>
          <div className={styles.recHeader}>
            <Info className={styles.recIcon} aria-hidden="true" />
            <h4 className={styles.recTitle}>Recommendations</h4>
          </div>
          <ul className={styles.recList}>
            {recommendations.map((rec) => (
              <li key={rec.code} className={styles.recItem}>
                <AlertTriangle className={styles.recBullet} aria-hidden="true" />
                <span>{rec.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default ReportIssues;
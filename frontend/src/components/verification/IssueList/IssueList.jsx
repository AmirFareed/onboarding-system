import { AlertTriangle, CheckCircle2, Flag, Info } from 'lucide-react';

import VerificationStatusBadge from '../VerificationStatusBadge/VerificationStatusBadge';
import styles from './IssueList.module.css';

function IssueGroup({ title, icon: Icon, tone, items }) {
  return (
    <div className={styles.group}>
      <h4 className={`${styles.groupTitle} ${styles[tone]}`}>
        <Icon aria-hidden="true" />
        {title} ({items.length})
      </h4>
      {items.length === 0 ? (
        <p className={styles.groupEmpty}>
          <CheckCircle2 aria-hidden="true" />
          No {title.toLowerCase()} issues.
        </p>
      ) : (
        <ul className={styles.list}>
          {items.map((issue, index) => (
            <li key={`${issue.rule_name}-${index}`} className={styles.item}>
              <div className={styles.itemHeader}>
                <span className={styles.itemName}>{issue.rule_name}</span>
                <VerificationStatusBadge status={issue.status} />
              </div>
              {issue.message && <p className={styles.itemMessage}>{issue.message}</p>}
              {issue.related_document_ids.length > 0 && (
                <div className={styles.documents}>
                  {issue.related_document_ids.map((id) => (
                    <span key={id} className={styles.documentTag}>
                      #{id}
                    </span>
                  ))}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Verification issue list grouped by severity.
 *
 * Backend severities map to employee-facing groups: Critical, Warning and
 * Review Required. Only non-passing rules appear; passed checks are reported
 * in the summary cards instead.
 *
 * @param {object} props
 * @param {object} props.issues Grouped issue lists.
 */
function IssueList({ issues }) {
  return (
    <section className={styles.section} aria-label="Verification issues">
      <div className={styles.sectionHeader}>
        <h3 className={styles.title}>Issues</h3>
        <p className={styles.count}>
          {issues.total} {issues.total === 1 ? 'issue' : 'issues'} requiring attention
        </p>
      </div>

      <IssueGroup
        title="Critical"
        icon={AlertTriangle}
        tone="critical"
        items={issues.critical}
      />
      <IssueGroup title="Warning" icon={Flag} tone="warning" items={issues.warning} />
      <IssueGroup
        title="Review Required"
        icon={Info}
        tone="review"
        items={issues.reviewRequired}
      />
    </section>
  );
}

export default IssueList;

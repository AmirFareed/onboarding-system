import { useState } from 'react';

import { ATTENTION_ICONS } from '../../../data/statuses';
import styles from './ReportAttentionSection.module.css';

/**
 * Individual attention group (failures, missing docs, duplicates, pending).
 */
function AttentionGroup({ group }) {
  const [expanded, setExpanded] = useState(group.type === 'failure');
  const icon = ATTENTION_ICONS[group.type];

  return (
    <div className={styles.group}>
      <button
        type="button"
        className={styles.groupHeader}
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        <span className={styles.groupIcon} aria-hidden="true">
          {icon?.icon ?? ''}
        </span>
        <span className={styles.groupTitle}>
          {group.count} {group.label}
        </span>
        <span className={styles.chevron} aria-hidden="true">
          {expanded ? '\u25B2' : '\u25BC'}
        </span>
      </button>

      {expanded && (
        <ul className={styles.detailList}>
          {group.details.map((item, index) => (
            <li key={`${item.title}-${index}`} className={styles.detailItem}>
              <span className={styles.detailTitle}>{item.title}</span>
              {item.message && (
                <span className={styles.detailMessage}>{item.message}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * "What Requires Attention" section for the validation report.
 *
 * Displays prioritized, deduplicated attention items: actual failures first,
 * then missing documents, duplicates, and pending checks. Each group is
 * expandable; failures are expanded by default.
 *
 * @param {object} props
 * @param {object[]} props.attention Attention items from the view model.
 */
function ReportAttentionSection({ attention }) {
  if (!attention || attention.length === 0) {
    return (
      <p className={styles.empty}>
        No issues requiring attention were found for this application.
      </p>
    );
  }

  return (
    <div className={styles.wrap}>
      {attention.map((group) => (
        <AttentionGroup key={group.type} group={group} />
      ))}
    </div>
  );
}

export default ReportAttentionSection;

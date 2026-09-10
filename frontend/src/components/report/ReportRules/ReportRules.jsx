import { useState } from 'react';

import StatusChip from '../../common/StatusChip/StatusChip';
import { getReportStatus } from '../../../data/statuses';
import styles from './ReportRules.module.css';

/**
 * Fixed display order for status counts within a category header.
 * Only statuses with count > 0 are rendered.
 */
const STATUS_ORDER = ['PASSED', 'FAILED', 'WARNING', 'PENDING', 'NOT_VERIFIABLE'];

/**
 * Single business-rule category with expand/collapse.
 *
 * All categories start collapsed. The entire header is clickable.
 */
function RuleCategory({ group }) {
  const [expanded, setExpanded] = useState(false);

  const orderedStatuses = STATUS_ORDER.filter((key) => {
    const countKey = key === 'PASSED' ? 'passed'
      : key === 'FAILED' ? 'failed'
        : key === 'WARNING' ? 'warnings'
          : key === 'PENDING' ? 'pending'
            : 'notVerifiable';
    return group[countKey] > 0;
  });

  return (
    <section className={styles.category} aria-label={group.label}>
      <button
        type="button"
        className={styles.categoryHeader}
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        aria-controls={`rules-${group.label?.replace(/\s+/g, '-').toLowerCase()}`}
      >
        <span className={styles.categoryTitle}>{group.label}</span>
        <span className={styles.categoryStatusSummary}>
          {orderedStatuses.map((key) => {
            const status = getReportStatus(key);
            const countKey = key === 'PASSED' ? 'passed'
              : key === 'FAILED' ? 'failed'
                : key === 'WARNING' ? 'warnings'
                  : key === 'PENDING' ? 'pending'
                    : 'notVerifiable';
            return (
              <StatusChip
                key={key}
                label={`${group[countKey]} ${status.label}`}
                variant={status.variant}
              />
            );
          })}
        </span>
        <span className={styles.chevron} aria-hidden="true">
          {expanded ? '\u25BC' : '\u203A'}
        </span>
      </button>

      {expanded && (
        <div
          className={styles.categoryBody}
          id={`rules-${group.label?.replace(/\s+/g, '-').toLowerCase()}`}
          role="region"
        >
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Check</th>
                <th scope="col">Result</th>
                <th scope="col">Detail</th>
              </tr>
            </thead>
            <tbody>
              {group.items.map((rule) => {
                const status = getReportStatus(rule.semanticStatus);
                return (
                  <tr key={rule.rule_id ?? rule.rule_name}>
                    <td data-label="Check" className={styles.ruleCell}>
                      {rule.rule_name}
                    </td>
                    <td data-label="Result">
                      <StatusChip
                        label={status.label}
                        variant={status.variant}
                        icon={status.icon}
                      />
                    </td>
                    <td data-label="Detail" className={styles.messageCell}>
                      {rule.semanticStatus === 'NOT_VERIFIABLE'
                        ? rule.notVerifiableReason || 'Required document is missing'
                        : rule.message || '\u2014'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/**
 * Business-rule results grouped by category with accordion behavior.
 *
 * All categories start collapsed. Each can be expanded independently.
 * Status counts are right-aligned and ordered consistently.
 *
 * @param {object} props
 * @param {object[]} props.groups Per-category rule groups from the view model.
 */
function ReportRules({ groups }) {
  if (!groups || groups.length === 0) {
    return (
      <p className={styles.empty}>
        No business-rule results are available for this application.
      </p>
    );
  }

  return (
    <div className={styles.groups}>
      {groups.map((group) => (
        <RuleCategory key={group.label} group={group} />
      ))}
    </div>
  );
}

export default ReportRules;

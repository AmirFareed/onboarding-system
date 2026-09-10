import { ClipboardCheck, FileWarning, FolderClock, Inbox, ShieldX } from 'lucide-react';

import styles from './ValidationQueueSummary.module.css';

const FINALIZED = new Set(['APPROVED', 'CORRECTED']);
const REJECTED = 'REJECTED';

/**
 * Derive the summary counters from a list of queue items.
 *
 * Each application is counted into exactly one bucket, in priority order, so
 * the counters always sum to the total. "Pending" is any application that has
 * not been actioned or finalized; "Missing documents" is one with at least one
 * missing required document; "Needs attention" is one explicitly flagged by
 * the backend; "Rejected" and "Completed" are the finalized outcomes.
 *
 * @param {Array<object>} applications Validation queue items.
 * @returns {Array<{id: string, label: string, count: number, icon: object}>}
 */
export function computeSummaryCounters(applications = []) {
  const counters = [
    { id: 'pending', label: 'Pending', count: 0 },
    { id: 'missing', label: 'Missing documents', count: 0 },
    { id: 'attention', label: 'Needs attention', count: 0 },
    { id: 'rejected', label: 'Rejected', count: 0 },
    { id: 'completed', label: 'Completed', count: 0 },
  ];

  for (const application of applications) {
    if (FINALIZED.has(application.status)) {
      counters[4].count += 1;
    } else if (application.status === REJECTED) {
      counters[3].count += 1;
    } else if (application.needs_attention) {
      counters[2].count += 1;
    } else if (application.missing_document_count > 0) {
      counters[1].count += 1;
    } else {
      counters[0].count += 1;
    }
  }

  return counters;
}

const ICONS = {
  pending: FolderClock,
  missing: Inbox,
  attention: FileWarning,
  rejected: ShieldX,
  completed: ClipboardCheck,
};

/**
 * Summary counter cards for the validation queue.
 *
 * Each card shows one count from the queue (pending, missing documents, needs
 * attention, rejected, completed). Business-facing labels only.
 *
 * @param {object} props
 * @param {Array<object>} props.applications Queue items to summarise.
 */
function ValidationQueueSummary({ applications }) {
  const counters = computeSummaryCounters(applications);

  return (
    <section className={styles.summary} aria-label="Validation queue summary">
      {counters.map(({ id, label, count }) => {
        const Icon = ICONS[id];
        return (
          <div key={id} className={styles.card} aria-label={label}>
            <div className={styles.iconWrap} aria-hidden="true">
              <Icon />
            </div>
            <div className={styles.meta}>
              <span className={styles.count}>{count}</span>
              <span className={styles.label}>{label}</span>
            </div>
          </div>
        );
      })}
    </section>
  );
}

export default ValidationQueueSummary;
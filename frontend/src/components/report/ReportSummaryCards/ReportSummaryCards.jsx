import StatusChip from '../../common/StatusChip/StatusChip';
import { getApplicationStatus, getReportStatus } from '../../../data/statuses';
import styles from './ReportSummaryCards.module.css';

/**
 * Segment of the breakdown bar.
 */
function BreakdownSegment({ label, count, variant, total }) {
  if (count === 0) return null;
  const width = total > 0 ? `${(count / total) * 100}%` : '0%';
  return (
    <div
      className={`${styles.segment} ${styles[`segment_${variant}`] ?? ''}`}
      style={{ width }}
      title={`${label}: ${count}`}
    >
      {count > 0 && <span className={styles.segmentLabel}>{count}</span>}
    </div>
  );
}

/**
 * Headline summary for the redesigned validation report.
 *
 * Three clear layers:
 *   A — High-level outcome (failures, missing, pending, warnings)
 *   B — Document completeness (X / Y with progress bar)
 *   C — Validation checks (labeled breakdown bar with legend)
 *
 * @param {object} props
 * @param {object} props.viewModel The derived view model.
 */
function ReportSummaryCards({ viewModel }) {
  const { summary, overallStatus, applicationStatus, completeness } = viewModel;
  const overall = getReportStatus(overallStatus);
  const appStatus = getApplicationStatus(applicationStatus);

  const missingCount = completeness?.missing_documents?.length ?? 0;
  const presentCount =
    completeness?.required_documents?.filter((d) => d.is_present).length ?? 0;
  const requiredCount = completeness?.required_documents?.length ?? 0;
  const completenessPercentage =
    requiredCount > 0 ? Math.round((presentCount / requiredCount) * 100) : 0;

  return (
    <section className={styles.section} aria-label="Validation summary">
      {/* Dual status — application lifecycle vs validation result */}
      <div className={styles.statusBar}>
        <div className={styles.statusBlock}>
          <span className={styles.statusLabel}>Application Status</span>
          <StatusChip label={appStatus.label} variant={appStatus.variant} />
        </div>
        <div className={styles.statusBlock}>
          <span className={styles.statusLabel}>Validation Result</span>
          <StatusChip label={overall.label} variant={overall.variant} />
        </div>
      </div>

      {/* Layer A — High-level outcome signals */}
      <div className={styles.outcomeGrid}>
        {summary.actualFailures > 0 && (
          <div className={`${styles.outcomeCard} ${styles.outcomeCard_danger}`}>
            <span className={styles.outcomeValue}>{summary.actualFailures}</span>
            <span className={styles.outcomeLabel}>
              Actual Failure{summary.actualFailures !== 1 ? 's' : ''}
            </span>
          </div>
        )}
        {missingCount > 0 && (
          <div className={`${styles.outcomeCard} ${styles.outcomeCard_warning}`}>
            <span className={styles.outcomeValue}>{missingCount}</span>
            <span className={styles.outcomeLabel}>
              Missing Document{missingCount !== 1 ? 's' : ''}
            </span>
          </div>
        )}
        {summary.pending > 0 && (
          <div className={`${styles.outcomeCard} ${styles.outcomeCard_info}`}>
            <span className={styles.outcomeValue}>{summary.pending}</span>
            <span className={styles.outcomeLabel}>
              Pending Check{summary.pending !== 1 ? 's' : ''}
            </span>
          </div>
        )}
        {summary.warnings > 0 && (
          <div className={`${styles.outcomeCard} ${styles.outcomeCard_warning}`}>
            <span className={styles.outcomeValue}>{summary.warnings}</span>
            <span className={styles.outcomeLabel}>
              Warning{summary.warnings !== 1 ? 's' : ''}
            </span>
          </div>
        )}
        {summary.actualFailures === 0 && missingCount === 0 && summary.pending === 0 && summary.warnings === 0 && (
          <div className={`${styles.outcomeCard} ${styles.outcomeCard_success}`}>
            <span className={styles.outcomeValue}>✓</span>
            <span className={styles.outcomeLabel}>All checks passed</span>
          </div>
        )}
      </div>

      {/* Layer B — Document completeness */}
      <div className={styles.completenessBlock}>
        <span className={styles.blockTitle}>Document Completeness</span>
        <div className={styles.completenessRow}>
          <span className={styles.completenessValue}>
            {presentCount} / {requiredCount} present
          </span>
          <span className={styles.completenessPercent}>{completenessPercentage}%</span>
        </div>
        <div className={styles.progressTrack}>
          <div
            className={styles.progressFill}
            style={{ width: `${completenessPercentage}%` }}
          />
        </div>
      </div>

      {/* Layer C — Validation checks breakdown */}
      <div className={styles.breakdownBlock}>
        <span className={styles.blockTitle}>
          Validation Checks — {summary.totalChecks} Total
        </span>
        <div className={styles.breakdownBar}>
          <BreakdownSegment label="Passed" count={summary.passed} variant="success" total={summary.totalChecks} />
          <BreakdownSegment label="Failed" count={summary.actualFailures} variant="danger" total={summary.totalChecks} />
          <BreakdownSegment label="Warning" count={summary.warnings} variant="warning" total={summary.totalChecks} />
          <BreakdownSegment label="Pending" count={summary.pending} variant="info" total={summary.totalChecks} />
          <BreakdownSegment label="Not Verifiable" count={summary.notVerifiable} variant="neutral" total={summary.totalChecks} />
        </div>
        <div className={styles.legend}>
          <span className={styles.legendItem}>✓ Passed {summary.passed}</span>
          <span className={styles.legendItem}>✕ Failed {summary.actualFailures}</span>
          <span className={styles.legendItem}>⚠ Warning {summary.warnings}</span>
          <span className={styles.legendItem}>⏳ Pending {summary.pending}</span>
          <span className={styles.legendItem}>— Not Verifiable {summary.notVerifiable}</span>
        </div>
      </div>
    </section>
  );
}

export default ReportSummaryCards;

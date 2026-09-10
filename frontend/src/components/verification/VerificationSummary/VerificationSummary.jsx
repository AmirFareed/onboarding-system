import { FileCheck2, Fingerprint, Stamp, Link2, TextCursorInput } from 'lucide-react';
import StatusChip from '../../common/StatusChip/StatusChip';
import styles from './VerificationSummary.module.css';

function Breakdown({ passed, warnings, failed }) {
  const items = [
    { label: 'Passed', count: passed, variant: 'success' },
    { label: 'Warnings', count: warnings, variant: 'warning' },
    { label: 'Failed', count: failed, variant: 'danger' },
  ];
  return (
    <div className={styles.breakdown}>
      {items.map(({ label, count, variant }) => (
        <div key={label} className={styles.breakdownRow}>
          <StatusChip label={`${count} ${label}`} variant={variant} />
        </div>
      ))}
    </div>
  );
}

function SummaryCard({ icon: Icon, title, value, detail, children }) {
  return (
    <div className={styles.card} aria-label={title}>
      <div className={styles.cardHeader}>
        <div className={styles.iconWrap} aria-hidden="true">
          <Icon />
        </div>
        <h4 className={styles.cardTitle}>{title}</h4>
      </div>
      <div className={styles.value}>{value}</div>
      {detail && <p className={styles.detail}>{detail}</p>}
      {children}
    </div>
  );
}

/**
 * Overall verification summary cards.
 *
 * Derives employee-facing aggregates from the stored rule results: document
 * completeness, signature and stamp checks (from the visual category), cross-
 * document consistency and required-field checks. Counts are shown with the
 * shared status vocabulary; no internal rule names or technical metadata.
 *
 * @param {object} props
 * @param {object} props.summary Computed summary aggregates.
 */
function VerificationSummary({ summary }) {
  return (
    <section className={styles.section} aria-label="Overall verification summary">
      <div className={styles.grid}>
        <SummaryCard
          icon={FileCheck2}
          title="Document Completeness"
          value={`${summary.completionPercentage}%`}
          detail={`${summary.requiredPresent} of ${summary.requiredTotal} required documents`}
        >
          <Breakdown passed={summary.requiredPresent} warnings={0} failed={summary.requiredTotal - summary.requiredPresent} />
        </SummaryCard>

        <SummaryCard
          icon={Fingerprint}
          title="Signatures"
          value={summary.signatures.total ? 'Checked' : 'No checks'}
          detail="Signature presence across documents"
        >
          {summary.signatures.total > 0 && (
            <Breakdown
              passed={summary.signatures.passed}
              warnings={summary.signatures.warnings}
              failed={summary.signatures.failed}
            />
          )}
        </SummaryCard>

        <SummaryCard
          icon={Stamp}
          title="Stamps"
          value={summary.stamps.total ? 'Checked' : 'No checks'}
          detail="Stamp presence across documents"
        >
          {summary.stamps.total > 0 && (
            <Breakdown
              passed={summary.stamps.passed}
              warnings={summary.stamps.warnings}
              failed={summary.stamps.failed}
            />
          )}
        </SummaryCard>

        <SummaryCard
          icon={Link2}
          title="Cross-document Consistency"
          value={summary.crossDocument.total ? 'Checked' : 'No checks'}
          detail="Values matched across documents"
        >
          {summary.crossDocument.total > 0 && (
            <Breakdown
              passed={summary.crossDocument.passed}
              warnings={summary.crossDocument.warnings}
              failed={summary.crossDocument.failed}
            />
          )}
        </SummaryCard>

        <SummaryCard
          icon={TextCursorInput}
          title="Required Fields"
          value={summary.fields.total ? 'Checked' : 'No checks'}
          detail="Required field presence and format"
        >
          {summary.fields.total > 0 && (
            <Breakdown
              passed={summary.fields.passed}
              warnings={summary.fields.warnings}
              failed={summary.fields.failed}
            />
          )}
        </SummaryCard>
      </div>
    </section>
  );
}

export default VerificationSummary;

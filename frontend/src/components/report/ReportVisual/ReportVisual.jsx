import StatusChip from '../../common/StatusChip/StatusChip';
import styles from './ReportVisual.module.css';

/**
 * Compact visual card for signatures or stamps.
 */
function VisualCard({ title, data }) {
  const total = data.present + data.missing + data.pending + data.notVerifiable;
  return (
    <div className={styles.card}>
      <h4 className={styles.cardTitle}>{title}</h4>
      <div className={styles.chipRow}>
        <StatusChip label={`${data.present} Present`} variant="success" icon={'\u2713'} />
        <StatusChip label={`${data.missing} Missing`} variant="danger" icon={'\u2715'} />
        <StatusChip label={`${data.pending} Pending`} variant="info" icon={'\u23F3'} />
        <StatusChip label={`${data.notVerifiable} Not Verifiable`} variant="neutral" icon={'\u2014'} />
      </div>
      <span className={styles.totalNote}>{total} total check{total !== 1 ? 's' : ''}</span>
    </div>
  );
}

/**
 * Signature and stamp visual evidence summary.
 *
 * @param {object} props
 * @param {object|null} props.visual The visual verification data from the view model.
 */
function ReportVisual({ visual }) {
  if (!visual) {
    return (
      <p className={styles.empty}>
        No visual evidence results are available for this application.
      </p>
    );
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.grid}>
        <VisualCard title="Signatures" data={visual.signatures} />
        <VisualCard title="Stamps" data={visual.stamps} />
      </div>
      <div className={styles.definitions}>
        <p className={styles.definition}>
          <strong>Pending:</strong> Document exists, but automated detection has not completed.
        </p>
        <p className={styles.definition}>
          <strong>Not Verifiable:</strong> The required document is missing, so this check cannot currently be performed.
        </p>
      </div>
    </div>
  );
}

export default ReportVisual;

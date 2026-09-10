import styles from './StatusChip.module.css';

/**
 * Coloured pill that renders a status value (application or document status).
 *
 * The caller resolves the raw status via `getApplicationStatus` /
 * `getDocumentStatus` / `getReportStatus` and passes the display label +
 * variant through, keeping this component purely presentational.
 *
 * @param {object} props
 * @param {string} props.label Display text, e.g. "Uploaded".
 * @param {string} props.variant Chip colour: "success", "warning", "danger",
 *   "info" or "neutral".
 * @param {string} [props.icon] Optional icon character displayed before the
 *   dot (e.g. "\u2713" for passed, "\u2715" for failed).
 */
function StatusChip({ label, variant = 'neutral', icon }) {
  return (
    <span className={`${styles.chip} ${styles[variant] ?? styles.neutral}`}>
      {icon && <span className={styles.icon} aria-hidden="true">{icon}</span>}
      <span className={styles.dot} aria-hidden="true" />
      {label}
    </span>
  );
}

export default StatusChip;

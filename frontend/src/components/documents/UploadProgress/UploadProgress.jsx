import styles from './UploadProgress.module.css';

/**
 * Horizontal progress bar showing the upload percentage of one document.
 *
 * @param {object} props
 * @param {number} props.progress A value from 0 to 100.
 * @param {string} [props.label] Optional text above the bar.
 */
function UploadProgress({ progress, label }) {
  const clamped = Math.max(0, Math.min(100, Math.round(progress ?? 0)));

  return (
    <div className={styles.container}>
      {label && (
        <div className={styles.labelRow}>
          <span className={styles.label}>{label}</span>
          <span className={styles.percent}>{clamped}%</span>
        </div>
      )}
      <div className={styles.track} role="progressbar" aria-valuenow={clamped} aria-valuemin={0} aria-valuemax={100}>
        <div className={styles.bar} style={{ width: `${clamped}%` }} />
      </div>
    </div>
  );
}

export default UploadProgress;

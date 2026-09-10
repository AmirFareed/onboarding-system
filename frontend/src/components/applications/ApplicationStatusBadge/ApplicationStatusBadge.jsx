import { getApplicationStatus } from '../../../data/statuses';
import styles from './ApplicationStatusBadge.module.css';

/**
 * Coloured pill showing an application's lifecycle status.
 *
 * Resolves the raw backend status value through the shared status catalogue
 * and renders it with the spec's colour mapping (blue / sky / orange / green /
 * red / purple / rose, grey fallback for unknown values).
 *
 * @param {object} props
 * @param {string} props.status Raw application status value (backend enum).
 * @param {string} [props.className] Optional extra class applied to the pill.
 */
function ApplicationStatusBadge({ status, className }) {
  const entry = getApplicationStatus(status);
  const colorClass = styles[entry.color] ?? styles.gray;
  return (
    <span className={`${styles.badge} ${colorClass} ${className ?? ''}`}>
      {entry.label}
    </span>
  );
}

export default ApplicationStatusBadge;

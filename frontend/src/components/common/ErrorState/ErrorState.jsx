import { AlertTriangle } from 'lucide-react';
import styles from './ErrorState.module.css';

/**
 * Full-width error block with a retry action, used for failed fetches.
 *
 * @param {object} props
 * @param {string} props.message The error message to display.
 * @param {Function} props.onRetry Callback to retry the failed request.
 */
function ErrorState({ message, onRetry }) {
  return (
    <div className={styles.error} role="alert">
      <div className={styles.iconWrap} aria-hidden="true">
        <AlertTriangle />
      </div>
      <div className={styles.body}>
        <h3 className={styles.title}>Something went wrong</h3>
        <p className={styles.message}>{message}</p>
      </div>
      {onRetry && (
        <button className={styles.retry} type="button" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export default ErrorState;

import { AlertTriangle } from 'lucide-react';
import { ErrorBoundary as ReactErrorBoundary } from 'react-error-boundary';

import styles from './ErrorBoundary.module.css';

/**
 * Full-page fallback shown when a render error would otherwise unmount the
 * whole app.
 *
 * @param {object} props
 * @param {Error} props.error The error that was thrown.
 * @param {Function} props.resetErrorBoundary Retries the failed subtree.
 */
function Fallback({ error, resetErrorBoundary }) {
  return (
    <div className={styles.page} role="alert">
      <div className={styles.card}>
        <div className={styles.iconWrap} aria-hidden="true">
          <AlertTriangle />
        </div>
        <h2 className={styles.title}>Something went wrong</h2>
        <p className={styles.message}>{error.message}</p>
        <button className={styles.retry} type="button" onClick={resetErrorBoundary}>
          Try again
        </button>
      </div>
    </div>
  );
}

export { ReactErrorBoundary as ErrorBoundary, Fallback };

import EmptyState from '../../common/EmptyState/EmptyState';
import styles from './RecentActivity.module.css';

/**
 * Recent Activity dashboard section.
 *
 * Displays a static empty state; activity records will come from the backend
 * integration in a later phase and are never fabricated here.
 */
function RecentActivity() {
  return (
    <section className={styles.card} aria-label="Recent activity">
      <h3 className={styles.title}>Recent Activity</h3>
      <EmptyState
        title="No recent activity"
        message="Activity will appear here as applications are processed."
      />
    </section>
  );
}

export default RecentActivity;

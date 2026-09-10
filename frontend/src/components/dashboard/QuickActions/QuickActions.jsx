import { Link } from 'react-router-dom';
import { getDashboardActions } from '../../../data/dashboard';
import { useAuth } from '../../../hooks/useAuth';
import styles from './QuickActions.module.css';

/**
 * Role-aware dashboard Quick Actions.
 *
 * The shortcut cards come from `getDashboardActions(user)`, which resolves the
 * acting user's canonical role to its action set (Employee sees everything,
 * Operator/Reviewer/IT see their own subsets -- see src/data/dashboard.js).
 * Navigation visibility only -- the backend 403 stays authoritative.
 */
function QuickActions() {
  const { user } = useAuth();
  const actions = getDashboardActions(user);

  return (
    <section className={styles.section} aria-label="Quick actions">
      <h3 className={styles.title}>Quick Actions</h3>
      <div className={styles.grid}>
        {actions.map(({ id, label, description, to, icon: Icon }) => (
          <Link key={id} to={to} className={styles.action}>
            <div className={styles.iconWrap} aria-hidden="true">
              <Icon />
            </div>
            <div className={styles.meta}>
              <span className={styles.actionLabel}>{label}</span>
              <span className={styles.actionDescription}>{description}</span>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}

export default QuickActions;
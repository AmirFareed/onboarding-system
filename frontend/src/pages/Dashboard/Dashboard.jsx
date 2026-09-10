import QuickActions from '../../components/dashboard/QuickActions/QuickActions';
import RecentActivity from '../../components/dashboard/RecentActivity/RecentActivity';
import RecentApplications from '../../components/dashboard/RecentApplications/RecentApplications';
import { getDashboardWelcome } from '../../data/dashboard';
import { useAuth } from '../../hooks/useAuth';
import styles from './Dashboard.module.css';

/**
 * Landing page of the dashboard.
 *
 * Represents a real employee workspace: a welcome header, quick actions and
 * two empty-state sections (recent applications and recent activity). No
 * statistics or business data is fabricated; the sections will be populated
 * once the dashboard API integration is implemented in a later phase.
 */
function Dashboard() {
  const { user } = useAuth();

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h2 className={styles.welcome}>Welcome back!</h2>
        <p className={styles.subtitle}>{getDashboardWelcome(user)}</p>
      </header>

      <QuickActions />

      <div className={styles.columns}>
        <RecentApplications />
        <RecentActivity />
      </div>
    </div>
  );
}

export default Dashboard;

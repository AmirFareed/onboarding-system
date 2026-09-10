import { Menu } from 'lucide-react';

import { useAuth } from '../../../hooks/useAuth';
import { USER_PROFILE } from '../../../data/dashboard';
import ThemeToggle from '../../theme/ThemeToggle/ThemeToggle';
import styles from './Navbar.module.css';

/**
 * Top navigation bar of the dashboard.
 *
 * Left side holds the responsive menu toggle, the page title and a breadcrumb;
 * the right side holds a functional theme toggle and the employee profile
 * with the current date. There is no search or notifications feature in the
 * product yet, so those controls aren't rendered here rather than shown as
 * non-functional decoration.
 *
 * @param {string} title Page title shown in the bar.
 * @param {string} breadcrumb Breadcrumb trail for the current page.
 * @param {boolean} showMenu Whether the hamburger toggle is visible.
 * @param {Function} onToggleSidebar Callback fired when the toggle is clicked.
 */
function Navbar({ title, breadcrumb, showMenu = false, onToggleSidebar }) {
  const { user } = useAuth();
  const today = new Date().toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });

  const displayName = user?.name ?? USER_PROFILE.name;
  // The backend user model has no `initials` field (see auth/schemas.py's
  // UserRead: only email/name), so this is always computed from the name.
  const initials = displayName
    .split(' ')
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase();

  return (
    <header className={styles.navbar}>
      <div className={styles.left}>
        {showMenu && (
          <button
            className={styles.iconButton}
            type="button"
            aria-label="Toggle navigation"
            onClick={onToggleSidebar}
          >
            <Menu aria-hidden="true" />
          </button>
        )}
        <div className={styles.titles}>
          <h1 className={styles.title}>{title}</h1>
          <span className={styles.breadcrumb}>{breadcrumb}</span>
        </div>
      </div>

      <div className={styles.right}>
        <ThemeToggle />

        <div className={styles.profile}>
          <div className={styles.avatar} aria-hidden="true">
            {initials}
          </div>
          <div className={styles.profileInfo}>
            <span className={styles.profileName}>{displayName}</span>
            <span className={styles.date}>{today}</span>
          </div>
        </div>
      </div>
    </header>
  );
}

export default Navbar;

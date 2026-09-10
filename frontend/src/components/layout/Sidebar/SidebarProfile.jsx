import { LogOut } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { useAuth } from '../../../hooks/useAuth';
import { USER_PROFILE } from '../../../data/dashboard';
import styles from './Sidebar.module.css';

function SidebarProfile() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const name = user?.name ?? USER_PROFILE.name;
  // The backend user model has no `initials` field (see auth/schemas.py's
  // UserRead: only email/name), so this is always computed from the name.
  const initials = name
    .split(' ')
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase();

  const handleLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  return (
    <>
      <div className={styles.user}>
        <div className={styles.avatar} aria-hidden="true">
          {initials}
        </div>
        <div className={styles.userInfo}>
          <span className={styles.userName}>{name}</span>
          <span className={styles.userStatus}>
            <span className={styles.onlineDot} aria-hidden="true" />
            Online
          </span>
        </div>
      </div>
      <button
        className={styles.logout}
        type="button"
        title="Logout"
        aria-label="Logout"
        onClick={handleLogout}
      >
        <LogOut className={styles.logoutIcon} aria-hidden="true" />
        <span className={styles.navLabel}>Logout</span>
      </button>
    </>
  );
}

export default SidebarProfile;

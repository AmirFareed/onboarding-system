import { ChevronsLeft, ChevronsRight } from 'lucide-react';
import { useLocation } from 'react-router-dom';

import Logo from '../../common/Logo/Logo';
import { findNavItem } from '../../../data/navigation';
import { useAuth } from '../../../hooks/useAuth';
import { visibleNavigationFor } from '../../../utils/roles';
import SidebarItem from './SidebarItem';
import SidebarProfile from './SidebarProfile';
import styles from './Sidebar.module.css';

function Sidebar({ collapsed = false, drawerOpen = false, onNavigate, onToggleCollapse }) {
  const location = useLocation();
  const { user } = useAuth();
  const navigation = visibleNavigationFor(user);
  const activeItem = findNavItem(location.pathname);

  const className = [
    styles.sidebar,
    collapsed ? styles.collapsed : '',
    drawerOpen ? styles.drawerOpen : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <aside className={className}>
      <div className={styles.brand}>
        <Logo className={styles.logo} />
        <div className={styles.brandText}>
          <span className={styles.brandName}>FinTech</span>
          <span className={styles.brandSubtitle}>Onboarding Automation System</span>
        </div>
      </div>

      <nav className={styles.nav} aria-label="Primary">
        {navigation.map((section) => (
          <div key={section.id} className={styles.section}>
            <p className={styles.sectionLabel}>{section.label}</p>
            <ul className={styles.navList}>
              {section.items.map((item) => (
                <SidebarItem
                  key={item.id}
                  item={item}
                  active={item.id === activeItem.id}
                  onClick={onNavigate}
                />
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <div className={styles.footer}>
        <button
          className={styles.collapseButton}
          type="button"
          onClick={onToggleCollapse}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? (
            <ChevronsRight className={styles.navIcon} aria-hidden="true" />
          ) : (
            <ChevronsLeft className={styles.navIcon} aria-hidden="true" />
          )}
          <span className={styles.navLabel}>{collapsed ? 'Expand' : 'Collapse'}</span>
        </button>
        <SidebarProfile />
      </div>
    </aside>
  );
}

export default Sidebar;

import { useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';

import { useMediaQuery } from '../../../hooks/useMediaQuery';
import { findNavItem } from '../../../data/navigation';
import Navbar from '../Navbar/Navbar';
import Sidebar from '../Sidebar/Sidebar';
import styles from './DashboardLayout.module.css';

/**
 * Application shell that wraps every routed page.
 *
 * The sidebar responds to the viewport size: fixed and expanded on desktop,
 * an icon-only rail on tablet, and a drawer with a backdrop overlay on mobile.
 * The page title and breadcrumb are derived from the current route so the
 * navbar always reflects the active navigation entry.
 */
function DashboardLayout() {
  const location = useLocation();
  const isDesktop = useMediaQuery('(min-width: 1024px)');
  const isTablet = useMediaQuery('(min-width: 768px) and (max-width: 1023px)');
  const isMobile = useMediaQuery('(max-width: 767px)');

  const [collapsed, setCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Close the mobile drawer whenever the route changes, adjusted during
  // render (React's recommended pattern) rather than in an effect.
  const [drawerClosedForPath, setDrawerClosedForPath] = useState(location.pathname);
  if (location.pathname !== drawerClosedForPath) {
    setDrawerClosedForPath(location.pathname);
    setDrawerOpen(false);
  }

  const showMenuToggle = isTablet || isMobile;
  const navItem = findNavItem(location.pathname);
  const breadcrumb = navItem.id === 'dashboard' ? 'Home' : `Dashboard / ${navItem.label}`;

  const handleToggleSidebar = () => {
    if (isTablet) {
      setCollapsed((value) => !value);
    } else {
      setDrawerOpen((value) => !value);
    }
  };

  const handleToggleCollapse = () => {
    if (isMobile) {
      setDrawerOpen(false);
    } else {
      setCollapsed((value) => !value);
    }
  };

  const isCompact = collapsed && (isDesktop || isTablet);

  const mainClassName = [
    styles.main,
    isDesktop && collapsed ? styles.sidebarCompact : '',
    isTablet ? (collapsed ? styles.sidebarCollapsed : styles.sidebarVisible) : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={styles.shell}>
      <Sidebar
        collapsed={isCompact}
        drawerOpen={isMobile && drawerOpen}
        onNavigate={() => setDrawerOpen(false)}
        onToggleCollapse={handleToggleCollapse}
      />

      {isMobile && drawerOpen && (
        <div
          className={styles.backdrop}
          role="presentation"
          onClick={() => setDrawerOpen(false)}
        />
      )}

      <div className={mainClassName}>
        <Navbar
          title={navItem.label}
          breadcrumb={breadcrumb}
          showMenu={showMenuToggle}
          onToggleSidebar={handleToggleSidebar}
        />
        <main className={styles.content}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default DashboardLayout;

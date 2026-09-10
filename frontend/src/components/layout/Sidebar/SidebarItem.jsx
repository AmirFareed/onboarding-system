import { Link } from 'react-router-dom';

import styles from './Sidebar.module.css';

function SidebarItem({ item, active = false, onClick }) {
  const { path, label, icon: Icon } = item;

  return (
    <li>
      <Link
        to={path}
        onClick={onClick}
        title={label}
        className={`${styles.navItem} ${active ? styles.active : ''}`}
      >
        <Icon className={styles.navIcon} aria-hidden="true" />
        <span className={styles.navLabel}>{label}</span>
      </Link>
    </li>
  );
}

export default SidebarItem;

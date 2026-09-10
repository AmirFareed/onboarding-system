import styles from './PlaceholderPage.module.css';

/**
 * Generic page rendered for every menu entry that does not have its own screen
 * yet. It keeps navigation functional and the active highlight correct while
 * each feature is built out in its own phase.
 *
 * @param {object} props
 * @param {string} props.title Page heading, e.g. "Upload Documents".
 * @param {string} props.description Short note explaining the module is
 *   scheduled for a future phase.
 */
function PlaceholderPage({ title, description }) {
  return (
    <div className={styles.page}>
      <span className={styles.badge} aria-hidden="true">
        Coming soon
      </span>
      <h2 className={styles.title}>{title}</h2>
      <p className={styles.description}>{description}</p>
    </div>
  );
}

export default PlaceholderPage;

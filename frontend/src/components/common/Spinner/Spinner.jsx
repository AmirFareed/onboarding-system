import styles from './Spinner.module.css';

/**
 * Small loading indicator. Used inside buttons and inline loading states.
 *
 * @param {object} props
 * @param {string} [props.size] Either "small" or "medium".
 */
function Spinner({ size = 'small' }) {
  return <span className={`${styles.spinner} ${size === 'medium' ? styles.medium : ''}`} aria-hidden="true" />;
}

export default Spinner;

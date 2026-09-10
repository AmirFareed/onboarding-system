import { Search } from 'lucide-react';

import styles from './ApplicationSearch.module.css';

/**
 * Search input for the applications list.
 *
 * @param {object} props
 * @param {string} props.value Current search term.
 * @param {Function} props.onChange Callback with the next term.
 * @param {string} [props.id] Optional id for label association.
 */
function ApplicationSearch({ value, onChange, id }) {
  return (
    <label className={styles.search} htmlFor={id}>
      <Search className={styles.icon} aria-hidden="true" />
      <span className={styles.srOnly}>Search applications</span>
      <input
        id={id}
        className={styles.input}
        type="search"
        placeholder="Search by application ID, created by, or notes..."
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-label="Search applications"
      />
    </label>
  );
}

export default ApplicationSearch;
